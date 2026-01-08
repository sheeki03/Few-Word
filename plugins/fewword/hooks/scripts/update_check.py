#!/usr/bin/env python3
"""
SessionStart hook: Check for plugin updates.

Compares installed version with latest on GitHub and notifies user if outdated.
Runs silently if up-to-date or if check fails (best-effort, non-blocking).
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
    # CLAUDE_PLUGIN_ROOT points to the plugin directory
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
        parts = v.split('.')
        return tuple(int(p) for p in parts)
    except (ValueError, AttributeError):
        return (0, 0, 0)


def main():
    """Check for updates and notify if newer version available."""
    # Skip if disabled
    if os.environ.get('FEWWORD_DISABLE_UPDATE_CHECK'):
        return

    installed = get_installed_version()
    if not installed:
        return

    latest = get_latest_version()
    if not latest:
        return  # Network issue, fail silently

    # Compare versions
    if parse_version(latest) > parse_version(installed):
        print(f"[fewword] Update available: {installed} → {latest}")
        print(f"[fewword] Run: claude plugin update fewword@sheeki03-Few-Word")


if __name__ == "__main__":
    main()
