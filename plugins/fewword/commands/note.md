---
description: "Add notes to offloaded outputs"
arguments:
  - name: selector
    description: "Output ID, number, or command name"
    required: true
  - name: note
    description: "Note text to add"
    required: true
---

# Context Note

Add notes to offloaded outputs for documentation and context.

## Usage

```bash
/note A1B2C3D4 "Failed deploy, rolled back at 3pm"
/note 1 "Root cause: missing env var"
/note pytest "Regression introduced in commit abc123"

# View notes for an output
/note A1B2C3D4 --view
```

## Implementation

Run this Python script to manage notes:

```python
#!/usr/bin/env python
"""Context Note - Add notes to outputs."""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

def get_cwd():
    return os.environ.get('FEWWORD_CWD', os.getcwd())

def resolve_id(selector, cwd):
    """Resolve selector to hex ID."""
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'
    index_path = Path(cwd) / '.fewword' / 'index' / '.recent_index'

    # Number resolution
    if selector.isdigit():
        # P2 fix: Check file exists before opening to avoid unnecessary exception handling
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

def get_notes(hex_id, cwd):
    """Get existing notes for an output."""
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'
    notes = []

    try:
        with open(manifest_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get('type') == 'note' and entry.get('id', '').upper() == hex_id.upper():
                        notes.append({
                            'note': entry.get('note', ''),
                            'noted_at': entry.get('noted_at', '')
                        })
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except (FileNotFoundError, IOError):
        pass

    return notes

def add_note(hex_id, note, cwd):
    """Add a note to an output."""
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'

    # Ensure directory exists (P0 fix: prevents FileNotFoundError on fresh installs)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        'type': 'note',
        'id': hex_id.upper(),
        'note': note,
        'noted_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    }

    with open(manifest_path, 'a') as f:
        f.write(json.dumps(entry) + '\n')

def format_age(iso_timestamp):
    """Format timestamp as human-readable age."""
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
    except (ValueError, TypeError, AttributeError):
        return "?"

def main():
    args = sys.argv[1:]
    cwd = get_cwd()

    if len(args) < 1:
        print("Usage:")
        print("  /note <selector> \"<note>\"  # Add note")
        print("  /note <selector> --view     # View notes")
        sys.exit(1)

    selector = args[0]
    hex_id = resolve_id(selector, cwd)

    if not hex_id:
        print(f"Error: Could not resolve '{selector}' to an output ID.")
        print("Use /recent to see available outputs.")
        sys.exit(1)

    # View mode
    if '--view' in args:
        notes = get_notes(hex_id, cwd)
        if notes:
            print(f"Notes for [{hex_id}]:")
            print("")
            for i, n in enumerate(notes, 1):
                age = format_age(n['noted_at'])
                print(f"  {i}. ({age}) {n['note']}")
        else:
            print(f"No notes for [{hex_id}]")
        sys.exit(0)

    # Add mode
    note_parts = [a for a in args[1:] if a != '--view']
    note = ' '.join(note_parts).strip()

    # Handle quoted strings
    if note.startswith('"') and note.endswith('"'):
        note = note[1:-1]
    elif note.startswith("'") and note.endswith("'"):
        note = note[1:-1]

    if not note:
        print("Error: No note provided.")
        print('Usage: /note <selector> "Your note here"')
        sys.exit(1)

    # Validate note length
    if len(note) > 500:
        print(f"Error: Note too long ({len(note)} chars). Max 500 chars.")
        sys.exit(1)

    add_note(hex_id, note, cwd)
    print(f"Added note to [{hex_id}]: {note[:60]}{'...' if len(note) > 60 else ''}")

if __name__ == '__main__':
    main()
```

## Output Example

### Adding a note
```
> /note A1B2 "Failed deploy, rolled back at 3pm"
Added note to [A1B2C3D4]: Failed deploy, rolled back at 3pm
```

### Viewing notes
```
> /note A1B2 --view
Notes for [A1B2C3D4]:

  1. (2h ago) Failed deploy, rolled back at 3pm
  2. (1h ago) Root cause identified: missing DB_URL env var
```

## Integration with /open

Notes appear when retrieving output:

```
───────────────────────────────────────
[fw A1B2] pytest e=1 45K 882L (2h ago)
───────────────────────────────────────
Notes:
  - (2h ago) Failed deploy, rolled back at 3pm
  - (1h ago) Root cause identified: missing DB_URL env var
HEAD:
  ...
```

## Notes

- Notes are stored as separate entries in manifest (append-only)
- Max note length: 500 characters
- Multiple notes can be added to the same output
- Notes persist across sessions and survive cleanup
- Notes appear when viewing outputs with `/open`
- **Quote handling limitation**: Quotes around notes are stripped only when they match at start and end. A note like `"foo bar'` will retain both quotes.
