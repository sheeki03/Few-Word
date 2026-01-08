#!/usr/bin/env python3
"""
PreToolUse hook: Rewrite Bash commands to offload outputs to filesystem.

Input (stdin): JSON with tool_name, tool_input, cwd, session_id
Output (stdout): JSON with hookSpecificOutput containing updatedInput

v1.3 features:
- Tiered offloading: inline (<512B), compact pointer (512B-4KB), preview (>4KB)
- Ultra-compact pointer (~35 tokens)
- Smart preview: only for failures (exit != 0)
- Session ID tracking for stats
- Exit code in filename for smart retention
- Manifest writing (append-only)
- LATEST symlinks for easy retrieval
"""

import json
import sys
import os
import re
import uuid
from pathlib import Path
from datetime import datetime


# === Configuration (env var overridable, with safe fallbacks) ===
def _safe_int(env_var: str, default: int) -> int:
    """Parse env var as int with fallback on invalid input."""
    try:
        return int(os.environ.get(env_var, default))
    except ValueError:
        return default

INLINE_MAX = _safe_int('FEWWORD_INLINE_MAX', 512)      # < this: show inline
PREVIEW_MIN = _safe_int('FEWWORD_PREVIEW_MIN', 4096)   # > this: add preview
PREVIEW_LINES = _safe_int('FEWWORD_PREVIEW_LINES', 5)  # max preview lines
PREVIEW_LINE_MAX = 200  # truncate long preview lines
OPEN_CMD = os.environ.get('FEWWORD_OPEN_CMD', '/context-open')   # retrieval command
SHOW_PATH = os.environ.get('FEWWORD_SHOW_PATH', '0') == '1'      # append path to pointer
VERBOSE_POINTER = os.environ.get('FEWWORD_VERBOSE_POINTER', '0') == '1'  # old v2.0 format

# Interactive commands that should NEVER be intercepted
INTERACTIVE_COMMANDS = {
    'ssh', 'vim', 'vi', 'nvim', 'nano', 'emacs', 'less', 'more', 'top',
    'htop', 'watch', 'tmux', 'screen', 'ftp', 'sftp', 'telnet', 'python',
    'python3', 'node', 'irb', 'rails', 'psql', 'mysql', 'sqlite3', 'mongosh',
    'redis-cli', 'man', 'info', 'edit', 'pico', 'joe', 'jed', 'ne'
}

# Patterns indicating command handles its own output - skip these
SKIP_PATTERNS = [
    r'>\s*\S+',           # stdout redirect: > file, >> file
    r'2>\s*\S+',          # stderr redirect: 2> file
    r'&>\s*\S+',          # both redirect: &> file
    r'\|\s*tee\s+',       # piping to tee
    r'\|\s*less',         # piping to pager
    r'\|\s*more',         # piping to pager
    r'<<',                # heredoc (may contain sensitive data)
]


def is_disabled(cwd: str) -> bool:
    """Check if offloading is disabled via env var or file."""
    if os.environ.get('FEWWORD_DISABLE'):
        return True
    disable_file = Path(cwd) / '.fewword' / 'DISABLE_OFFLOAD'
    if disable_file.exists():
        return True
    return False


def get_first_command(cmd: str) -> str:
    """Extract the first actual command word, handling prefixes."""
    cmd = cmd.strip()
    prefixes = ['sudo', 'env', 'nohup', 'nice', 'time', 'strace', 'ltrace']
    words = cmd.split()

    for word in words:
        # Skip environment variable assignments (VAR=value)
        if '=' in word and not word.startswith('-'):
            continue
        # Skip known prefixes
        if word in prefixes:
            continue
        # Return the actual command (handle full paths)
        return word.split('/')[-1]

    return words[0] if words else ''


def should_skip(command: str) -> tuple[bool, str]:
    """
    Determine if command should skip offloading.
    Returns (should_skip, reason).
    """
    if not command or not command.strip():
        return True, "empty command"

    # Check for pipes - SKIP (exit code masking)
    if '|' in command:
        return True, "pipeline (skips to avoid exit code issues)"

    first_cmd = get_first_command(command)

    # Check interactive commands
    if first_cmd in INTERACTIVE_COMMANDS:
        return True, f"interactive: {first_cmd}"

    # Check skip patterns (redirects, heredocs, etc.)
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, command):
            return True, "already handling output"

    # Skip trivial commands
    if len(command.strip()) < 10:
        return True, "trivial command"

    return False, ""


def get_session_id(cwd: str) -> str:
    """Read current session ID from session.json."""
    session_file = Path(cwd) / '.fewword' / 'index' / 'session.json'
    try:
        with open(session_file, 'r') as f:
            data = json.load(f)
            return data.get('session_id', '')
    except (OSError, json.JSONDecodeError):
        return ''


def generate_wrapper(original_cmd: str, output_dir: str, safe_cmd: str,
                     timestamp: str, event_id: str, cwd: str, session_id: str) -> str:
    """
    Generate bash wrapper that implements tiered offloading.

    v1.3: Tiered logic + compact pointer + smart preview + session tracking.

    Tiers:
    1. < INLINE_MAX (512B): Show inline, delete file
    2. INLINE_MAX - PREVIEW_MIN (512B-4KB): Compact pointer only
    3. > PREVIEW_MIN (4KB+): Compact pointer + preview (failures only)
    """
    # Escape paths for shell
    escaped_dir = output_dir.replace("'", "'\"'\"'")
    escaped_cwd = cwd.replace("'", "'\"'\"'")
    escaped_open_cmd = OPEN_CMD.replace("'", "'\"'\"'")

    wrapper = f'''
set -o pipefail

__fw_dir='{escaped_dir}'
__fw_cwd='{escaped_cwd}'
__fw_cmd='{safe_cmd}'
__fw_ts='{timestamp}'
__fw_id='{event_id}'
__fw_session='{session_id}'
__fw_open_cmd='{escaped_open_cmd}'
__fw_manifest="$__fw_cwd/.fewword/index/tool_outputs.jsonl"

mkdir -p "$__fw_dir" 2>/dev/null
mkdir -p "$(dirname "$__fw_manifest")" 2>/dev/null

# Temporary file (without exit code)
__fw_tmp="$__fw_dir/${{__fw_cmd}}_${{__fw_ts}}_${{__fw_id}}_tmp.txt"

# 1. Capture stdout+stderr to temp file, preserve real exit code
# Use subshell ( ) not compound command {{ }} so 'exit N' in command doesn't exit wrapper
( {original_cmd} ) > "$__fw_tmp" 2>&1
__fw_exit=$?

# 2. Final filename with exit code
__fw_out="$__fw_dir/${{__fw_cmd}}_${{__fw_ts}}_${{__fw_id}}_exit${{__fw_exit}}.txt"
__fw_rel_path=".fewword/scratch/tool_outputs/${{__fw_cmd}}_${{__fw_ts}}_${{__fw_id}}_exit${{__fw_exit}}.txt"

# 3. Rename temp to final
mv "$__fw_tmp" "$__fw_out" 2>/dev/null

# 4. Measure size
__fw_bytes=$(wc -c < "$__fw_out" 2>/dev/null | tr -d ' ')
__fw_lines=$(wc -l < "$__fw_out" 2>/dev/null | tr -d ' ')

# 5. Format size for display (human readable)
if [ "${{__fw_bytes:-0}}" -ge 1048576 ]; then
  __fw_size="$(((__fw_bytes + 524288) / 1048576))M"
elif [ "${{__fw_bytes:-0}}" -ge 1024 ]; then
  __fw_size="$(((__fw_bytes + 512) / 1024))K"
else
  __fw_size="${{__fw_bytes}}B"
fi

# 6. Build compact pointer line (single line, no newlines)
__fw_pointer="[fw $__fw_id] $__fw_cmd e=$__fw_exit $__fw_size ${{__fw_lines}}L | $__fw_open_cmd $__fw_id"
'''

    # Add path to pointer if FEWWORD_SHOW_PATH=1
    if SHOW_PATH:
        wrapper += '''
__fw_pointer="$__fw_pointer | $__fw_rel_path"
'''

    # Verbose pointer for backwards compat
    if VERBOSE_POINTER:
        wrapper += f'''
# VERBOSE MODE (FEWWORD_VERBOSE_POINTER=1)
# Tier decision with verbose output
if [ "${{__fw_bytes:-0}}" -lt {INLINE_MAX} ]; then
  # INLINE: show full content, delete file
  cat "$__fw_out"
  rm -f "$__fw_out"
else
  # Large output: show verbose pointer and preview
  echo ""
  echo "=== [FewWord: Output offloaded] ==="
  echo "File: $__fw_out"
  echo "Size: $__fw_bytes bytes, $__fw_lines lines"
  echo "Exit: $__fw_exit"
  echo "ID: $__fw_id"
  echo ""

  if [ "$__fw_lines" -le 20 ]; then
    echo "=== Full output ==="
    cat "$__fw_out"
  else
    echo "=== First 10 lines ==="
    head -10 "$__fw_out"
    __fw_omitted=$(( __fw_lines - 20 ))
    echo ""
    echo "... ($__fw_omitted lines omitted) ..."
    echo ""
    echo "=== Last 10 lines ==="
    tail -10 "$__fw_out"
  fi

  echo ""
  echo "=== Retrieval commands ==="
  echo "  Full: cat $__fw_out"
  echo "  Latest: cat $__fw_dir/LATEST_$__fw_cmd.txt"
  echo "  Grep: grep 'pattern' $__fw_out"

  # Write manifest entry (append-only)
  __fw_now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  printf '{{"type":"offload","id":"%s","session_id":"%s","created_at":"%s","cmd":"%s","exit_code":%d,"bytes":%d,"lines":%d,"path":"%s"}}\\n' \\
    "$__fw_id" "$__fw_session" "$__fw_now" "$__fw_cmd" "$__fw_exit" "$__fw_bytes" "$__fw_lines" "$__fw_rel_path" \\
    >> "$__fw_manifest" 2>/dev/null

  # Create LATEST symlinks (absolute paths)
  __fw_abs_out="$(cd "$(dirname "$__fw_out")" && pwd)/$(basename "$__fw_out")"
  ln -sf "$__fw_abs_out" "$__fw_dir/LATEST.txt" 2>/dev/null
  ln -sf "$__fw_abs_out" "$__fw_dir/LATEST_$__fw_cmd.txt" 2>/dev/null
fi
'''
    else:
        # Compact mode (default)
        wrapper += f'''
# COMPACT MODE (default)
# Tier decision: inline < {INLINE_MAX}B, compact {INLINE_MAX}B-{PREVIEW_MIN}B, preview > {PREVIEW_MIN}B
if [ "${{__fw_bytes:-0}}" -lt {INLINE_MAX} ]; then
  # TIER 1 - INLINE: show full content, delete file
  cat "$__fw_out"
  rm -f "$__fw_out"
elif [ "${{__fw_bytes:-0}}" -lt {PREVIEW_MIN} ]; then
  # TIER 2 - COMPACT: pointer only, no preview
  echo "$__fw_pointer"

  # Write manifest entry (append-only)
  __fw_now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  printf '{{"type":"offload","id":"%s","session_id":"%s","created_at":"%s","cmd":"%s","exit_code":%d,"bytes":%d,"lines":%d,"path":"%s"}}\\n' \\
    "$__fw_id" "$__fw_session" "$__fw_now" "$__fw_cmd" "$__fw_exit" "$__fw_bytes" "$__fw_lines" "$__fw_rel_path" \\
    >> "$__fw_manifest" 2>/dev/null

  # Create LATEST symlinks (absolute paths)
  __fw_abs_out="$(cd "$(dirname "$__fw_out")" && pwd)/$(basename "$__fw_out")"
  ln -sf "$__fw_abs_out" "$__fw_dir/LATEST.txt" 2>/dev/null
  ln -sf "$__fw_abs_out" "$__fw_dir/LATEST_$__fw_cmd.txt" 2>/dev/null
else
  # TIER 3 - PREVIEW: pointer + smart preview (failures only)
  echo "$__fw_pointer"

  # Show preview only for failures (exit != 0)
  if [ "$__fw_exit" -ne 0 ]; then
    # Plain tail - last {PREVIEW_LINES} lines, truncated to {PREVIEW_LINE_MAX} chars
    tail -{PREVIEW_LINES} "$__fw_out" | cut -c1-{PREVIEW_LINE_MAX}
  fi

  # Write manifest entry (append-only)
  __fw_now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  printf '{{"type":"offload","id":"%s","session_id":"%s","created_at":"%s","cmd":"%s","exit_code":%d,"bytes":%d,"lines":%d,"path":"%s"}}\\n' \\
    "$__fw_id" "$__fw_session" "$__fw_now" "$__fw_cmd" "$__fw_exit" "$__fw_bytes" "$__fw_lines" "$__fw_rel_path" \\
    >> "$__fw_manifest" 2>/dev/null

  # Create LATEST symlinks (absolute paths)
  __fw_abs_out="$(cd "$(dirname "$__fw_out")" && pwd)/$(basename "$__fw_out")"
  ln -sf "$__fw_abs_out" "$__fw_dir/LATEST.txt" 2>/dev/null
  ln -sf "$__fw_abs_out" "$__fw_dir/LATEST_$__fw_cmd.txt" 2>/dev/null
fi
'''

    wrapper += '''
# Always preserve exit code
exit $__fw_exit
'''
    return wrapper.strip()


def main():
    # Read JSON input from stdin
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            sys.exit(0)
        input_data = json.loads(raw_input)
    except json.JSONDecodeError:
        # Invalid JSON - pass through silently
        sys.exit(0)

    # Only process Bash tool
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    tool_input = input_data.get("tool_input", {})
    command = tool_input.get("command", "")
    cwd = input_data.get("cwd", os.getcwd())

    # Check escape hatch
    if is_disabled(cwd):
        sys.exit(0)

    # Check if should skip
    skip, reason = should_skip(command)
    if skip:
        sys.exit(0)

    # Get session ID from session.json
    session_id = get_session_id(cwd)

    # Generate unique event ID for correlation
    event_id = uuid.uuid4().hex[:8]

    # Generate filename components
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    first_cmd = get_first_command(command)
    safe_cmd = re.sub(r'[^a-zA-Z0-9_-]', '_', first_cmd)[:20]
    output_dir = f"{cwd}/.fewword/scratch/tool_outputs"

    # Generate wrapped command
    wrapped = generate_wrapper(command, output_dir, safe_cmd, timestamp, event_id, cwd, session_id)

    # Return the updated input with correct JSON envelope
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": {
                "command": wrapped
            }
        }
    }

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
