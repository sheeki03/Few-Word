#!/usr/bin/env python3
"""
SessionStart hook: Check for plugin updates.

Compares installed version with latest on GitHub and notifies user if outdated.
Runs silently if up-to-date or if check fails (best-effort, non-blocking).
"""

import os
import json
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path


GITHUB_VERSION_URL = "https://raw.githubusercontent.com/sheeki03/Few-Word/main/plugins/fewword/.claude-plugin/plugin.json"
CHECK_TIMEOUT = 3  # seconds
NOTIFY_INTERVAL_SECONDS = 24 * 60 * 60


def is_truthy(value: str | None) -> bool:
    """Return True for common truthy env values."""
    if value is None:
        return False
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def notifications_enabled() -> bool:
    """Allow update notifications by default; opt-out via env."""
    if is_truthy(os.environ.get('FEWWORD_DISABLE_UPDATE_NOTIFY')):
        return False
    return True


def open_notification_tty():
    """Best-effort handle to the user's terminal for visible notifications."""
    if os.environ.get('FEWWORD_DISABLE_TTY_NOTIFY'):
        return None

    if os.name == 'nt':
        tty_path = 'CONOUT$'
    else:
        tty_path = '/dev/tty'

    try:
        return open(tty_path, 'w')
    except OSError:
        return None


def notify_via_system(title: str, body: str) -> bool:
    """Try OS notification if available."""
    if os.environ.get('FEWWORD_DISABLE_OS_NOTIFY'):
        return False

    safe_title = title.replace('"', '\\"')
    safe_body = body.replace('"', '\\"')

    if sys.platform.startswith('win'):
        ps = shutil.which('powershell') or shutil.which('pwsh')
        if ps:
            def ps_quote(value: str) -> str:
                return "'" + value.replace("'", "''") + "'"

            ps_title = ps_quote(title)
            ps_body = ps_quote(body)
            script = (
                f"$Title = {ps_title};"
                f"$Body = {ps_body};"
                "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
                "$template = [Windows.UI.Notifications.ToastTemplateType]::ToastText02;"
                "$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($template);"
                "$textNodes = $xml.GetElementsByTagName('text');"
                "$textNodes.Item(0).AppendChild($xml.CreateTextNode($Title)) > $null;"
                "$textNodes.Item(1).AppendChild($xml.CreateTextNode($Body)) > $null;"
                "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml);"
                "$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('FewWord');"
                "$notifier.Show($toast);"
            )
            result = subprocess.run(
                [ps, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return result.returncode == 0

    if sys.platform == 'darwin' and shutil.which('osascript'):
        script = f'display notification "{safe_body}" with title "{safe_title}"'
        subprocess.run(
            ['osascript', '-e', script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return True

    if shutil.which('notify-send'):
        subprocess.run(
            ['notify-send', safe_title, safe_body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return True

    return False


def notify_user(installed: str, latest: str) -> None:
    """Send a visible notification about available update."""
    title = "FewWord Plugin Update"
    body = f"v{latest} available. Run /update"
    update_cmd = "claude plugin update fewword@sheeki03-Few-Word"

    # Try TTY first (direct terminal output)
    tty = open_notification_tty()
    if tty:
        try:
            lines = [
                f"FewWord plugin update: v{installed} → v{latest}",
                f"Run: {update_cmd}",
            ]
            border = '=' * max(len(line) for line in lines)
            message = '\n'.join([border, *lines, border])
            if os.isatty(tty.fileno()):
                message = f"\033[1;33m{message}\033[0m"
            tty.write(f"\n{message}\n")
            tty.flush()
            return
        finally:
            tty.close()

    # Try OS notification (macOS/Linux/Windows)
    if notify_via_system(title, body):
        return

    # Fallback: stdout (captured in system reminders)
    print(f"[fewword] Update: v{installed} → v{latest}")
    print(f"[fewword] Run: {update_cmd}")


def get_state_path() -> Path | None:
    """Return the path for notification state, or None if unavailable."""
    if sys.platform.startswith('win'):
        base = os.environ.get('APPDATA')
        if base:
            return Path(base) / 'fewword' / 'update_check.json'
        return Path.home() / 'fewword' / 'update_check.json'

    base = os.environ.get('XDG_CONFIG_HOME')
    if base:
        return Path(base) / 'fewword' / 'update_check.json'

    return Path.home() / '.config' / 'fewword' / 'update_check.json'


def load_state(path: Path | None) -> dict:
    """Load state from disk."""
    if not path:
        return {}
    try:
        with open(path, 'r') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(path: Path | None, state: dict) -> None:
    """Persist state to disk."""
    if not path:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(state, f)
    except OSError:
        return


def should_notify(state: dict, now: float) -> bool:
    """Return True if notification should fire."""
    last_ts = state.get('last_notified_at')
    if last_ts is None:
        return True
    return (now - float(last_ts)) >= NOTIFY_INTERVAL_SECONDS


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

    if not notifications_enabled():
        return

    installed = get_installed_version()
    if not installed:
        return

    latest = get_latest_version()
    if not latest:
        return  # Network issue, fail silently

    # Compare versions
    if parse_version(latest) > parse_version(installed):
        now = time.time()
        state_path = get_state_path()
        state = load_state(state_path)
        if not should_notify(state, now):
            return
        notify_user(installed, latest)
        save_state(state_path, {
            'last_notified_at': now,
            'last_notified_version': latest,
        })


if __name__ == "__main__":
    main()
