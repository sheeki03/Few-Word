---
description: "Visual timeline of command outputs in current session"
arguments:
  - name: options
    description: "Filter options: --last 2h, --cmd pytest, --failures"
    required: false
---

# Context Timeline

Display a visual timeline of command outputs for the current session.

## Usage

```bash
/timeline                 # Current session
/timeline --last 2h       # Last 2 hours
/timeline --last 30m      # Last 30 minutes
/timeline --cmd pytest    # Filter by command
/timeline --failures      # Only show failures
```

## Implementation

Run this Python script to display timeline:

```python
#!/usr/bin/env python
"""Context Timeline - Visual session history."""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict

def get_cwd():
    return os.environ.get('FEWWORD_CWD', os.getcwd())

def parse_duration(duration_str):
    """Parse duration string like '2h', '30m', '1d' to timedelta."""
    if not duration_str:
        return None

    # P1 fix #25: Wrap int() in try/except to handle invalid input, remove unused 'match' variable
    try:
        if duration_str.endswith('h'):
            return timedelta(hours=int(duration_str[:-1]))
        elif duration_str.endswith('m'):
            return timedelta(minutes=int(duration_str[:-1]))
        elif duration_str.endswith('d'):
            return timedelta(days=int(duration_str[:-1]))
        elif duration_str.endswith('s'):
            return timedelta(seconds=int(duration_str[:-1]))
    except ValueError:
        return None
    return None

def format_time(iso_timestamp):
    """Format timestamp as HH:MM."""
    try:
        ts = iso_timestamp.replace('Z', '+00:00')
        dt = datetime.fromisoformat(ts)
        # Convert to local time
        local_dt = dt.astimezone()
        return local_dt.strftime('%H:%M')
    except (ValueError, TypeError, AttributeError):
        return '??:??'

def get_session_info(cwd):
    """Get current session info."""
    session_file = Path(cwd) / '.fewword' / 'index' / 'session.json'
    try:
        with open(session_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, IOError):
        return None

def get_manifest_entries(cwd, session_id=None, since=None, cmd_filter=None, failures_only=False):
    """Get manifest entries with filters."""
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'
    entries = []

    if not manifest_path.exists():
        return entries

    now = datetime.now(timezone.utc)

    with open(manifest_path, 'r') as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get('type') != 'offload':
                    continue

                # Filter by session
                if session_id and entry.get('session_id') != session_id:
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

                # Filter by command
                if cmd_filter:
                    cmd = entry.get('cmd_group') or entry.get('cmd')
                    if cmd != cmd_filter:
                        continue

                # Filter failures
                if failures_only and entry.get('exit_code', 0) == 0:
                    continue

                entries.append(entry)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

    return entries

def group_by_time_bucket(entries, bucket_minutes=15):
    """Group entries into time buckets."""
    buckets = defaultdict(list)

    for entry in entries:
        try:
            ts = entry.get('created_at', '').replace('Z', '+00:00')
            dt = datetime.fromisoformat(ts)
            # Round to nearest bucket
            bucket = dt.replace(minute=(dt.minute // bucket_minutes) * bucket_minutes, second=0, microsecond=0)
            buckets[bucket].append(entry)
        except (ValueError, TypeError, AttributeError):
            pass

    return dict(sorted(buckets.items()))

def truncate(s, max_len):
    """Truncate string with ellipsis."""
    if len(s) <= max_len:
        return s
    return s[:max_len-1] + '…'

def main():
    args = sys.argv[1:]
    cwd = get_cwd()

    # Parse flags
    cmd_filter = None
    since = None
    failures_only = '--failures' in args

    # Parse --last duration
    for i, arg in enumerate(args):
        if arg == '--last' and i + 1 < len(args):
            since = parse_duration(args[i + 1])
        elif arg == '--cmd' and i + 1 < len(args):
            cmd_filter = args[i + 1]

    # Get session info
    session = get_session_info(cwd)
    if not session and not since:
        print("No active session found.")
        print("Use --last 2h to see recent outputs regardless of session.")
        sys.exit(0)

    session_id = session.get('session_id') if session and not since else None

    # Get entries
    entries = get_manifest_entries(
        cwd,
        session_id=session_id,
        since=since,
        cmd_filter=cmd_filter,
        failures_only=failures_only
    )

    if not entries:
        filter_desc = []
        if cmd_filter:
            filter_desc.append(f"cmd={cmd_filter}")
        if failures_only:
            filter_desc.append("failures only")
        if since:
            filter_desc.append(f"last {args[args.index('--last')+1] if '--last' in args else '?'}")

        print("No outputs found" + (f" ({', '.join(filter_desc)})" if filter_desc else "") + ".")
        sys.exit(0)

    # Calculate session duration
    if session:
        try:
            started = datetime.fromisoformat(session.get('started_at', '').replace('Z', '+00:00'))
            duration = datetime.now(timezone.utc) - started
            hours = int(duration.total_seconds() // 3600)
            minutes = int((duration.total_seconds() % 3600) // 60)
            duration_str = f"{hours}h {minutes}m" if hours else f"{minutes}m"
        except (ValueError, TypeError, AttributeError):
            duration_str = "?"
    else:
        duration_str = "N/A"

    # Print header
    if session_id:
        print(f"Session {session_id[:8]} ({duration_str})")
    else:
        print(f"Timeline (last {args[args.index('--last')+1] if '--last' in args else '?'})")

    print("=" * 70)

    # Group by time buckets (15 min)
    buckets = group_by_time_bucket(entries, bucket_minutes=15)

    # Count failures for summary
    total_failures = sum(1 for e in entries if e.get('exit_code', 0) != 0)
    failure_cmds = defaultdict(int)
    for e in entries:
        if e.get('exit_code', 0) != 0:
            cmd = e.get('cmd_group') or e.get('cmd', '?')
            failure_cmds[cmd] += 1

    # Print timeline
    time_labels = []
    cmd_rows = []

    for bucket_time, bucket_entries in buckets.items():
        time_label = bucket_time.astimezone().strftime('%H:%M')
        time_labels.append(time_label)

        # Build cell for this bucket
        cells = []
        for entry in bucket_entries[:3]:  # Max 3 per bucket
            cmd = entry.get('cmd_group') or entry.get('cmd', '?')
            cmd = truncate(cmd, 8)
            exit_code = entry.get('exit_code', 0)
            status = '✗' if exit_code != 0 else '✓'
            entry_id = entry.get('id', '????')[:4]
            cells.append(f"{status} {cmd}")

        cmd_rows.append(cells)

    # Print time header
    print(" " + " │ ".join(f"{t:^10}" for t in time_labels))
    print("─" * (len(time_labels) * 13))

    # Print rows (max 3 rows for stacked entries)
    max_stack = max(len(cells) for cells in cmd_rows) if cmd_rows else 0
    for row_idx in range(max_stack):
        row_cells = []
        for cells in cmd_rows:
            if row_idx < len(cells):
                row_cells.append(f"{cells[row_idx]:^10}")
            else:
                row_cells.append(" " * 10)
        print(" " + " │ ".join(row_cells))

    print("─" * (len(time_labels) * 13))

    # Print legend and summary
    print("")
    print(f"Legend: ✓ = exit 0, ✗ = exit != 0")
    print(f"Total: {len(entries)} outputs, {total_failures} failures")

    if failure_cmds:
        failure_summary = ", ".join(f"{cmd}({count})" for cmd, count in sorted(failure_cmds.items(), key=lambda x: -x[1])[:3])
        print(f"Failures: {failure_summary}")

    # Suggest diff if there are failures that later passed
    cmd_history = defaultdict(list)
    for e in entries:
        cmd = e.get('cmd_group') or e.get('cmd')
        cmd_history[cmd].append(e)

    suggestions = []
    for cmd, history in cmd_history.items():
        if len(history) >= 2:
            exits = [e.get('exit_code', 0) for e in history]
            # Check for fail->pass pattern
            for i in range(len(exits) - 1):
                if exits[i] != 0 and exits[i+1] == 0:
                    fail_id = history[i].get('id', '?')[:8]
                    pass_id = history[i+1].get('id', '?')[:8]
                    suggestions.append(f"/diff {fail_id} {pass_id}")
                    break

    if suggestions:
        print("")
        print(f"Tip: {suggestions[0]}  (compare failing → passing)")

if __name__ == '__main__':
    main()
```

## Output Example

```
Session b719edab (2h 15m)
======================================================================
    10:30     │    10:45     │    11:00     │    11:15     │    11:45
──────────────────────────────────────────────────────────────────────
  ✗ pytest   │   ✓ npm      │   ✗ pytest   │   ✓ cargo    │   ✓ pytest
             │              │              │   ✓ git      │
──────────────────────────────────────────────────────────────────────

Legend: ✓ = exit 0, ✗ = exit != 0
Total: 6 outputs, 2 failures
Failures: pytest(2)

Tip: /diff E5F6 I9J0  (compare failing → passing)
```

## Notes

- Default shows current session only
- Use `--last 2h` to see outputs regardless of session
- Time buckets are 15 minutes (adjustable in code)
- Shows max 3 outputs per time bucket
- Automatically suggests diff when fail→pass pattern detected
