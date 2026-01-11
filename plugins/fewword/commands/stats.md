---
description: "Show FewWord session statistics with rich output and token savings"
---

# FewWord Stats

Show comprehensive statistics about offloaded outputs, token savings, and retrieval patterns.

## Usage

```bash
/stats                    # Current session stats
/stats --json             # Output as JSON
/stats --all-time         # Stats across all sessions
```

## Implementation

Run this Python script to display rich stats:

```python
#!/usr/bin/env python3
"""FewWord Stats - Rich session statistics."""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

def get_cwd():
    return os.environ.get('FEWWORD_CWD', os.getcwd())

def get_session_info(cwd):
    """Get current session info."""
    session_file = Path(cwd) / '.fewword' / 'index' / 'session.json'
    try:
        with open(session_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, IOError):
        return None

def get_manifest_entries(cwd, session_id=None):
    """Get manifest entries, optionally filtered by session."""
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'
    entries = {
        'offloads': [],
        'pins': [],
        'tags': [],
        'notes': [],
        'opens': []
    }

    if not manifest_path.exists():
        return entries

    with open(manifest_path, 'r') as f:
        for line in f:
            try:
                entry = json.loads(line)
                entry_type = entry.get('type', '')

                # Filter by session if specified
                if session_id and entry_type == 'offload':
                    if entry.get('session_id') != session_id:
                        continue

                if entry_type == 'offload':
                    entries['offloads'].append(entry)
                elif entry_type == 'pin':
                    entries['pins'].append(entry)
                elif entry_type == 'tag':
                    entries['tags'].append(entry)
                elif entry_type == 'note':
                    entries['notes'].append(entry)
                elif entry_type == 'open':
                    entries['opens'].append(entry)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

    return entries

def count_existing_files(cwd, entries):
    """Count how many output files still exist."""
    existing = 0
    cleaned = 0
    for entry in entries:
        path = Path(cwd) / entry.get('path', '')
        if path.exists():
            existing += 1
        else:
            cleaned += 1
    return existing, cleaned

def calculate_tokens(bytes_count, pointer_count, pointer_tokens=35):
    """Calculate token savings."""
    tokens_inline = bytes_count // 4  # ~4 bytes per token
    tokens_pointers = pointer_count * pointer_tokens
    tokens_saved = tokens_inline - tokens_pointers
    if tokens_inline > 0:
        reduction_pct = int((tokens_saved / tokens_inline) * 100)
    else:
        reduction_pct = 0
    return tokens_inline, tokens_pointers, tokens_saved, reduction_pct

def format_bytes(b):
    """Format bytes as human-readable."""
    if b >= 1048576:
        return f"{b / 1048576:.1f}MB"
    elif b >= 1024:
        return f"{b / 1024:.1f}KB"
    else:
        return f"{b}B"

def format_duration(seconds):
    """Format duration as human-readable."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"

def main():
    args = sys.argv[1:]
    cwd = get_cwd()

    json_mode = '--json' in args
    all_time = '--all-time' in args

    # Get session info
    session = get_session_info(cwd)
    session_id = None if all_time else (session.get('session_id') if session else None)

    # Get entries
    entries = get_manifest_entries(cwd, session_id=session_id)
    offloads = entries['offloads']

    if not offloads and not all_time:
        if not session:
            print("No active session found.")
            print("Session tracking starts on next SessionStart.")
        else:
            print(f"No outputs offloaded this session ({session.get('session_id', '?')[:8]}).")
            print("")
            print("Outputs < 512B are shown inline (no savings needed).")
            print("Run commands with larger outputs to see savings.")
        sys.exit(0)

    # Calculate basic stats
    total_bytes = sum(e.get('bytes', 0) for e in offloads)
    total_lines = sum(e.get('lines', 0) for e in offloads)
    total_count = len(offloads)

    # Count existing vs cleaned
    existing, cleaned = count_existing_files(cwd, offloads)

    # Token calculations
    tokens_inline, tokens_pointers, tokens_saved, reduction_pct = calculate_tokens(total_bytes, total_count)

    # Tier breakdown
    tier2 = [e for e in offloads if 512 <= e.get('bytes', 0) < 4096]
    tier3 = [e for e in offloads if e.get('bytes', 0) >= 4096]
    tier2_bytes = sum(e.get('bytes', 0) for e in tier2)
    tier3_bytes = sum(e.get('bytes', 0) for e in tier3)

    # Command breakdown
    cmd_stats = defaultdict(lambda: {'count': 0, 'bytes': 0, 'failures': 0})
    for e in offloads:
        cmd = e.get('cmd_group') or e.get('cmd', 'unknown')
        cmd_stats[cmd]['count'] += 1
        cmd_stats[cmd]['bytes'] += e.get('bytes', 0)
        if e.get('exit_code', 0) != 0:
            cmd_stats[cmd]['failures'] += 1

    # Sort by bytes descending
    top_cmds = sorted(cmd_stats.items(), key=lambda x: -x[1]['bytes'])[:5]

    # Find biggest output
    biggest = max(offloads, key=lambda e: e.get('bytes', 0)) if offloads else None

    # Retrieval stats (if tracking opens)
    opens = entries['opens']
    opened_ids = set(o.get('id', '').upper() for o in opens)
    retrieved_count = len([e for e in offloads if e.get('id', '').upper() in opened_ids])
    retrieval_rate = int((retrieved_count / total_count) * 100) if total_count > 0 else 0

    # Session duration
    if session:
        try:
            started = datetime.fromisoformat(session.get('started_at', '').replace('Z', '+00:00'))
            duration_secs = (datetime.now(timezone.utc) - started).total_seconds()
            duration_str = format_duration(duration_secs)
        except (ValueError, TypeError, AttributeError):
            duration_str = "?"
    else:
        duration_str = "N/A"

    # JSON output mode
    if json_mode:
        output = {
            'session_id': session.get('session_id') if session else None,
            'all_time': all_time,
            'tokens': {
                'prevented': tokens_inline,
                'used': tokens_pointers,
                'saved': tokens_saved,
                'reduction_pct': reduction_pct
            },
            'storage': {
                'count': total_count,
                'bytes': total_bytes,
                'existing': existing,
                'cleaned': cleaned
            },
            'tiers': {
                'compact': {'count': len(tier2), 'bytes': tier2_bytes},
                'preview': {'count': len(tier3), 'bytes': tier3_bytes}
            },
            'top_commands': {cmd: stats for cmd, stats in top_cmds},
            'retrieval_rate': retrieval_rate
        }
        print(json.dumps(output, indent=2))
        sys.exit(0)

    # Rich text output
    session_label = f"Session {session.get('session_id', '?')[:8]}" if session and not all_time else "All Time"

    print("=" * 55)
    print(f"       FewWord {'Session' if not all_time else 'All-Time'} Stats ({session_label})")
    print("=" * 55)
    print("")

    # Token Savings
    print("Token Savings")
    print(f"   Prevented:     ~{tokens_inline:,} tokens")
    print(f"   Actually used: ~{tokens_pointers:,} tokens (pointers)")
    print(f"   Net savings:   ~{tokens_saved:,} tokens ({reduction_pct}% reduction)")
    print("")

    # Storage
    print("Storage")
    print(f"   Offloaded:     {total_count} outputs ({format_bytes(total_bytes)})")
    print(f"   Still exists:  {existing} outputs")
    print(f"   Cleaned up:    {cleaned} outputs (TTL expired)")
    if entries['pins']:
        pinned_ids = set(p.get('id', '').upper() for p in entries['pins'])
        pinned_count = len([e for e in offloads if e.get('id', '').upper() in pinned_ids])
        print(f"   Pinned:        {pinned_count} outputs")
    print("")

    # Tier Breakdown
    print("By Tier")
    print(f"   Inline (<512B):     (shown in context, not tracked)")
    print(f"   Compact (512B-4KB): {len(tier2)} outputs ({format_bytes(tier2_bytes)})")
    print(f"   Preview (>4KB):     {len(tier3)} outputs ({format_bytes(tier3_bytes)})")
    print("")

    # Top Commands
    if top_cmds:
        print("Top Commands by Size")
        for i, (cmd, stats) in enumerate(top_cmds, 1):
            fail_str = f", {stats['failures']} failed" if stats['failures'] else ""
            print(f"   {i}. {cmd:12} {format_bytes(stats['bytes']):>8} ({stats['count']} runs{fail_str})")
        print("")

    # Biggest Output
    if biggest:
        print("Biggest Output")
        big_id = biggest.get('id', '????')[:8]
        big_cmd = biggest.get('cmd', '?')
        big_bytes = format_bytes(biggest.get('bytes', 0))
        print(f"   [{big_id}] {big_cmd} ({big_bytes})")
        print(f"   /open {big_id}")
        print("")

    # Retrieval Rate
    print("Retrieval Rate")
    print(f"   Outputs opened: {retrieved_count}/{total_count} ({retrieval_rate}%)")
    print("")

    # Session info
    if session and not all_time:
        print(f"Session started: {duration_str} ago")

    print("")
    print("Commands: /recent | /timeline | /doctor")

if __name__ == '__main__':
    main()
```

## Output Example

```
=======================================================
       FewWord Session Stats (b719edab)
=======================================================

Token Savings
   Prevented:     ~15,240 tokens
   Actually used: ~1,470 tokens (pointers)
   Net savings:   ~13,770 tokens (90% reduction)

Storage
   Offloaded:     42 outputs (15.3MB)
   Still exists:  34 outputs
   Cleaned up:    8 outputs (TTL expired)
   Pinned:        3 outputs

By Tier
   Inline (<512B):     (shown in context, not tracked)
   Compact (512B-4KB): 15 outputs (42.5KB)
   Preview (>4KB):     27 outputs (15.2MB)

Top Commands by Size
   1. pytest       8.2MB (19 runs, 5 failed)
   2. npm          4.1MB (8 runs)
   3. cargo        2.8MB (12 runs, 1 failed)
   4. tsc          128KB (3 runs, 2 failed)

Biggest Output
   [A1B2C3D4] pytest (2.1MB)
   /open A1B2C3D4

Retrieval Rate
   Outputs opened: 12/42 (28%)

Session started: 2h 15m ago

Commands: /recent | /timeline | /doctor
```

## Notes

- `--json` outputs machine-readable format for scripting
- `--all-time` shows stats across all sessions (not just current)
- Retrieval rate tracks how often outputs are actually opened
- Token estimate: ~4 bytes/token, ~35 tokens/pointer
