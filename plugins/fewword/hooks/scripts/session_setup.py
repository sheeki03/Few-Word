#!/usr/bin/env python3
"""
SessionStart hook: Create FewWord directory structure and update .gitignore.

Cross-platform: Works on Windows, macOS, and Linux.
"""

import os
from pathlib import Path


def main():
    """Create FewWord directories and update .gitignore if needed."""
    cwd = os.environ.get('FEWWORD_CWD', os.getcwd())
    base = Path(cwd) / '.fewword'

    # Create directory structure
    directories = [
        base / 'scratch' / 'tool_outputs',
        base / 'scratch' / 'subagents',
        base / 'memory' / 'plans',
        base / 'memory' / 'history',
        base / 'memory' / 'patterns',
        base / 'memory' / 'pinned',
        base / 'index',
    ]

    for d in directories:
        d.mkdir(parents=True, exist_ok=True)

    # Update .gitignore if in a git repo
    git_dir = Path(cwd) / '.git'
    gitignore = Path(cwd) / '.gitignore'

    if git_dir.is_dir():
        # Check if .fewword is already in .gitignore
        needs_update = True
        if gitignore.exists():
            try:
                content = gitignore.read_text()
                # Check for .fewword entry (with or without trailing slash)
                for line in content.splitlines():
                    line = line.strip()
                    if line in ('.fewword', '.fewword/', '.fewword/*'):
                        needs_update = False
                        break
            except (OSError, IOError):
                pass

        if needs_update:
            try:
                with open(gitignore, 'a') as f:
                    f.write('\n# FewWord context plugin\n')
                    f.write('.fewword/scratch/\n')
                    f.write('.fewword/index/\n')
                print('[fewword] Added to .gitignore')
            except (OSError, IOError):
                pass


if __name__ == '__main__':
    main()
