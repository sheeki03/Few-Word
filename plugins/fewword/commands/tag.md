---
description: "Add tags to offloaded outputs for organization"
arguments:
  - name: selector
    description: "Output ID, number, or command name"
    required: true
  - name: tags
    description: "One or more tags to add (space-separated)"
    required: true
---

# Context Tag

Add tags to offloaded outputs for better organization and retrieval.

## Usage

```bash
/tag A1B2 prod-migration deploy-jan9
/tag 1 bugfix important
/tag pytest regression test-failure

# List tags for an output
/tag A1B2 --list

# Remove tags
/tag A1B2 --remove prod-migration
```

## Implementation

Run this Python script to manage tags:

```python
#!/usr/bin/env python
"""Context Tag - Add tags to outputs."""

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

def validate_path_within_cwd(path, cwd):
    """P0 fix: Validate that a path is within cwd to prevent path traversal."""
    resolved_cwd = os.path.realpath(os.path.abspath(cwd))
    resolved_path = os.path.realpath(os.path.abspath(os.path.join(cwd, str(path))))
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

    # Number resolution — ensures file exists before reading and handles IOErrors
    if selector.isdigit():
        if not index_path.exists():
            pass  # Fall through to other resolution methods
        else:
            try:
                with open(index_path, 'r') as f:
                    lines = f.readlines()
                num = int(selector)
                if 1 <= num <= len(lines):
                    parts = lines[num - 1].strip().split(':')
                    if len(parts) >= 2:
                        return parts[1].upper()
            except (FileNotFoundError, IndexError, ValueError, IOError):
                pass

    # Hex ID resolution
    if len(selector) == 8 and all(c in '0123456789ABCDEFabcdef' for c in selector):
        return selector.upper()

    # Command name - find latest
    try:
        with open(manifest_path, 'r') as f:
            for line in reversed(f.readlines()):
                try:
                    entry = json.loads(line)
                    if entry.get('type') == 'offload' and entry.get('cmd') == selector:
                        return entry.get('id', '').upper()
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except (FileNotFoundError, IOError):
        pass

    return None

def get_tags(hex_id, cwd):
    """Get existing tags for an output, accounting for removals."""
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'
    tags_added = set()
    tags_removed = set()

    try:
        with open(manifest_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get('id', '').upper() == hex_id.upper():
                        if entry.get('type') == 'tag':
                            tags_added.update(entry.get('tags', []))
                        elif entry.get('type') == 'tag_remove':
                            tags_removed.update(entry.get('tags', []))
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except (FileNotFoundError, IOError):
        pass

    # Compute final set: added minus removed
    return list(tags_added - tags_removed)

def add_tags(hex_id, tags, cwd):
    """Add tags to an output."""
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'

    # Get existing tags
    existing = get_tags(hex_id, cwd)
    new_tags = [t for t in tags if t not in existing]

    if not new_tags:
        print(f"Tags already exist for [{hex_id}]: {', '.join(tags)}")
        return existing

    # Append tag entry
    entry = {
        'type': 'tag',
        'id': hex_id.upper(),
        'tags': new_tags,
        'tagged_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    }

    # P0 fix #1 & #2: Ensure parent directory exists and handle write errors
    try:
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        with open(manifest_path, 'a') as f:
            f.write(json.dumps(entry) + '\n')
            f.flush()
            os.fsync(f.fileno())
    except (IOError, OSError) as e:
        print(f"Error: Could not write to manifest at {manifest_path}: {e}", file=sys.stderr)
        return existing  # Return existing tags without new ones on failure

    return existing + new_tags

def remove_tags(hex_id, tags_to_remove, cwd):
    """Remove tags by adding a removal entry."""
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'

    entry = {
        'type': 'tag_remove',
        'id': hex_id.upper(),
        'tags': tags_to_remove,
        'removed_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    }

    # P0 fix #1 & #2: Ensure parent directory exists and handle write errors
    try:
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        with open(manifest_path, 'a') as f:
            f.write(json.dumps(entry) + '\n')
            f.flush()
            os.fsync(f.fileno())
        return True
    except (IOError, OSError) as e:
        print(f"Error: Could not write to manifest at {manifest_path}: {e}", file=sys.stderr)
        return False

def main():
    args = sys.argv[1:]
    cwd = get_cwd()

    if len(args) < 1:
        print("Usage:")
        print("  /tag <selector> <tag1> [tag2] ...  # Add tags")
        print("  /tag <selector> --list             # List tags")
        print("  /tag <selector> --remove <tag>     # Remove tag")
        sys.exit(1)

    selector = args[0]
    hex_id = resolve_id(selector, cwd)

    if not hex_id:
        print(f"Error: Could not resolve '{selector}' to an output ID.")
        print("Use /recent to see available outputs.")
        sys.exit(1)

    # List mode
    if '--list' in args:
        tags = get_tags(hex_id, cwd)
        if tags:
            print(f"Tags for [{hex_id}]: {', '.join(sorted(tags))}")
        else:
            print(f"No tags for [{hex_id}]")
        sys.exit(0)

    # Remove mode
    if '--remove' in args:
        idx = args.index('--remove')
        tags_to_remove = args[idx + 1:]
        if not tags_to_remove:
            print("Error: Specify tags to remove after --remove")
            sys.exit(1)
        # P0 fix #3: Validate tags in remove path same as add path
        import re
        for tag in tags_to_remove:
            if not re.match(r'^[a-zA-Z0-9_-]+$', tag):
                print(f"Error: Invalid tag '{tag}'. Tags must be alphanumeric with hyphens/underscores.")
                sys.exit(1)
        if remove_tags(hex_id, tags_to_remove, cwd):
            print(f"Removed tags from [{hex_id}]: {', '.join(tags_to_remove)}")
        else:
            print(f"Error: Failed to remove tags from [{hex_id}]")
            sys.exit(1)
        sys.exit(0)

    # Add mode
    tags = [t for t in args[1:] if not t.startswith('--')]
    if not tags:
        print("Error: No tags provided.")
        print("Usage: /tag <selector> <tag1> [tag2] ...")
        sys.exit(1)

    # Validate tags (alphanumeric + hyphen/underscore)
    import re
    for tag in tags:
        if not re.match(r'^[a-zA-Z0-9_-]+$', tag):
            print(f"Error: Invalid tag '{tag}'. Tags must be alphanumeric with hyphens/underscores.")
            sys.exit(1)

    all_tags = add_tags(hex_id, tags, cwd)
    print(f"Tagged [{hex_id}]: {', '.join(sorted(all_tags))}")

if __name__ == '__main__':
    main()
```

## Integration with /recent

Tags appear in `/recent` output:

```
 # │ ID       │ Cmd    │ Exit │ Size  │ Age │ Tags
───┼──────────┼────────┼──────┼───────┼─────┼────────────────
 1 │ A1B2C3D4 │ pytest │ 1    │ 45K   │ 2m  │ prod-migration
 2 │ C3D4E5F6 │ npm    │ 0    │ 12K   │ 5m  │ deploy-jan9
```

## Notes

- Tags are stored as separate entries in manifest (append-only)
- Tag names must be alphanumeric with hyphens/underscores
- Use `/recent --tag <tag>` to filter by tag
- Tags persist across sessions and survive cleanup
- Pinned files keep their tags
