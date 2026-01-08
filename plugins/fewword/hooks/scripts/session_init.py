#!/usr/bin/env python3
"""
SessionStart hook: Initialize session ID for FewWord.

Generates a unique session_id and writes it to .fewword/index/session.json.
This enables per-session stats in /fewword-stats.

Runs on SessionStart before other hooks.
"""

import os
import json
import uuid
from pathlib import Path
from datetime import datetime


def main():
    """Generate session ID and write to session.json."""
    cwd = os.getcwd()
    index_dir = Path(cwd) / '.fewword' / 'index'
    session_file = index_dir / 'session.json'

    # Create index directory if needed
    index_dir.mkdir(parents=True, exist_ok=True)

    # Generate new session ID
    session_id = uuid.uuid4().hex[:12]
    started_at = datetime.utcnow().isoformat() + 'Z'

    session_data = {
        'session_id': session_id,
        'started_at': started_at
    }

    # Write session file (overwrite any existing)
    try:
        with open(session_file, 'w') as f:
            json.dump(session_data, f)
    except OSError:
        pass  # Best effort, don't fail the session


def get_session_id() -> str | None:
    """Read current session ID from session.json.

    Used by offload_bash.py to include session_id in manifest entries.
    Returns None if session file doesn't exist.
    """
    cwd = os.getcwd()
    session_file = Path(cwd) / '.fewword' / 'index' / 'session.json'

    try:
        with open(session_file, 'r') as f:
            data = json.load(f)
            return data.get('session_id')
    except (OSError, json.JSONDecodeError):
        return None


if __name__ == "__main__":
    main()
