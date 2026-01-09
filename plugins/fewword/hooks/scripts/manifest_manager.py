#!/usr/bin/env python3
"""
FewWord Manifest Manager

Handles manifest rotation and compression for large outputs.

Features:
- Manifest rotation when size exceeds threshold
- Compressed storage for large outputs (gzip)
- Reading across rotated manifests
- Cleanup of old rotated manifests

Usage:
    # Rotate manifest if needed
    python3 manifest_manager.py rotate [cwd]

    # Compress file if eligible
    python3 manifest_manager.py compress <file_path> [min_bytes]

    # Read from all manifests
    python3 manifest_manager.py read-all [cwd] [limit]
"""

import gzip
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Generator


def get_cwd():
    """Get current working directory from env or os."""
    return os.environ.get('FEWWORD_CWD', os.getcwd())


def get_manifest_path(cwd: str) -> Path:
    """Get path to main manifest file."""
    return Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'


def get_rotated_manifests(cwd: str) -> List[Path]:
    """Get list of rotated manifest files, sorted newest first."""
    index_dir = Path(cwd) / '.fewword' / 'index'
    if not index_dir.exists():
        return []

    # Find all rotated manifests (tool_outputs_YYYY-MM.jsonl)
    rotated = list(index_dir.glob('tool_outputs_*.jsonl'))
    # Sort by name descending (newest first)
    rotated.sort(reverse=True)
    return rotated


def check_manifest_size(cwd: str, max_mb: int = 50) -> bool:
    """Check if manifest needs rotation."""
    manifest = get_manifest_path(cwd)
    if not manifest.exists():
        return False

    size_mb = manifest.stat().st_size / (1024 * 1024)
    return size_mb >= max_mb


def rotate_manifest(cwd: str, keep_rotated: int = 5) -> Optional[str]:
    """
    Rotate manifest if it exists and is non-empty.

    Returns the path to rotated file, or None if nothing rotated.
    """
    manifest = get_manifest_path(cwd)
    if not manifest.exists():
        return None

    # Only rotate if non-empty
    if manifest.stat().st_size == 0:
        return None

    # Generate rotated filename with year-month
    timestamp = datetime.now().strftime('%Y-%m')
    index_dir = manifest.parent
    rotated_name = f'tool_outputs_{timestamp}.jsonl'
    rotated_path = index_dir / rotated_name

    # If same month rotation exists, append a counter
    counter = 1
    while rotated_path.exists():
        rotated_name = f'tool_outputs_{timestamp}_{counter}.jsonl'
        rotated_path = index_dir / rotated_name
        counter += 1

    # Move current to rotated
    shutil.move(str(manifest), str(rotated_path))

    # Create fresh manifest
    manifest.touch()

    # Cleanup old rotated manifests
    cleanup_old_rotated(cwd, keep_rotated)

    return str(rotated_path)


def cleanup_old_rotated(cwd: str, keep: int = 5):
    """Remove rotated manifests beyond keep limit."""
    rotated = get_rotated_manifests(cwd)

    # Keep the newest 'keep' manifests
    for old_manifest in rotated[keep:]:
        try:
            old_manifest.unlink()
        except Exception:
            pass


def read_all_manifests(cwd: str, limit: int = 1000) -> Generator[Dict, None, None]:
    """
    Read entries from all manifests (current + rotated).

    Yields entries newest first, up to limit.
    """
    manifest = get_manifest_path(cwd)
    rotated = get_rotated_manifests(cwd)

    count = 0

    # Read from current manifest first (newest)
    if manifest.exists():
        lines = manifest.read_text().strip().split('\n')
        for line in reversed(lines):
            if not line:
                continue
            try:
                entry = json.loads(line)
                yield entry
                count += 1
                if count >= limit:
                    return
            except json.JSONDecodeError:
                pass

    # Then read from rotated manifests (newest to oldest)
    for rotated_manifest in rotated:
        try:
            lines = rotated_manifest.read_text().strip().split('\n')
            for line in reversed(lines):
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    yield entry
                    count += 1
                    if count >= limit:
                        return
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass


def compress_file(file_path: str, min_bytes: int = 1048576, level: int = 6) -> Optional[str]:
    """
    Compress a file with gzip if it exceeds min_bytes.

    Args:
        file_path: Path to file to compress
        min_bytes: Minimum size to trigger compression
        level: Gzip compression level (1-9)

    Returns:
        Path to compressed file, or None if not compressed
    """
    path = Path(file_path)
    if not path.exists():
        return None

    # Don't compress if already compressed
    if path.suffix == '.gz':
        return None

    # Check size threshold
    if path.stat().st_size < min_bytes:
        return None

    # Compress
    compressed_path = path.with_suffix(path.suffix + '.gz')
    try:
        with open(path, 'rb') as f_in:
            with gzip.open(compressed_path, 'wb', compresslevel=level) as f_out:
                shutil.copyfileobj(f_in, f_out)

        # Remove original
        path.unlink()
        return str(compressed_path)
    except Exception:
        # Cleanup failed compression
        if compressed_path.exists():
            compressed_path.unlink()
        return None


def decompress_file(file_path: str) -> Optional[str]:
    """
    Decompress a gzipped file.

    Args:
        file_path: Path to .gz file

    Returns:
        Content as string, or None if failed
    """
    path = Path(file_path)
    if not path.exists():
        return None

    if not path.suffix == '.gz':
        # Not compressed, read normally
        return path.read_text()

    try:
        with gzip.open(path, 'rt') as f:
            return f.read()
    except Exception:
        return None


def read_file_auto(file_path: str) -> Optional[str]:
    """
    Read file, automatically decompressing if .gz extension.

    Args:
        file_path: Path to file (may be .gz)

    Returns:
        File content as string
    """
    path = Path(file_path)
    if not path.exists():
        # Try with .gz extension
        gz_path = Path(str(file_path) + '.gz')
        if gz_path.exists():
            path = gz_path

    if not path.exists():
        return None

    if path.suffix == '.gz':
        return decompress_file(str(path))
    else:
        return path.read_text()


def get_compression_stats(cwd: str) -> Dict:
    """Get statistics about compressed files."""
    scratch_dir = Path(cwd) / '.fewword' / 'scratch' / 'tool_outputs'
    if not scratch_dir.exists():
        return {'compressed': 0, 'uncompressed': 0, 'savings_bytes': 0}

    compressed = 0
    uncompressed = 0
    compressed_bytes = 0
    uncompressed_bytes = 0

    for f in scratch_dir.iterdir():
        if f.is_file():
            size = f.stat().st_size
            if f.suffix == '.gz':
                compressed += 1
                compressed_bytes += size
            else:
                uncompressed += 1
                uncompressed_bytes += size

    # Note: savings_bytes would require knowing original uncompressed size of compressed files
    # For now, we report the raw byte counts and let callers compute estimates if needed
    return {
        'compressed': compressed,
        'uncompressed': uncompressed,
        'compressed_bytes': compressed_bytes,
        'uncompressed_bytes': uncompressed_bytes,
        'savings_bytes': 0  # P1 fix: key missing caused KeyError in callers
    }


# === CLI ===

def main():
    if len(sys.argv) < 2:
        print("Usage: manifest_manager.py <command> [args]")
        print("")
        print("Commands:")
        print("  rotate [cwd]              Rotate manifest if needed")
        print("  compress <file> [min_bytes]  Compress file if eligible")
        print("  read-all [cwd] [limit]    Read all manifest entries")
        print("  stats [cwd]               Show compression statistics")
        sys.exit(1)

    command = sys.argv[1]

    if command == 'rotate':
        cwd = sys.argv[2] if len(sys.argv) > 2 else get_cwd()
        max_mb = int(os.environ.get('FEWWORD_MANIFEST_MAX_MB', 50))
        keep = int(os.environ.get('FEWWORD_MANIFEST_KEEP_ROTATED', 5))

        if check_manifest_size(cwd, max_mb):
            result = rotate_manifest(cwd, keep)
            if result:
                print(f"Rotated manifest to: {result}")
            else:
                print("Rotation not needed")
        else:
            print("Manifest size OK, no rotation needed")

    elif command == 'compress':
        if len(sys.argv) < 3:
            print("Usage: manifest_manager.py compress <file_path> [min_bytes]")
            sys.exit(1)

        file_path = sys.argv[2]
        min_bytes = int(sys.argv[3]) if len(sys.argv) > 3 else 1048576

        result = compress_file(file_path, min_bytes)
        if result:
            print(f"Compressed to: {result}")
        else:
            print("Not compressed (too small or already compressed)")

    elif command == 'read-all':
        cwd = sys.argv[2] if len(sys.argv) > 2 else get_cwd()
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 100

        count = 0
        for entry in read_all_manifests(cwd, limit):
            print(json.dumps(entry))
            count += 1

        print(f"# Read {count} entries", file=sys.stderr)

    elif command == 'stats':
        cwd = sys.argv[2] if len(sys.argv) > 2 else get_cwd()
        stats = get_compression_stats(cwd)
        print(f"Compressed files: {stats['compressed']}")
        print(f"Uncompressed files: {stats['uncompressed']}")
        print(f"Compressed size: {stats['compressed_bytes'] / 1024:.1f}KB")
        print(f"Uncompressed size: {stats['uncompressed_bytes'] / 1024:.1f}KB")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == '__main__':
    main()
