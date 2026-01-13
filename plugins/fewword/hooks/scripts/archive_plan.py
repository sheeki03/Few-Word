#!/usr/bin/env python3
"""
SessionEnd hook: Archive completed plans.

Cross-platform replacement for the bash one-liner that had quoting issues.
Fixes: GitHub Issue #16 - EOF error with nested quotes on some platforms.
"""

import os
import shutil
from pathlib import Path
from datetime import datetime


def main():
    """Archive completed plan files on session end."""
    cwd = os.environ.get('FEWWORD_CWD', os.getcwd())
    plan_file = Path(cwd) / '.fewword' / 'index' / 'current_plan.yaml'

    # Check if plan file exists
    if not plan_file.exists():
        return

    # Check if plan is completed
    try:
        content = plan_file.read_text(encoding='utf-8')
        if 'status: completed' not in content:
            return
    except (OSError, UnicodeDecodeError):
        return

    # Create archive directory
    archive_dir = Path(cwd) / '.fewword' / 'memory' / 'plans'
    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    # Generate timestamp for archive filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_file = archive_dir / f'archived_{timestamp}.yaml'

    # Move the plan file to archive
    try:
        shutil.move(str(plan_file), str(archive_file))
        print('[fewword] Archived completed plan')
    except OSError:
        pass  # Best effort - don't fail hook on archive error


if __name__ == '__main__':
    main()
