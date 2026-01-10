#!/usr/bin/env python3
"""
SessionStart hook: Check for plugin updates.

Compares installed version with latest on GitHub and notifies user if outdated.
Displays notification directly in terminal via /dev/tty on every session start.
"""

import os
import json
import urllib.request
import urllib.error
from pathlib import Path


GITHUB_VERSION_URL = "https://raw.githubusercontent.com/sheeki03/Few-Word/main/plugins/fewword/.claude-plugin/plugin.json"
CHECK_TIMEOUT = 3  # seconds


def get_installed_version() -> str | None:
    """Read installed version from plugin.json."""
    plugin_root = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
    if not plugin_root:
        return None

    plugin_json = Path(plugin_root) / '.claude-plugin' / 'plugin.json'
    try:
        with open(plugin_json, 'r') as f:
            data = json.load(f)
            return data.get('version') if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def get_latest_version() -> str | None:
    """Fetch latest version from GitHub."""
    try:
        req = urllib.request.Request(
            GITHUB_VERSION_URL,
            headers={'User-Agent': 'FewWord-UpdateCheck'}
        )
        with urllib.request.urlopen(req, timeout=CHECK_TIMEOUT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data.get('version') if isinstance(data, dict) else None
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None


def parse_version(v: str) -> tuple:
    """Parse version string to comparable tuple."""
    try:
        return tuple(int(p) for p in v.split('.'))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def notify_user(installed: str, latest: str) -> None:
    """Display update notification in terminal."""
    lines = [
        f"FewWord plugin update: v{installed} → v{latest}",
        "Run: /fewword:update",
    ]
    border = '=' * max(len(line) for line in lines)
    message = '\n'.join([border, *lines, border])

    # Try writing directly to terminal (visible to user)
    tty_path = 'CONOUT$' if os.name == 'nt' else '/dev/tty'
    try:
        with open(tty_path, 'w') as tty:
            # Add color if terminal supports it
            if os.isatty(tty.fileno()):
                message = f"\033[1;33m{message}\033[0m"
            tty.write(f"\n{message}\n")
            tty.flush()
            return
    except OSError:
        pass

    # Fallback: stdout (goes to system reminders)
    print(f"[fewword] Update: v{installed} → v{latest}")
    print(f"[fewword] Run: /fewword:update")


def main():
    """Check for updates and notify if newer version available."""
    if os.environ.get('FEWWORD_DISABLE_UPDATE_CHECK'):
        return

    installed = get_installed_version()
    if not installed:
        return

    latest = get_latest_version()
    if not latest:
        return  # Network issue, fail silently

    if parse_version(latest) > parse_version(installed):
        notify_user(installed, latest)


if __name__ == "__main__":
    main()
