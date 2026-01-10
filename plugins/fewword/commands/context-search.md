---
description: "Search through offloaded outputs with hard caps"
arguments:
  - name: pattern
    description: "The search pattern (regex supported)"
    required: true
---

# Context Search

Search across all offloaded outputs with manifest integration and hard caps to prevent context explosion.

## Usage

```bash
/context-search "AssertionError"
/context-search "connection refused" --cmd pytest
/context-search "error" --since 24h
/context-search "FAILED" --pinned-only
/context-search "pattern" --full          # Bypass line cap (still respects file/byte caps)
```

## Hard Caps (Context Bomb Prevention)

| Limit | Value | Purpose |
|-------|-------|---------|
| Max files scanned | 50 | Prevent full history scan |
| Max bytes per file | 2MB | Skip huge outputs |
| Max output lines | 50 | Keep context reasonable |
| Max matches shown | 10 files | Prevent flood |

## Implementation

Run this Python script to search:

```python
#!/usr/bin/env python3
"""Context Search - Search offloaded outputs with hard caps."""

import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

def get_cwd():
    return os.environ.get('FEWWORD_CWD', os.getcwd())

def parse_duration(duration_str):
    """Parse duration string like '24h', '7d' to timedelta."""
    if not duration_str:
        return None
    if duration_str.endswith('h'):
        return timedelta(hours=int(duration_str[:-1]))
    elif duration_str.endswith('d'):
        return timedelta(days=int(duration_str[:-1]))
    elif duration_str.endswith('m'):
        return timedelta(minutes=int(duration_str[:-1]))
    return None

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
    except (ValueError, TypeError, AttributeError):
        return "?"

def get_pinned_ids(cwd):
    """Get set of pinned output IDs."""
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'
    pinned = set()

    try:
        with open(manifest_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get('type') == 'pin':
                        pinned.add(entry.get('id', '').upper())
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except (FileNotFoundError, IOError):
        pass

    return pinned

def get_searchable_entries(cwd, cmd_filter=None, since=None, pinned_only=False, limit=50):
    """Get entries eligible for search, respecting hard caps."""
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'
    entries = []

    if not manifest_path.exists():
        return entries

    now = datetime.now(timezone.utc)
    pinned_ids = get_pinned_ids(cwd) if pinned_only else set()

    with open(manifest_path, 'r') as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get('type') != 'offload':
                    continue

                # Filter by command
                if cmd_filter:
                    cmd = entry.get('cmd_group') or entry.get('cmd')
                    if cmd != cmd_filter:
                        continue

                # Filter by time
                if since:
                    try:
                        ts = entry.get('created_at', '').replace('Z', '+00:00')
                        created = datetime.fromisoformat(ts)
                        if now - created > since:
                            continue
                    except (ValueError, TypeError, AttributeError):
                        pass

                # Filter pinned only
                if pinned_only and entry.get('id', '').upper() not in pinned_ids:
                    continue

                entries.append(entry)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

    # Return most recent first, limited
    return list(reversed(entries))[:limit]

def search_file(path, pattern, max_bytes=2*1024*1024, max_matches=20):
    """Search a file for pattern, respecting size limit."""
    try:
        # Check file size first
        if path.stat().st_size > max_bytes:
            return None, "skipped (>2MB)"

        content = path.read_text(errors='replace')
        matches = []

        for i, line in enumerate(content.split('\n'), 1):
            if re.search(pattern, line, re.IGNORECASE):
                # Truncate long lines
                if len(line) > 200:
                    line = line[:200] + '...'
                matches.append((i, line))
                if len(matches) >= max_matches:
                    break

        return matches, None
    except Exception as e:
        return None, str(e)

def main():
    args = sys.argv[1:]
    cwd = get_cwd()

    # Parse arguments
    pattern = None
    cmd_filter = None
    since = None
    pinned_only = '--pinned-only' in args
    full_mode = '--full' in args

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == '--cmd' and i + 1 < len(args):
            cmd_filter = args[i + 1]
            i += 2
        elif arg == '--since' and i + 1 < len(args):
            since = parse_duration(args[i + 1])
            i += 2
        elif arg.startswith('--'):
            i += 1
        else:
            if pattern is None:
                pattern = arg
            i += 1

    if not pattern:
        print("Usage: /context-search <pattern> [options]")
        print("")
        print("Options:")
        print("  --cmd <name>      Filter by command (e.g., pytest)")
        print("  --since <duration> Filter by time (e.g., 24h, 7d)")
        print("  --pinned-only     Search only pinned outputs")
        print("  --full            Show more matches (still capped)")
        sys.exit(1)

    # Validate pattern is valid regex
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        print(f"Error: Invalid regex pattern: {e}")
        sys.exit(1)

    # Hard caps
    MAX_FILES = 50
    MAX_OUTPUT_LINES = 50 if not full_mode else 200
    MAX_RESULTS_FILES = 10 if not full_mode else 25

    # Get searchable entries
    entries = get_searchable_entries(cwd, cmd_filter, since, pinned_only, limit=MAX_FILES)

    if not entries:
        filter_desc = []
        if cmd_filter:
            filter_desc.append(f"cmd={cmd_filter}")
        if since:
            filter_desc.append(f"since specified")
        if pinned_only:
            filter_desc.append("pinned-only")

        print(f"No outputs found to search" + (f" ({', '.join(filter_desc)})" if filter_desc else "") + ".")
        sys.exit(0)

    # Search each file
    results = []
    files_scanned = 0
    files_skipped = 0
    total_matches = 0

    for entry in entries:
        path = Path(cwd) / entry.get('path', '')
        if not path.exists():
            continue

        files_scanned += 1
        matches, error = search_file(path, pattern)

        if error:
            files_skipped += 1
            continue

        if matches:
            results.append({
                'entry': entry,
                'matches': matches,
                'path': str(path)
            })
            total_matches += len(matches)

        if len(results) >= MAX_RESULTS_FILES:
            break

    # Output
    print(f'Searching for: "{pattern}"')
    if cmd_filter or since or pinned_only:
        filters = []
        if cmd_filter:
            filters.append(f"cmd={cmd_filter}")
        if since:
            filters.append(f"since={args[args.index('--since')+1]}")
        if pinned_only:
            filters.append("pinned-only")
        print(f"Filters: {', '.join(filters)}")
    print("")

    if not results:
        print("No matches found.")
        print(f"Scanned {files_scanned} files" + (f", skipped {files_skipped}" if files_skipped else "") + ".")
        sys.exit(0)

    print(f"Found {total_matches} matches across {len(results)} outputs:")
    print("")

    output_lines = 0
    for result in results:
        entry = result['entry']
        matches = result['matches']

        entry_id = entry.get('id', '????')[:8]
        cmd = entry.get('cmd_group') or entry.get('cmd', '?')
        exit_code = entry.get('exit_code', '?')
        age = calculate_age(entry.get('created_at', ''))

        print(f"[{entry_id}] {cmd} e={exit_code} ({age}) - {len(matches)} matches")

        # Show matches (capped)
        matches_shown = 0
        for line_num, line_content in matches:
            if output_lines >= MAX_OUTPUT_LINES:
                break
            print(f"  {line_num}: {line_content}")
            output_lines += 1
            matches_shown += 1

        if matches_shown < len(matches):
            remaining = len(matches) - matches_shown
            print(f"  ...{remaining} more matches (use --full)")

        print("")

        if output_lines >= MAX_OUTPUT_LINES:
            break

    # Summary
    print("-" * 50)
    summary_parts = [f"{total_matches} matches in {len(results)} files"]
    if files_scanned > len(results):
        summary_parts.append(f"scanned {files_scanned} files")
    if files_skipped:
        summary_parts.append(f"skipped {files_skipped} large files")

    caps_hit = []
    if len(results) >= MAX_RESULTS_FILES:
        caps_hit.append(f"max {MAX_RESULTS_FILES} files")
    if output_lines >= MAX_OUTPUT_LINES:
        caps_hit.append(f"max {MAX_OUTPUT_LINES} lines")

    print(f"Total: {', '.join(summary_parts)}")
    if caps_hit:
        print(f"Capped at: {', '.join(caps_hit)}")

    print("")
    if results:
        first_id = results[0]['entry'].get('id', '')[:8]
        print(f'Tip: /context-open {first_id} --grep "{pattern}"')

if __name__ == '__main__':
    main()
```

## Output Example

```
Searching for: "AssertionError"
Filters: cmd=pytest, since=24h

Found 7 matches across 3 outputs:

[A1B2C3D4] pytest e=1 (2h ago) - 4 matches
  45: AssertionError: expected 200, got 404
  89: AssertionError: mock not called
  ...2 more matches (use --full)

[C3D4E5F6] pytest e=1 (5h ago) - 2 matches
  12: AssertionError: values differ

[E5F6G7H8] pytest e=1 (1d ago) - 1 match
  234: raise AssertionError("unexpected state")

--------------------------------------------------
Total: 7 matches in 3 files, scanned 15 files
Capped at: max 50 lines

Tip: /context-open A1B2C3D4 --grep "AssertionError"
```

## Notes

- Hard caps prevent context explosion (50 files, 2MB/file, 50 lines)
- Use `--full` to increase line cap to 200
- `--cmd` filters by cmd_group (includes aliases)
- `--since` accepts `24h`, `7d`, `30m` formats
- `--pinned-only` searches only preserved outputs
- Regex patterns supported (case-insensitive)
