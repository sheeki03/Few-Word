---
description: "Unpin a previously pinned output"
arguments:
  - name: selector
    description: "Output ID, number, or command name to unpin"
    required: true
---

# Context Unpin

Remove a pinned output, moving it back to scratch for normal TTL cleanup.

## Usage

```bash
/context-unpin A1B2               # By hex ID
/context-unpin 1                  # By number from /context-recent
/context-unpin pytest             # Latest pinned pytest output
```

## Implementation

Run this Python script to unpin:

```python
#!/usr/bin/env python3
"""Context Unpin - Remove pin from output."""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

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
    """P0 fix #26: Validate that a path is within cwd to prevent path traversal."""
    resolved_cwd = os.path.realpath(os.path.abspath(cwd))
    resolved_path = os.path.realpath(os.path.abspath(os.path.join(cwd, str(path_str))))
    # Check that resolved path starts with cwd (is a descendant)
    try:
        # Python 3.9+
        return Path(resolved_path).is_relative_to(resolved_cwd)
    except AttributeError:
        # Python 3.8 fallback
        return resolved_path.startswith(resolved_cwd + os.sep) or resolved_path == resolved_cwd

def resolve_id(selector, cwd):
    """Resolve selector to hex ID."""
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'
    index_path = Path(cwd) / '.fewword' / 'index' / '.recent_index'

    # Number resolution
    if selector.isdigit():
        try:
            with open(index_path, 'r') as f:
                lines = f.readlines()
            num = int(selector)
            if 1 <= num <= len(lines):
                parts = lines[num - 1].strip().split(':')
                if len(parts) >= 2:
                    return parts[1].upper()
        except (FileNotFoundError, IndexError, ValueError):
            pass

    # Hex ID resolution
    if len(selector) == 8 and all(c in '0123456789ABCDEFabcdef' for c in selector):
        return selector.upper()

    # Command name - find latest pinned
    try:
        with open(manifest_path, 'r') as f:
            lines = f.readlines()

        # Find latest pinned output for this command
        for line in reversed(lines):
            try:
                entry = json.loads(line)
                if entry.get('type') == 'offload' and entry.get('cmd') == selector:
                    # Check if this is pinned
                    hex_id = entry.get('id', '').upper()
                    if is_pinned(hex_id, cwd):
                        return hex_id
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
    except (FileNotFoundError, IOError):
        pass

    return None

def is_pinned(hex_id, cwd):
    """Check if output is pinned."""
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'

    pinned = False
    unpinned = False

    try:
        with open(manifest_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get('id', '').upper() == hex_id:
                        if entry.get('type') == 'pin':
                            pinned = True
                        elif entry.get('type') == 'unpin':
                            unpinned = True
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except (FileNotFoundError, IOError):
        pass

    return pinned and not unpinned

def get_pinned_path(hex_id, cwd):
    """Get path to pinned file."""
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'

    try:
        with open(manifest_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get('type') == 'pin' and entry.get('id', '').upper() == hex_id:
                        return entry.get('pinned_path')
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except (FileNotFoundError, IOError):
        pass

    return None

def unpin_output(hex_id, cwd):
    """Unpin an output by recording unpin entry in manifest."""
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'

    # Record unpin
    unpin_entry = {
        'type': 'unpin',
        'id': hex_id.upper(),
        'unpinned_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    }

    # P2 fix: Handle manifest write errors gracefully with atomic-ish write
    try:
        with open(manifest_path, 'a') as f:
            f.write(json.dumps(unpin_entry) + '\n')
            f.flush()  # P2 fix: Ensure data reaches OS buffer
            os.fsync(f.fileno())  # P2 fix: Ensure data reaches disk
    except (IOError, OSError) as e:
        print(f"Warning: Could not write to manifest: {e}", file=sys.stderr)
        return False

    # Optionally delete pinned file (leave for cleanup to handle)
    pinned_path = get_pinned_path(hex_id, cwd)
    if pinned_path:
        # P0 fix #26: Validate path is within cwd before deletion to prevent path traversal
        if not validate_path_within_cwd(pinned_path, cwd):
            print(f"Warning: Skipping deletion - path escapes working directory: {pinned_path}", file=sys.stderr)
        else:
            full_path = Path(cwd) / pinned_path
            if full_path.exists():
                try:
                    full_path.unlink()
                except (OSError, PermissionError) as e:
                    print(f"Warning: Could not delete pinned file: {e}", file=sys.stderr)

    return True

def main():
    args = sys.argv[1:]
    cwd = get_cwd()

    if not args:
        print("Usage: /context-unpin <selector>")
        print("")
        print("Examples:")
        print("  /context-unpin A1B2       # By hex ID")
        print("  /context-unpin 1          # By number from /context-recent")
        print("  /context-unpin pytest     # Latest pinned pytest output")
        sys.exit(1)

    selector = args[0]
    hex_id = resolve_id(selector, cwd)

    if not hex_id:
        print(f"Error: Could not resolve '{selector}' to an output ID.")
        print("Use /context-recent to see available outputs.")
        sys.exit(1)

    if not is_pinned(hex_id, cwd):
        print(f"[{hex_id}] is not currently pinned.")
        sys.exit(0)

    if unpin_output(hex_id, cwd):
        print(f"Unpinned [{hex_id}]")
        print("Output will now follow normal TTL cleanup (24h success, 48h failure).")
    else:
        print(f"Error: Failed to unpin [{hex_id}]")
        sys.exit(1)

if __name__ == '__main__':
    main()
```

## Notes

- Unpinned outputs return to normal TTL cleanup schedule
- The pinned copy in memory/pinned is deleted
- The original in scratch/ may still exist (until TTL expires)
- Use `/context-recent --pinned` to see currently pinned outputs
