#!/usr/bin/env python3
"""
Smart cleanup script for FewWord scratch files.

Features:
- TTL-based cleanup: 24h for success (exit 0), 48h for failures (exit != 0)
- LRU eviction when scratch exceeds 250MB
- Protects LATEST aliases and newest files
- Writes tombstones to manifest for deleted files
- Handles legacy files (no exit code) with 24h default TTL

Runs on:
- SessionStart (via hooks.json)
- After each offload (called from offload_bash.py)
"""
from __future__ import annotations

import os
import re
import json
import time
from pathlib import Path
from datetime import datetime


# === Configuration (env var overrides, with safe fallbacks) ===
def _safe_int(env_var: str, default: int) -> int:
    """Parse env var as int with fallback on invalid input."""
    try:
        return int(os.environ.get(env_var, default))
    except ValueError:
        return default

RETENTION_SUCCESS_MIN = _safe_int('FEWWORD_RETENTION_SUCCESS_MIN', 1440)  # 24h
RETENTION_FAIL_MIN = _safe_int('FEWWORD_RETENTION_FAIL_MIN', 2880)        # 48h
SCRATCH_MAX_MB = _safe_int('FEWWORD_SCRATCH_MAX_MB', 250)
MIN_KEEP_FILES = 1  # Always keep at least this many newest files

# Strict pattern for real offload output files
# Matches: {cmd}_{YYYYMMDD_HHMMSS}_{8hex}_exit{code}.txt
OUTPUT_PATTERN = re.compile(
    r'^([a-zA-Z0-9_-]+)_(\d{8}_\d{6})_([0-9a-f]{8})_exit(-?\d+)\.txt$',
    re.IGNORECASE
)

# Legacy pattern (v1 files without exit code)
LEGACY_PATTERN = re.compile(
    r'^([a-zA-Z0-9_-]+)_(\d{8}_\d{6})_([0-9a-f]{8})\.txt$',
    re.IGNORECASE
)

# Temp file pattern (orphaned from interrupted commands)
# Matches: {cmd}_{YYYYMMDD_HHMMSS}_{8hex}_tmp.txt
TEMP_PATTERN = re.compile(
    r'^([a-zA-Z0-9_-]+)_(\d{8}_\d{6})_([0-9a-f]{8})_tmp\.txt$',
    re.IGNORECASE
)


def is_alias_file(filename: str) -> bool:
    """Check if file is a LATEST alias (should never be deleted)."""
    return filename.startswith('LATEST')


def is_temp_file(filename: str) -> bool:
    """Check if file is an orphaned temp file from interrupted command."""
    return bool(TEMP_PATTERN.match(filename))


def is_offload_file(filename: str) -> tuple[bool, int | None]:
    """
    Check if file is a real offload output.
    Returns (is_offload, exit_code or None).
    """
    # Check modern pattern with exit code
    match = OUTPUT_PATTERN.match(filename)
    if match:
        exit_code = int(match.group(4))
        return True, exit_code

    # Check legacy pattern (treat as success)
    if LEGACY_PATTERN.match(filename):
        return True, None  # None means legacy, use default TTL

    return False, None


def parse_file_info(filepath: Path) -> dict | None:
    """Extract info from offload file."""
    filename = filepath.name
    is_offload, exit_code = is_offload_file(filename)

    if not is_offload:
        return None

    try:
        stat = filepath.stat()
        return {
            'path': filepath,
            'filename': filename,
            'exit_code': exit_code,
            'mtime': stat.st_mtime,
            'size': stat.st_size,
            'age_minutes': (time.time() - stat.st_mtime) / 60,
        }
    except OSError:
        return None


def get_ttl_minutes(exit_code: int | None) -> int:
    """Get TTL based on exit code."""
    if exit_code is None:
        # Legacy file - use success TTL as safe default
        return RETENTION_SUCCESS_MIN
    elif exit_code == 0:
        return RETENTION_SUCCESS_MIN
    else:
        return RETENTION_FAIL_MIN


def append_tombstone(manifest_path: Path, file_id: str):
    """Append tombstone entry to manifest (append-only)."""
    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            'type': 'tombstone',
            'id': file_id,
            'deleted_at': datetime.utcnow().isoformat() + 'Z'
        }

        line = json.dumps(entry) + '\n'

        # Best-effort locking on Unix
        with open(manifest_path, 'a') as f:
            try:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (ImportError, IOError, OSError):
                pass  # Lock failed or not available, still write
            f.write(line)
    except Exception:
        pass  # Don't fail cleanup if manifest write fails


def extract_id_from_filename(filename: str) -> str | None:
    """Extract the 8-char hex ID from filename."""
    # Modern: {cmd}_{ts}_{id}_exit{code}.txt
    match = OUTPUT_PATTERN.match(filename)
    if match:
        return match.group(3)

    # Legacy: {cmd}_{ts}_{id}.txt
    match = LEGACY_PATTERN.match(filename)
    if match:
        return match.group(3)

    return None


def cleanup_scratch(cwd: str = None, verbose: bool = False):
    """
    Main cleanup function.

    0. Clean up orphaned temp files (fixes GitHub Issue #17)
    1. Find all offload files (not aliases)
    2. Apply TTL-based deletion
    3. Apply LRU eviction if over size cap
    4. Write tombstones for deleted files
    """
    if cwd is None:
        cwd = os.getcwd()

    scratch_dir = Path(cwd) / '.fewword' / 'scratch' / 'tool_outputs'
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'

    if not scratch_dir.exists():
        if verbose:
            print("[fewword] No scratch directory found")
        return

    deleted_count = 0
    deleted_bytes = 0

    # Phase 0: Clean up orphaned temp files (from interrupted commands)
    # These are left behind when process is killed before rename completes
    for filepath in scratch_dir.iterdir():
        if filepath.is_file() and is_temp_file(filepath.name):
            try:
                stat = filepath.stat()
                # Only delete temp files older than 5 minutes (in case command is still running)
                age_minutes = (time.time() - stat.st_mtime) / 60
                if age_minutes > 5:
                    filepath.unlink()
                    deleted_count += 1
                    deleted_bytes += stat.st_size
                    if verbose:
                        print(f"[fewword] Deleted (orphaned temp): {filepath.name}")
            except OSError:
                pass

    # Collect all offload files with their info
    files = []
    for filepath in scratch_dir.iterdir():
        if filepath.is_file() and not is_alias_file(filepath.name):
            info = parse_file_info(filepath)
            if info:
                files.append(info)

    if not files:
        if verbose:
            print("[fewword] No offload files found")
        # Still report temp file cleanup if any occurred
        if deleted_count > 0:
            print(f"[fewword] Cleanup: deleted {deleted_count} files ({deleted_bytes / 1024:.1f}KB), "
                  f"remaining 0 files (0.0MB)")
        return

    # Sort by mtime (newest first) for LRU
    files.sort(key=lambda x: x['mtime'], reverse=True)

    # Phase 1: TTL-based deletion
    for info in files:
        ttl = get_ttl_minutes(info['exit_code'])
        if info['age_minutes'] > ttl:
            try:
                info['path'].unlink()
                file_id = extract_id_from_filename(info['filename'])
                if file_id:
                    append_tombstone(manifest_path, file_id)
                deleted_count += 1
                deleted_bytes += info['size']
                info['deleted'] = True
                if verbose:
                    print(f"[fewword] Deleted (TTL): {info['filename']}")
            except OSError:
                pass

    # Remove deleted files from list
    files = [f for f in files if not f.get('deleted')]

    # Phase 2: LRU eviction if over size cap
    total_size_mb = sum(f['size'] for f in files) / (1024 * 1024)

    if total_size_mb > SCRATCH_MAX_MB and len(files) > MIN_KEEP_FILES:
        # Sort by mtime (oldest first for deletion)
        files.sort(key=lambda x: x['mtime'])

        while total_size_mb > SCRATCH_MAX_MB and len(files) > MIN_KEEP_FILES:
            oldest = files[0]
            try:
                oldest['path'].unlink()
                file_id = extract_id_from_filename(oldest['filename'])
                if file_id:
                    append_tombstone(manifest_path, file_id)
                deleted_count += 1
                deleted_bytes += oldest['size']
                total_size_mb -= oldest['size'] / (1024 * 1024)
                files.pop(0)  # Only remove from list after successful delete
                if verbose:
                    print(f"[fewword] Deleted (LRU): {oldest['filename']}")
            except OSError:
                # Can't delete this file, stop LRU eviction to avoid infinite loop
                break

    if verbose or deleted_count > 0:
        remaining = len(files)
        remaining_mb = sum(f['size'] for f in files) / (1024 * 1024)
        print(f"[fewword] Cleanup: deleted {deleted_count} files ({deleted_bytes / 1024:.1f}KB), "
              f"remaining {remaining} files ({remaining_mb:.1f}MB)")


def main():
    """Run cleanup from command line or SessionStart hook."""
    import sys

    # Check for verbose flag
    verbose = '-v' in sys.argv or '--verbose' in sys.argv

    # Get cwd from environment or current directory
    cwd = os.environ.get('FEWWORD_CWD', os.getcwd())

    cleanup_scratch(cwd, verbose=verbose)
    print("[fewword] Ready")


if __name__ == "__main__":
    main()
