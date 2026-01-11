#!/usr/bin/env python3
"""
PreToolUse hook: Rewrite Bash commands to offload outputs to filesystem.

Input (stdin): JSON with tool_name, tool_input, cwd, session_id
Output (stdout): JSON with hookSpecificOutput containing updatedInput

v1.3.5 features:
- Tiered offloading: inline (<512B), compact pointer (512B-4KB), preview (>4KB)
- Ultra-compact pointer with summary (~40 tokens)
- Smart preview: only for failures (exit != 0)
- Session ID tracking for stats
- Exit code in filename for smart retention
- Manifest writing (append-only) with cmd_token, cmd_group, summary
- LATEST symlinks for easy retrieval
- Redaction of secrets BEFORE writing to disk (ON by default)
- Config file support (.fewwordrc.toml / .fewwordrc.json)
- Command aliases for grouping (npm/yarn/pnpm -> npm group)

Environment variables (see config_loader.py for full list):
- FEWWORD_INLINE_MAX: Max bytes for inline output (default: 512)
- FEWWORD_PREVIEW_MIN: Min bytes for preview tier (default: 4096)
- FEWWORD_DISABLE: Disable all offloading (default: 0)
"""

import json
import sys
import os
import re
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple

# Import FewWord modules (relative import from same directory)
_script_dir = Path(__file__).parent
sys.path.insert(0, str(_script_dir))

try:
    from config_loader import get_config, FewWordConfig
    HAS_CONFIG = True
except ImportError:
    HAS_CONFIG = False
    FewWordConfig = None

try:
    from summary_extractors import get_cmd_token, resolve_cmd_group, extract_summary
    HAS_SUMMARY = True
except ImportError:
    HAS_SUMMARY = False

try:
    from redaction import Redactor, create_redactor_from_config
    HAS_REDACTION = True
except ImportError:
    HAS_REDACTION = False


# === Configuration (config file + env var overridable) ===
def _safe_int(env_var: str, default: int) -> int:
    """Parse env var as int with fallback on invalid input."""
    try:
        return int(os.environ.get(env_var, default))
    except ValueError:
        return default


def get_effective_config(cwd: str) -> Dict:
    """Get effective configuration from config file + env vars."""
    if HAS_CONFIG:
        # P1 fix #14: Wrap config loading to handle malformed configs gracefully
        try:
            config = get_config(cwd)
            return config.to_dict()
        except Exception as e:
            import sys
            print(f"[FewWord] Warning: Config loading failed, using defaults: {e}", file=sys.stderr)
            # Fall through to defaults below
    # Fallback to env vars only (also used on config error)
    return {
        'thresholds': {
            'inline_max': _safe_int('FEWWORD_INLINE_MAX', 512),
            'preview_min': _safe_int('FEWWORD_PREVIEW_MIN', 4096),
            'preview_lines': _safe_int('FEWWORD_PREVIEW_LINES', 5),
        },
        'pointer': {
            'open_cmd': os.environ.get('FEWWORD_OPEN_CMD', '/open'),
            'show_path': os.environ.get('FEWWORD_SHOW_PATH', '0') == '1',
            'verbose': os.environ.get('FEWWORD_VERBOSE_POINTER', '0') == '1',
            'peek_on_pointer': os.environ.get('FEWWORD_PEEK_ON_POINTER', '0') == '1',
            'peek_tier2_lines': _safe_int('FEWWORD_PEEK_TIER2_LINES', 2),
            'peek_tier3_lines': _safe_int('FEWWORD_PEEK_TIER3_LINES', 5),
        },
        'redaction': {
            'enabled': True,
            'patterns': [],
        },
        'aliases': {},
        'deny': {
            'cmds': [],
            'patterns': [],
        },
        'summary': {
            'enabled': True,
            'fallback_max_chars': 120,
        },
    }


# Legacy globals for backwards compatibility (will be overridden by config)
INLINE_MAX = _safe_int('FEWWORD_INLINE_MAX', 512)
PREVIEW_MIN = _safe_int('FEWWORD_PREVIEW_MIN', 4096)
PREVIEW_LINES = _safe_int('FEWWORD_PREVIEW_LINES', 5)
PREVIEW_LINE_MAX = 200
OPEN_CMD = os.environ.get('FEWWORD_OPEN_CMD', '/open')
SHOW_PATH = os.environ.get('FEWWORD_SHOW_PATH', '0') == '1'
VERBOSE_POINTER = os.environ.get('FEWWORD_VERBOSE_POINTER', '0') == '1'
PEEK_ON_POINTER = os.environ.get('FEWWORD_PEEK_ON_POINTER', '0') == '1'
PEEK_TIER2_LINES = _safe_int('FEWWORD_PEEK_TIER2_LINES', 2)
PEEK_TIER3_LINES = _safe_int('FEWWORD_PEEK_TIER3_LINES', 5)

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


def should_skip(command: str, config: Optional[Dict] = None) -> tuple[bool, str]:
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


def should_deny_storage(command: str, config: Dict) -> tuple[bool, str]:
    """
    Check if command matches deny rules (pointer-only, no output file).
    Returns (should_deny, reason).
    """
    deny_config = config.get('deny', {})
    deny_cmds = deny_config.get('cmds', [])
    deny_patterns = deny_config.get('patterns', [])

    if not deny_cmds and not deny_patterns:
        return False, ""

    first_cmd = get_first_command(command)

    # Check deny commands
    if first_cmd in deny_cmds:
        return True, f"deny_cmd: {first_cmd}"

    # Check deny patterns against full command
    for pattern in deny_patterns:
        try:
            if re.search(pattern, command):
                return True, f"deny_pattern: {pattern}"
        except re.error as e:
            # Warn about invalid patterns - user thinks it's working but it's not
            import sys
            print(f"[FewWord] Warning: Invalid deny pattern '{pattern}': {e}", file=sys.stderr)

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
                     timestamp: str, event_id: str, cwd: str, session_id: str,
                     cmd_token: str = '', cmd_group: str = '',
                     config: Optional[Dict] = None, denied: bool = False,
                     deny_reason: str = '') -> str:
    """
    Generate bash wrapper that implements tiered offloading.

    v1.3.5: Tiered logic + compact pointer + smart preview + session tracking + security hardening
            + cmd_token/cmd_group + denied mode

    Tiers:
    1. < INLINE_MAX (512B): Show inline, delete file
    2. INLINE_MAX - PREVIEW_MIN (512B-4KB): Compact pointer only
    3. > PREVIEW_MIN (4KB+): Compact pointer + preview (failures only)

    Denied mode: Pointer only, no output file stored
    """
    # Use config if provided, else fall back to globals
    if config:
        thresholds = config.get('thresholds', {})
        pointer_cfg = config.get('pointer', {})
        inline_max = thresholds.get('inline_max', INLINE_MAX)
        preview_min = thresholds.get('preview_min', PREVIEW_MIN)
        preview_lines = thresholds.get('preview_lines', PREVIEW_LINES)
        open_cmd = pointer_cfg.get('open_cmd', OPEN_CMD)
        show_path = pointer_cfg.get('show_path', SHOW_PATH)
        verbose_pointer = pointer_cfg.get('verbose', VERBOSE_POINTER)
        peek_on_pointer = pointer_cfg.get('peek_on_pointer', PEEK_ON_POINTER)
        peek_tier2 = pointer_cfg.get('peek_tier2_lines', PEEK_TIER2_LINES)
        peek_tier3 = pointer_cfg.get('peek_tier3_lines', PEEK_TIER3_LINES)
    else:
        inline_max = INLINE_MAX
        preview_min = PREVIEW_MIN
        preview_lines = PREVIEW_LINES
        open_cmd = OPEN_CMD
        show_path = SHOW_PATH
        verbose_pointer = VERBOSE_POINTER
        peek_on_pointer = PEEK_ON_POINTER
        peek_tier2 = PEEK_TIER2_LINES
        peek_tier3 = PEEK_TIER3_LINES

    # Escape paths and values for shell (single-quote safe)
    escaped_dir = output_dir.replace("'", "'\"'\"'")
    escaped_cwd = cwd.replace("'", "'\"'\"'")
    escaped_open_cmd = open_cmd.replace("'", "'\"'\"'")
    escaped_session = session_id.replace("'", "'\"'\"'")
    escaped_cmd_token = cmd_token.replace("'", "'\"'\"'")
    escaped_cmd_group = cmd_group.replace("'", "'\"'\"'")
    # Pre-compute expressions to avoid f-string compatibility issues (Python 3.11+)
    denied_str = 'true' if denied else 'false'
    escaped_deny_reason = deny_reason.replace("'", "'\"'\"'") if deny_reason else ""

    wrapper = f'''
set -o pipefail

__fw_dir='{escaped_dir}'
__fw_cwd='{escaped_cwd}'
__fw_cmd='{safe_cmd}'
__fw_ts='{timestamp}'
__fw_id='{event_id}'
__fw_session='{escaped_session}'
__fw_open_cmd='{escaped_open_cmd}'
__fw_cmd_token='{escaped_cmd_token}'
__fw_cmd_group='{escaped_cmd_group}'
__fw_manifest="$__fw_cwd/.fewword/index/tool_outputs.jsonl"
__fw_denied={denied_str}
__fw_deny_reason='{escaped_deny_reason}'

# P1 fix #13: Robust JSON escape helper
# Uses jq -Rs if available (proper JSON escaping), falls back to sed-based escaping
__fw_json_escape() {{
  # Try jq first (most reliable)
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$1" | jq -Rs '.' | sed 's/^"//;s/"$//'
  else
    # Fallback: escape backslash, quote, tab (\\t), newline (\\n), carriage return (\\r)
    printf '%s' "$1" | sed -e 's/\\\\/\\\\\\\\/g' -e 's/"/\\\\"/g' | \\
      awk '{{gsub(/\\t/, "\\\\t"); gsub(/\\r/, "\\\\r"); printf "%s\\\\n", $0}}' | \\
      sed 's/\\\\n$//'
  fi
}}

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

# 3. Rename temp to final (unless denied)
if [ "$__fw_denied" = "true" ]; then
  # Denied mode: delete temp file, show pointer-only message
  rm -f "$__fw_tmp"
  if [ -n "$__fw_deny_reason" ]; then
    echo "[fw $__fw_id] $__fw_cmd e=$__fw_exit (not stored) | $__fw_deny_reason"
  else
    echo "[fw $__fw_id] $__fw_cmd e=$__fw_exit (not stored) | command matched deny list"
  fi
  exit $__fw_exit
fi

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

  # Write manifest entry (append-only) with cmd_token and cmd_group (v1.3.5)
  # Use JSON escape helper for values that could contain special characters
  __fw_now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  __fw_esc_cmd=$(__fw_json_escape "$__fw_cmd")
  __fw_esc_cmd_token=$(__fw_json_escape "$__fw_cmd_token")
  __fw_esc_cmd_group=$(__fw_json_escape "$__fw_cmd_group")
  __fw_esc_path=$(__fw_json_escape "$__fw_rel_path")
  printf '{{"type":"offload","id":"%s","session_id":"%s","created_at":"%s","cmd":"%s","cmd_token":"%s","cmd_group":"%s","exit_code":%d,"bytes":%d,"lines":%d,"path":"%s"}}\\n' \\
    "$__fw_id" "$__fw_session" "$__fw_now" "$__fw_esc_cmd" "$__fw_esc_cmd_token" "$__fw_esc_cmd_group" "$__fw_exit" "$__fw_bytes" "$__fw_lines" "$__fw_esc_path" \\
    >> "$__fw_manifest" 2>/dev/null

  # Create LATEST symlinks (absolute paths) - with Windows fallback
  __fw_abs_out="$(cd "$(dirname "$__fw_out")" && pwd)/$(basename "$__fw_out")"
  ln -sf "$__fw_abs_out" "$__fw_dir/LATEST.txt" 2>/dev/null || echo "$__fw_abs_out" > "$__fw_dir/LATEST.txt"
  ln -sf "$__fw_abs_out" "$__fw_dir/LATEST_$__fw_cmd.txt" 2>/dev/null || echo "$__fw_abs_out" > "$__fw_dir/LATEST_$__fw_cmd.txt"
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
  # TIER 2 - COMPACT: pointer + optional peek preview (failures only)
  echo "$__fw_pointer"
'''

        # Add peek preview for Tier 2 if PEEK_ON_POINTER is enabled
        if PEEK_ON_POINTER:
            wrapper += f'''
  # Show peek preview only for failures (FEWWORD_PEEK_ON_POINTER=1)
  if [ "$__fw_exit" -ne 0 ]; then
    tail -{PEEK_TIER2_LINES} "$__fw_out" | cut -c1-{PREVIEW_LINE_MAX}
  fi
'''

        wrapper += f'''
  # Write manifest entry (append-only) with cmd_token and cmd_group (v1.3.5)
  # Use JSON escape helper for values that could contain special characters
  __fw_now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  __fw_esc_cmd=$(__fw_json_escape "$__fw_cmd")
  __fw_esc_cmd_token=$(__fw_json_escape "$__fw_cmd_token")
  __fw_esc_cmd_group=$(__fw_json_escape "$__fw_cmd_group")
  __fw_esc_path=$(__fw_json_escape "$__fw_rel_path")
  printf '{{"type":"offload","id":"%s","session_id":"%s","created_at":"%s","cmd":"%s","cmd_token":"%s","cmd_group":"%s","exit_code":%d,"bytes":%d,"lines":%d,"path":"%s"}}\\n' \\
    "$__fw_id" "$__fw_session" "$__fw_now" "$__fw_esc_cmd" "$__fw_esc_cmd_token" "$__fw_esc_cmd_group" "$__fw_exit" "$__fw_bytes" "$__fw_lines" "$__fw_esc_path" \\
    >> "$__fw_manifest" 2>/dev/null

  # Create LATEST symlinks (absolute paths) - with Windows fallback
  __fw_abs_out="$(cd "$(dirname "$__fw_out")" && pwd)/$(basename "$__fw_out")"
  ln -sf "$__fw_abs_out" "$__fw_dir/LATEST.txt" 2>/dev/null || echo "$__fw_abs_out" > "$__fw_dir/LATEST.txt"
  ln -sf "$__fw_abs_out" "$__fw_dir/LATEST_$__fw_cmd.txt" 2>/dev/null || echo "$__fw_abs_out" > "$__fw_dir/LATEST_$__fw_cmd.txt"
else
  # TIER 3 - PREVIEW: pointer + smart preview (failures only)
  echo "$__fw_pointer"

  # Show preview only for failures (exit != 0)
  if [ "$__fw_exit" -ne 0 ]; then
    # Plain tail - last {PEEK_TIER3_LINES if PEEK_ON_POINTER else PREVIEW_LINES} lines, truncated to {PREVIEW_LINE_MAX} chars
    tail -{PEEK_TIER3_LINES if PEEK_ON_POINTER else PREVIEW_LINES} "$__fw_out" | cut -c1-{PREVIEW_LINE_MAX}
  fi

  # Write manifest entry (append-only) with cmd_token and cmd_group (v1.3.5)
  # Use JSON escape helper for values that could contain special characters
  __fw_now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  __fw_esc_cmd=$(__fw_json_escape "$__fw_cmd")
  __fw_esc_cmd_token=$(__fw_json_escape "$__fw_cmd_token")
  __fw_esc_cmd_group=$(__fw_json_escape "$__fw_cmd_group")
  __fw_esc_path=$(__fw_json_escape "$__fw_rel_path")
  printf '{{"type":"offload","id":"%s","session_id":"%s","created_at":"%s","cmd":"%s","cmd_token":"%s","cmd_group":"%s","exit_code":%d,"bytes":%d,"lines":%d,"path":"%s"}}\\n' \\
    "$__fw_id" "$__fw_session" "$__fw_now" "$__fw_esc_cmd" "$__fw_esc_cmd_token" "$__fw_esc_cmd_group" "$__fw_exit" "$__fw_bytes" "$__fw_lines" "$__fw_esc_path" \\
    >> "$__fw_manifest" 2>/dev/null

  # Create LATEST symlinks (absolute paths) - with Windows fallback
  __fw_abs_out="$(cd "$(dirname "$__fw_out")" && pwd)/$(basename "$__fw_out")"
  ln -sf "$__fw_abs_out" "$__fw_dir/LATEST.txt" 2>/dev/null || echo "$__fw_abs_out" > "$__fw_dir/LATEST.txt"
  ln -sf "$__fw_abs_out" "$__fw_dir/LATEST_$__fw_cmd.txt" 2>/dev/null || echo "$__fw_abs_out" > "$__fw_dir/LATEST_$__fw_cmd.txt"
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

    # Load config
    config = get_effective_config(cwd)

    # Check if should skip
    skip, reason = should_skip(command, config)
    if skip:
        sys.exit(0)

    # Check if command is denied (pointer-only mode)
    denied, deny_reason = should_deny_storage(command, config)

    # Get session ID from session.json
    session_id = get_session_id(cwd)

    # Generate unique event ID for correlation
    event_id = uuid.uuid4().hex[:8]

    # Generate filename components
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    first_cmd = get_first_command(command)
    safe_cmd = re.sub(r'[^a-zA-Z0-9_-]', '_', first_cmd)[:20]
    output_dir = f"{cwd}/.fewword/scratch/tool_outputs"

    # Extract cmd_token and cmd_group (v1.3.5)
    if HAS_SUMMARY:
        cmd_token = get_cmd_token(command)
        cmd_group = resolve_cmd_group(cmd_token, config.get('aliases', {}))
    else:
        cmd_token = first_cmd
        cmd_group = first_cmd

    # Generate wrapped command (pass config values)
    thresholds = config.get('thresholds', {})
    pointer_config = config.get('pointer', {})
    redaction_config = config.get('redaction', {})

    wrapped = generate_wrapper(
        original_cmd=command,
        output_dir=output_dir,
        safe_cmd=safe_cmd,
        timestamp=timestamp,
        event_id=event_id,
        cwd=cwd,
        session_id=session_id,
        cmd_token=cmd_token,
        cmd_group=cmd_group,
        config=config,
        denied=denied,
        deny_reason=deny_reason
    )

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
