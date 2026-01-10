#!/usr/bin/env python3
"""
Cross-platform helpers for context commands (stdlib only).

Usage:
    python3 context_helpers.py age "2025-01-09T10:15:30Z"
    python3 context_helpers.py resolve "1" ".fewword/index/tool_outputs.jsonl" ".fewword/index/.recent_index"
    python3 context_helpers.py resolve "pytest" ".fewword/index/tool_outputs.jsonl" ".fewword/index/.recent_index"
    python3 context_helpers.py resolve "A1B2C3D4" ".fewword/index/tool_outputs.jsonl" ".fewword/index/.recent_index"
"""
import sys
import json
from datetime import datetime, timezone
from pathlib import Path


def calculate_age(iso_timestamp: str) -> str:
    """Convert ISO timestamp to human-readable age (e.g., '2h', '3d')."""
    try:
        # Handle both 'Z' suffix and +00:00 format
        ts = iso_timestamp.replace('Z', '+00:00')
        created = datetime.fromisoformat(ts)
        now = datetime.now(timezone.utc)
        diff = int((now - created).total_seconds())

        if diff < 0:
            return "future"
        elif diff < 60:
            return f"{diff}s"
        elif diff < 3600:
            return f"{diff // 60}m"
        elif diff < 86400:
            return f"{diff // 3600}h"
        else:
            return f"{diff // 86400}d"
    except Exception:
        return "?"


def get_index_path(index_path: str) -> str:
    """
    Resolve index path, handling Windows pointer file fallback.

    On Unix, .recent_index is a symlink to the session-specific file.
    On Windows, it's a text file containing the path to the actual index.
    """
    path = Path(index_path)
    if not path.exists():
        return index_path

    # Check if it's a pointer file (Windows fallback)
    # Pointer files contain a single line with the actual path
    try:
        content = path.read_text().strip()
        if content.startswith('.fewword/') and '\n' not in content:
            # It's a pointer file, return the actual path
            return content
    except Exception:
        pass

    return index_path


def resolve_id(selector: str, manifest_path: str, index_path: str) -> str:
    """
    Resolve selector (number/hex/cmd/title) to hex ID.

    Supports four modes:
    1. Number (1-99): Lookup from .recent_index
    2. Hex ID (8 chars): Validate and return
    3. Command name: Find latest exact match in manifest (offload entries)
    4. Title: Find latest exact match by title (manual/export entries)
    """
    selector = selector.strip()

    if not selector:
        return ""

    # Mode 1: Number - lookup from .recent_index
    if selector.isdigit():
        num = int(selector)
        if 1 <= num <= 99:
            try:
                actual_index = get_index_path(index_path)
                with open(actual_index, 'r') as f:
                    lines = f.readlines()
                idx = num - 1
                if 0 <= idx < len(lines):
                    # Format: <num>:<hex_id>:<cmd>
                    parts = lines[idx].strip().split(':')
                    if len(parts) >= 2:
                        return parts[1].upper()
            except Exception:
                pass
        return ""

    # Mode 2: Hex ID - validate 8-char hex and return
    if len(selector) == 8:
        if all(c in '0123456789ABCDEFabcdef' for c in selector):
            return selector.upper()

    # Mode 3 & 4: Command name OR title - find latest exact match in manifest
    try:
        with open(manifest_path, 'r') as f:
            lines = f.readlines()

        # Search in reverse (most recent first)
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                entry_type = entry.get('type', '')

                # Mode 3: Match offload entries by cmd
                if entry_type == 'offload':
                    if entry.get('cmd') == selector:  # Exact match only
                        return entry.get('id', '').upper()

                # Mode 4: Match manual/export entries by title (case-insensitive)
                if entry_type in ('manual', 'export'):
                    if entry.get('title', '').lower() == selector.lower():
                        return entry.get('id', '').upper()
            except json.JSONDecodeError:
                continue
    except Exception:
        pass

    return ""


def lookup_entry(hex_id: str, manifest_path: str) -> dict:
    """
    Lookup full entry from manifest by hex ID.

    Returns dict with entry fields. For offload entries: id, cmd, exit_code, bytes, lines, path, created_at
    For manual/export entries: id, title, source, bytes, lines, path, created_at (no exit_code)
    """
    hex_id = hex_id.upper()
    try:
        with open(manifest_path, 'r') as f:
            for line in reversed(f.readlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    # Match offload, manual, and export entry types
                    if entry.get('type') in ('offload', 'manual', 'export'):
                        if entry.get('id', '').upper() == hex_id:
                            return entry
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return {}


def main():
    if len(sys.argv) < 2:
        print("Usage: context_helpers.py <command> [args...]")
        print("Commands:")
        print("  age <iso_timestamp>      - Convert timestamp to human age")
        print("  resolve <selector> <manifest> <index> - Resolve ID")
        print("  lookup <hex_id> <manifest> - Get full entry as JSON")
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "age":
        if args:
            print(calculate_age(args[0]))
        else:
            print("?")

    elif cmd == "resolve":
        if len(args) >= 3:
            result = resolve_id(args[0], args[1], args[2])
            print(result)
        else:
            print("")

    elif cmd == "lookup":
        if len(args) >= 2:
            entry = lookup_entry(args[0], args[1])
            print(json.dumps(entry) if entry else "{}")
        else:
            print("{}")

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
