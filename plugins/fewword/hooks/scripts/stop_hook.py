#!/usr/bin/env python3
"""
Stop hook for FewWord - warns if scratch directory is too large.

Cross-platform: Works on Windows, macOS, and Linux.
"""

from __future__ import annotations

import os
from pathlib import Path


def get_directory_size_mb(directory: Path) -> float:
    """Calculate total size of a directory in MB (cross-platform)."""
    if not directory.exists():
        return 0.0

    total_bytes = 0
    try:
        for item in directory.rglob('*'):
            if item.is_file():
                try:
                    total_bytes += item.stat().st_size
                except OSError:
                    pass  # Skip files we can't access
    except OSError:
        pass  # Directory access error

    return total_bytes / (1024 * 1024)


def main():
    """Check scratch size and warn if too large."""
    cwd = os.environ.get('FEWWORD_CWD', os.getcwd())
    scratch_dir = Path(cwd) / '.fewword' / 'scratch'

    size_mb = get_directory_size_mb(scratch_dir)

    if size_mb > 100:
        print(f"[fewword] Warning: .fewword/scratch/ is {size_mb:.0f}MB - consider cleanup")


if __name__ == "__main__":
    main()
