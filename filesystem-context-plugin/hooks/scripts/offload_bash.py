#!/usr/bin/env python3
"""
PreToolUse hook: Rewrite Bash commands to offload large outputs to filesystem.

Input (stdin): JSON with tool_name, tool_input, cwd, session_id
Output (stdout): JSON with hookSpecificOutput containing updatedInput

The wrapper uses write-then-decide logic:
1. Always capture stdout+stderr to file first
2. After command completes, measure file size
3. If small (<8KB): cat file to stdout, delete file (normal UX)
4. If large: print pointer + preview only
5. Always preserve exit code
"""

import json
import sys
import os
import re
import uuid
from pathlib import Path
from datetime import datetime


# === Configuration (hardcoded for v1) ===
SIZE_THRESHOLD = 8000  # bytes (~2000 tokens), below this show full output
PREVIEW_LINES = 10     # lines to show from start and end for large outputs

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
    disable_file = Path(cwd) / '.fsctx' / 'DISABLE_OFFLOAD'
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

    # Check for pipes - SKIP in v1 (exit code masking)
    if '|' in command:
        return True, "pipeline (v1 skips to avoid exit code issues)"

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


def generate_wrapper(original_cmd: str, output_file: str, cwd: str) -> str:
    """
    Generate bash wrapper that implements write-then-decide logic.

    1. Capture to file first (can't know size ahead of time)
    2. Measure after command completes
    3. Small output -> cat + delete (normal UX)
    4. Large output -> pointer + preview
    5. Preserve exit code
    """
    # Escape the output file path for shell
    escaped_file = output_file.replace("'", "'\"'\"'")

    wrapper = f'''
__fsctx_out='{escaped_file}'
__fsctx_dir="$(dirname "$__fsctx_out")"
mkdir -p "$__fsctx_dir" 2>/dev/null

# 1. Capture stdout+stderr to file
{{ {original_cmd} ; }} > "$__fsctx_out" 2>&1
__fsctx_exit=$?

# 2. Measure size after command completes
__fsctx_bytes=$(wc -c < "$__fsctx_out" 2>/dev/null | tr -d ' ')
__fsctx_lines=$(wc -l < "$__fsctx_out" 2>/dev/null | tr -d ' ')

# 3. Decide: small -> cat + delete, large -> pointer + preview
if [ "${{__fsctx_bytes:-0}}" -lt {SIZE_THRESHOLD} ]; then
  # Small output: show full content (normal UX)
  cat "$__fsctx_out"
  rm -f "$__fsctx_out"
else
  # Large output: show pointer and preview
  echo ""
  echo "=== [FewWord: Output offloaded] ==="
  echo "File: $__fsctx_out"
  echo "Size: $__fsctx_bytes bytes, $__fsctx_lines lines"
  echo "Exit: $__fsctx_exit"
  echo ""
  if [ "$__fsctx_lines" -le {PREVIEW_LINES * 2} ]; then
    echo "=== Full output ==="
    cat "$__fsctx_out"
  else
    echo "=== First {PREVIEW_LINES} lines ==="
    head -{PREVIEW_LINES} "$__fsctx_out"
    __fsctx_omitted=$(( __fsctx_lines - {PREVIEW_LINES * 2} ))
    echo ""
    echo "... ($__fsctx_omitted lines omitted) ..."
    echo ""
    echo "=== Last {PREVIEW_LINES} lines ==="
    tail -{PREVIEW_LINES} "$__fsctx_out"
  fi
  echo ""
  echo "=== Retrieval commands ==="
  echo "  Full: cat $__fsctx_out"
  echo "  Grep: grep 'pattern' $__fsctx_out"
  echo "  Range: sed -n '50,100p' $__fsctx_out"
fi

# 4. Always preserve exit code
exit $__fsctx_exit
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
    session_id = input_data.get("session_id", "unknown")

    # Check escape hatch
    if is_disabled(cwd):
        sys.exit(0)

    # Check if should skip
    skip, reason = should_skip(command)
    if skip:
        sys.exit(0)

    # Generate unique event ID for correlation
    event_id = uuid.uuid4().hex[:8]

    # Generate output filename with event_id for correlation
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    first_cmd = get_first_command(command)
    safe_cmd = re.sub(r'[^a-zA-Z0-9_-]', '_', first_cmd)[:20]
    output_file = f"{cwd}/.fsctx/scratch/tool_outputs/{safe_cmd}_{timestamp}_{event_id}.txt"

    # Generate wrapped command
    wrapped = generate_wrapper(command, output_file, cwd)

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
