---
description: "Compare two command outputs with intelligent diff"
arguments:
  - name: selector1
    description: "First output (ID, number, or command name)"
    required: false
  - name: selector2
    description: "Second output (ID, --prev, or omit for latest)"
    required: false
---

# Context Diff

Compare two command outputs with noise stripping and summary view.

## Usage

```bash
/context-diff pytest              # Diff last 2 pytest runs
/context-diff A1B2 --prev         # Diff A1B2 vs previous of same cmd
/context-diff A1B2 C3D4           # Diff two specific outputs
/context-diff pytest --last 3     # Diff last 3 runs (multi-diff)

Output flags:
  --stat                          # Summary only (DEFAULT)
  --full                          # Show actual diff (200-line cap)
  --ignore-timing                 # Extra timestamp stripping
```

## Implementation

Run this Python script to perform the diff:

```python
#!/usr/bin/env python3
"""Context Diff - Compare command outputs with noise stripping."""

import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from difflib import unified_diff

def get_cwd():
    """Get current working directory with path traversal protection."""
    cwd = os.environ.get('FEWWORD_CWD', os.getcwd())
    # P0 fix: Resolve and validate path to prevent ../escape
    resolved = os.path.realpath(os.path.abspath(cwd))
    # Ensure the path exists and is a directory
    if not os.path.isdir(resolved):
        # Fall back to actual cwd if FEWWORD_CWD is invalid
        resolved = os.path.realpath(os.getcwd())
    return resolved

def validate_path_within_cwd(path_str, cwd):
    """P0 fix #16: Validate that a path is within cwd to prevent path traversal."""
    resolved_cwd = os.path.realpath(os.path.abspath(cwd))
    resolved_path = os.path.realpath(os.path.abspath(os.path.join(cwd, str(path_str))))
    # Check that resolved path starts with cwd (is a descendant)
    try:
        # Python 3.9+
        return Path(resolved_path).is_relative_to(resolved_cwd)
    except AttributeError:
        # Python 3.8 fallback
        return resolved_path.startswith(resolved_cwd + os.sep) or resolved_path == resolved_cwd

def calculate_age(iso_timestamp):
    """Convert ISO timestamp to human-readable age."""
    try:
        ts = iso_timestamp.replace('Z', '+00:00')
        created = datetime.fromisoformat(ts)
        now = datetime.now(timezone.utc)
        diff = int((now - created).total_seconds())
        if diff < 60:
            return f"{diff}s ago"
        elif diff < 3600:
            return f"{diff // 60}m ago"
        elif diff < 86400:
            return f"{diff // 3600}h ago"
        else:
            return f"{diff // 86400}d ago"
    except (ValueError, TypeError, OverflowError):
        return "?"

def get_manifest_entries(cwd, cmd_filter=None, limit=100):
    """Get recent manifest entries, optionally filtered by command."""
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'
    entries = []

    if not manifest_path.exists():
        return entries

    with open(manifest_path, 'r') as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get('type') == 'offload':
                    if cmd_filter is None or entry.get('cmd') == cmd_filter or entry.get('cmd_group') == cmd_filter:
                        entries.append(entry)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

    # Return most recent first
    return list(reversed(entries))[:limit]

def resolve_selector(selector, cwd, cmd_hint=None):
    """Resolve selector to manifest entry."""
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'
    index_path = Path(cwd) / '.fewword' / 'index' / '.recent_index'

    if not selector:
        return None

    # Number resolution
    if selector.isdigit():
        num = int(selector)
        try:
            with open(index_path, 'r') as f:
                lines = f.readlines()
            if 1 <= num <= len(lines):
                parts = lines[num - 1].strip().split(':')
                if len(parts) >= 2:
                    selector = parts[1]
        except (FileNotFoundError, IndexError, ValueError, IOError):
            pass

    # Hex ID resolution
    if len(selector) == 8 and all(c in '0123456789ABCDEFabcdef' for c in selector):
        hex_id = selector.upper()
        entries = get_manifest_entries(cwd)
        for entry in entries:
            if entry.get('id', '').upper() == hex_id:
                return entry

    # Command name - get latest
    entries = get_manifest_entries(cwd, cmd_filter=selector, limit=1)
    if entries:
        return entries[0]

    return None

def strip_noise(content, ignore_timing=False):
    """Strip noise from output for cleaner diff."""
    lines = content.split('\n')
    cleaned = []

    for line in lines:
        # Strip ANSI color codes
        line = re.sub(r'\x1b\[[0-9;]*m', '', line)

        # Normalize paths (convert absolute to relative)
        line = re.sub(r'/[^\s:]+/([^/\s:]+)', r'\1', line)

        # Strip timestamps if requested
        if ignore_timing:
            # Common timestamp patterns
            line = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*Z?', '[TIME]', line)
            line = re.sub(r'\d{2}:\d{2}:\d{2}[.\d]*', '[TIME]', line)
            line = re.sub(r'\d+\.\d+s', '[DURATION]', line)

        # Collapse repeated whitespace
        line = re.sub(r'  +', ' ', line)

        cleaned.append(line)

    return '\n'.join(cleaned)

def compute_stat_summary(old_lines, new_lines):
    """Compute diff statistics summary."""
    old_set = set(old_lines)
    new_set = set(new_lines)

    added = len(new_set - old_set)
    removed = len(old_set - new_set)
    unchanged = len(old_set & new_set)

    return added, removed, unchanged

def main():
    args = sys.argv[1:]
    cwd = get_cwd()

    # Parse flags
    show_full = '--full' in args
    show_stat = '--stat' in args or not show_full  # stat is default
    ignore_timing = '--ignore-timing' in args
    use_prev = '--prev' in args
    last_n = 2
    MAX_LAST = 100  # P2 fix: cap --last to prevent memory issues

    # Parse --last N
    for i, arg in enumerate(args):
        if arg == '--last' and i + 1 < len(args):
            try:
                last_n = min(int(args[i + 1]), MAX_LAST)  # P2 fix: cap value
            except (ValueError, TypeError):
                pass

    # P2 fix: Proper selector parsing using enumerate instead of buggy args.index
    skip_next = False
    selectors = []
    for i, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg == '--last':
            skip_next = True
            continue
        if arg.startswith('--'):
            continue
        selectors.append(arg)

    # Resolve entries
    entry1 = None
    entry2 = None

    if len(selectors) >= 2:
        # Two explicit selectors
        entry1 = resolve_selector(selectors[0], cwd)
        entry2 = resolve_selector(selectors[1], cwd)
    elif len(selectors) == 1:
        if use_prev:
            # selector --prev: compare with previous of same command
            entry2 = resolve_selector(selectors[0], cwd)
            if entry2:
                cmd = entry2.get('cmd_group') or entry2.get('cmd')
                entries = get_manifest_entries(cwd, cmd_filter=cmd)
                # Find the entry and get the one before it
                for i, e in enumerate(entries):
                    if e.get('id') == entry2.get('id') and i + 1 < len(entries):
                        entry1 = entries[i + 1]
                        break
        else:
            # Single command name: get last 2 runs
            cmd = selectors[0]
            entries = get_manifest_entries(cwd, cmd_filter=cmd, limit=last_n)
            if len(entries) >= 2:
                entry2 = entries[0]  # newest
                entry1 = entries[1]  # second newest
            elif len(entries) == 1:
                print(f"Only 1 output found for '{cmd}'. Need at least 2 to diff.")
                sys.exit(1)
            else:
                print(f"No outputs found for '{cmd}'.")
                sys.exit(1)
    else:
        print("Usage:")
        print("  /context-diff pytest              # Diff last 2 pytest runs")
        print("  /context-diff A1B2 --prev         # Diff A1B2 vs previous")
        print("  /context-diff A1B2 C3D4           # Diff two specific outputs")
        print("")
        print("Flags: --stat (default), --full, --ignore-timing")
        sys.exit(1)

    if not entry1 or not entry2:
        print("Error: Could not resolve both outputs to diff.")
        print("Use /context-recent to see available outputs.")
        sys.exit(1)

    # Read file contents
    path1_str = entry1.get('path', '')
    path2_str = entry2.get('path', '')

    # P0 fix #16: Validate paths are within cwd to prevent path traversal
    if not validate_path_within_cwd(path1_str, cwd):
        print(f"Error: Path for older output [{entry1.get('id')}] escapes working directory")
        print(f"  Rejected path: {path1_str}")
        sys.exit(1)

    if not validate_path_within_cwd(path2_str, cwd):
        print(f"Error: Path for newer output [{entry2.get('id')}] escapes working directory")
        print(f"  Rejected path: {path2_str}")
        sys.exit(1)

    path1 = Path(cwd) / path1_str
    path2 = Path(cwd) / path2_str

    if not path1.exists():
        print(f"Error: File not found for older output [{entry1.get('id')}]")
        print(f"  Was at: {path1}")
        sys.exit(1)

    if not path2.exists():
        print(f"Error: File not found for newer output [{entry2.get('id')}]")
        print(f"  Was at: {path2}")
        sys.exit(1)

    # P2 fix #17: Handle read exceptions
    try:
        content1 = path1.read_text(encoding='utf-8', errors='replace')
    except (PermissionError, IsADirectoryError, OSError) as e:
        print(f"Error: Could not read older output [{entry1.get('id')}]: {e}")
        print(f"  Path: {path1}")
        sys.exit(1)

    try:
        content2 = path2.read_text(encoding='utf-8', errors='replace')
    except (PermissionError, IsADirectoryError, OSError) as e:
        print(f"Error: Could not read newer output [{entry2.get('id')}]: {e}")
        print(f"  Path: {path2}")
        sys.exit(1)

    # Strip noise
    clean1 = strip_noise(content1, ignore_timing)
    clean2 = strip_noise(content2, ignore_timing)

    lines1 = clean1.split('\n')
    lines2 = clean2.split('\n')

    # Print header
    cmd1 = entry1.get('cmd', '?')
    cmd2 = entry2.get('cmd', '?')
    exit1 = entry1.get('exit_code', '?')
    exit2 = entry2.get('exit_code', '?')
    age1 = calculate_age(entry1.get('created_at', ''))
    age2 = calculate_age(entry2.get('created_at', ''))

    print("Comparing outputs:")
    print(f"  Older: [{entry1.get('id')}] {cmd1} e={exit1} ({age1})")
    print(f"  Newer: [{entry2.get('id')}] {cmd2} e={exit2} ({age2})")
    print("")

    # Compute statistics
    added, removed, unchanged = compute_stat_summary(lines1, lines2)

    if show_stat:
        # Summary mode (default)
        print(f"Changes: +{added} lines, -{removed} lines, {unchanged} unchanged")

        # Show exit code change if different
        if exit1 != exit2:
            if exit2 == 0:
                print(f"Status: FIXED (exit {exit1} -> {exit2})")
            elif exit1 == 0:
                print(f"Status: REGRESSED (exit {exit1} -> {exit2})")
            else:
                print(f"Status: exit {exit1} -> {exit2}")

        if added == 0 and removed == 0:
            print("Outputs are identical (after noise stripping).")
        else:
            print("")
            print("Use --full to see actual diff (capped at 200 lines)")

    if show_full:
        # Full diff mode
        diff = list(unified_diff(
            lines1, lines2,
            fromfile=f"{entry1.get('id')} ({age1})",
            tofile=f"{entry2.get('id')} ({age2})",
            lineterm=''
        ))

        if not diff:
            print("No differences found (after noise stripping).")
        else:
            # Cap at 200 lines
            max_lines = 200
            for i, line in enumerate(diff[:max_lines]):
                print(line)

            if len(diff) > max_lines:
                print(f"")
                print(f"... ({len(diff) - max_lines} more lines truncated)")
                print(f"Use /context-open {entry1.get('id')} and /context-open {entry2.get('id')} to see full outputs")

if __name__ == '__main__':
    main()
```

## Output Example

### --stat mode (default)
```
Comparing outputs:
  Older: [C3D4E5F6] pytest e=0 (2h ago)
  Newer: [A1B2C3D4] pytest e=1 (5m ago)

Changes: +8 lines, -2 lines, 45 unchanged
Status: REGRESSED (exit 0 -> 1)

Use --full to see actual diff (capped at 200 lines)
```

### --full mode
```
Comparing outputs:
  Older: [C3D4E5F6] pytest e=0 (2h ago)
  Newer: [A1B2C3D4] pytest e=1 (5m ago)

--- C3D4E5F6 (2h ago)
+++ A1B2C3D4 (5m ago)
@@ -42,3 +42,8 @@
 test_login.py::test_valid_login PASSED
-test_login.py::test_invalid_login PASSED
+test_login.py::test_invalid_login FAILED
+    AssertionError: expected 401, got 500
```

## Notes

- Default is `--stat` (summary-only, context-safe ~50 tokens)
- `--full` shows unified diff capped at 200 lines
- Noise stripping removes: ANSI colors, absolute paths, repeated whitespace
- `--ignore-timing` also strips timestamps and durations
- Compares by cmd_group if available (so npm/yarn/pnpm can be compared)
