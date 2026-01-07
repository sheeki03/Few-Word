#!/usr/bin/env python3
"""
Clean up scratch files based on retention policies.

Usage:
    python cleanup_scratch.py                    # Default: files older than 1 hour
    python cleanup_scratch.py --age 30           # Files older than 30 minutes
    python cleanup_scratch.py --all              # Remove all scratch files
    python cleanup_scratch.py --dry-run          # Show what would be deleted
"""

import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path


PLUGIN_DIR = Path(".fsctx")
SCRATCH_DIR = PLUGIN_DIR / "scratch"
MEMORY_DIR = PLUGIN_DIR / "memory"
INDEX_DIR = PLUGIN_DIR / "index"

# Retention policies (in minutes) - only for scratch/
# Note: index/ is NEVER auto-cleaned (contains active plan)
RETENTION = {
    "tool_outputs": 60,      # 1 hour
    "subagents": 120,        # 2 hours
}


def get_file_age_minutes(file_path: Path) -> float:
    """Get file age in minutes."""
    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
    age = datetime.now() - mtime
    return age.total_seconds() / 60


def cleanup_directory(dir_path: Path, max_age_minutes: int, dry_run: bool = False) -> list:
    """Clean files older than max_age_minutes. Returns list of deleted files."""
    deleted = []
    
    if not dir_path.exists():
        return deleted
    
    for file_path in dir_path.rglob("*"):
        if not file_path.is_file():
            continue
            
        age = get_file_age_minutes(file_path)
        if age > max_age_minutes:
            if dry_run:
                print(f"Would delete: {file_path} (age: {age:.0f}m)")
            else:
                file_path.unlink()
                print(f"Deleted: {file_path}")
            deleted.append(file_path)
    
    return deleted


def cleanup_all(dry_run: bool = False) -> dict:
    """Clean all scratch files (NOT index/ which contains active plan)."""
    results = {"deleted": 0, "freed_bytes": 0}

    if not SCRATCH_DIR.exists():
        print("No .fsctx/scratch/ directory found")
        return results

    for file_path in SCRATCH_DIR.rglob("*"):
        if file_path.is_file():
            size = file_path.stat().st_size
            if dry_run:
                print(f"Would delete: {file_path} ({size:,} bytes)")
            else:
                file_path.unlink()
                print(f"Deleted: {file_path}")
            results["deleted"] += 1
            results["freed_bytes"] += size

    return results


def show_stats():
    """Show current storage statistics."""
    print("=== FewWord Storage Stats ===\n")

    dirs = [
        (SCRATCH_DIR, "Scratch (ephemeral)"),
        (MEMORY_DIR, "Memory (persistent)"),
        (INDEX_DIR, "Index (metadata)"),
    ]

    for dir_path, name in dirs:
        if not dir_path.exists():
            print(f"{name}: Not initialized")
            continue

        total_size = 0
        file_count = 0

        for file_path in dir_path.rglob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size
                file_count += 1

        size_mb = total_size / (1024 * 1024)
        print(f"{name}: {file_count} files, {size_mb:.2f} MB")

    print()


def main():
    parser = argparse.ArgumentParser(description="Clean up scratch files")
    parser.add_argument("--age", type=int, help="Max file age in minutes")
    parser.add_argument("--all", action="store_true", help="Remove all scratch files")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted")
    parser.add_argument("--stats", action="store_true", help="Show storage stats only")
    
    args = parser.parse_args()
    
    if args.stats:
        show_stats()
        return
    
    show_stats()
    
    if args.all:
        print("=== Cleaning All Scratch Files ===\n")
        results = cleanup_all(args.dry_run)
        freed_mb = results["freed_bytes"] / (1024 * 1024)
        print(f"\n{'Would delete' if args.dry_run else 'Deleted'}: {results['deleted']} files ({freed_mb:.2f} MB)")
    else:
        print("=== Cleaning by Retention Policy ===\n")
        total_deleted = 0
        
        for subdir, max_age in RETENTION.items():
            dir_path = SCRATCH_DIR / subdir
            age = args.age if args.age else max_age
            deleted = cleanup_directory(dir_path, age, args.dry_run)
            total_deleted += len(deleted)
        
        print(f"\n{'Would delete' if args.dry_run else 'Deleted'}: {total_deleted} files")


if __name__ == "__main__":
    main()
