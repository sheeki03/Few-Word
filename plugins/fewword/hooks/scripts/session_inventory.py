#!/usr/bin/env python3
"""
SessionStart inventory injection for FewWord.

Prints a brief summary of what's in scratch (if anything) to help Claude
recover context after compaction.

Output is ultra-minimal (~50-100 tokens) to avoid context bloat.
If scratch is empty, prints nothing.

This is "best-effort" - /recent is the primary recovery path.
"""
from __future__ import annotations

import os
import json
import re
from pathlib import Path
from datetime import datetime


# Pattern for offload files
OUTPUT_PATTERN = re.compile(
    r'^([a-zA-Z0-9_-]+)_(\d{8}_\d{6})_([0-9a-f]{8})_exit(-?\d+)\.txt$',
    re.IGNORECASE
)

LEGACY_PATTERN = re.compile(
    r'^([a-zA-Z0-9_-]+)_(\d{8}_\d{6})_([0-9a-f]{8})\.txt$',
    re.IGNORECASE
)


def is_alias_file(filename: str) -> bool:
    """Check if file is a LATEST alias."""
    return filename.startswith('LATEST')


def parse_file_brief(filepath: Path) -> dict | None:
    """Extract brief info from offload file."""
    filename = filepath.name

    # Parse modern pattern
    match = OUTPUT_PATTERN.match(filename)
    if match:
        cmd = match.group(1)
        file_id = match.group(3).upper()[:4]  # Short ID for display
        exit_code = int(match.group(4))
        try:
            stat = filepath.stat()
            age_hours = (datetime.now().timestamp() - stat.st_mtime) / 3600
            return {
                'id': file_id,
                'cmd': cmd[:10],  # Truncate long commands
                'exit': exit_code,
                'age_h': age_hours,
            }
        except OSError:
            return None

    # Parse legacy pattern
    match = LEGACY_PATTERN.match(filename)
    if match:
        cmd = match.group(1)
        file_id = match.group(3).upper()[:4]
        try:
            stat = filepath.stat()
            age_hours = (datetime.now().timestamp() - stat.st_mtime) / 3600
            return {
                'id': file_id,
                'cmd': cmd[:10],
                'exit': 0,  # Assume success for legacy
                'age_h': age_hours,
            }
        except OSError:
            return None

    return None


def get_latest_aliases(scratch_dir: Path) -> set:
    """Get set of commands that have LATEST aliases (truncated to match cmd display)."""
    aliases = set()
    for filepath in scratch_dir.iterdir():
        if filepath.is_file() and filepath.name.startswith('LATEST_') and filepath.name.endswith('.txt'):
            # Extract command from LATEST_{cmd}.txt, truncate to match cmd[:10] display
            cmd = filepath.name[7:-4]  # Remove "LATEST_" and ".txt"
            aliases.add(cmd[:10])  # Truncate to match parse_file_brief cmd[:10]
    return aliases


def format_age(hours: float) -> str:
    """Format age in human-readable form."""
    if hours < 1:
        return f"{int(hours * 60)}m"
    elif hours < 24:
        return f"{int(hours)}h"
    else:
        return f"{int(hours / 24)}d"


def main():
    """Print inventory summary if scratch has files."""
    cwd = os.getcwd()
    scratch_dir = Path(cwd) / '.fewword' / 'scratch' / 'tool_outputs'

    # Skip if disabled
    if os.environ.get('FEWWORD_DISABLE_INVENTORY'):
        return

    if not scratch_dir.exists():
        return

    # Collect offload files (not aliases)
    files = []
    total_size = 0
    for filepath in scratch_dir.iterdir():
        if filepath.is_file() and not is_alias_file(filepath.name):
            info = parse_file_brief(filepath)
            if info:
                try:
                    info['size'] = filepath.stat().st_size
                    total_size += info['size']
                    files.append(info)
                except OSError:
                    pass

    if not files:
        return  # Nothing to show

    # Sort by age (newest first)
    files.sort(key=lambda x: x['age_h'])

    # Get LATEST aliases
    aliases = get_latest_aliases(scratch_dir)

    # Format output (ultra-minimal)
    size_kb = total_size / 1024
    if size_kb >= 1024:
        size_str = f"{size_kb / 1024:.1f}MB"
    else:
        size_str = f"{size_kb:.0f}KB"

    print(f"[fewword] Scratch: {len(files)} files, {size_str}")

    # Show last 3 files
    recent = files[:3]
    recent_strs = []
    for f in recent:
        s = f"{f['id']} {f['cmd']} exit={f['exit']}"
        if f['cmd'] in aliases:
            s += f" (LATEST_{f['cmd']})"
        recent_strs.append(s)

    if recent_strs:
        print(f"Recent: {', '.join(recent_strs)}")

    print("Full list: /recent")


if __name__ == "__main__":
    main()
