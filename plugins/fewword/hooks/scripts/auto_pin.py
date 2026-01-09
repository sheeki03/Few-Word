#!/usr/bin/env python3
"""
FewWord Auto-Pin Module

Automatically pins outputs based on configured rules.
Called after command execution with output details.

Auto-pin triggers:
- on_fail: Pin all failures (exit != 0)
- match: Pin if output matches regex pattern
- cmds: Pin specific commands
- exit_codes: Pin specific exit codes
- size_min: Pin outputs larger than threshold

Constraints:
- Respects deny-cmd mode (won't pin what wasn't stored)
- Respects redaction (pinned files are already redacted)
- max_files limit prevents runaway pinning
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Optional


def get_cwd():
    """Get current working directory."""
    return os.environ.get('FEWWORD_CWD', os.getcwd())


def count_auto_pinned(cwd: str) -> int:
    """Count number of auto-pinned files in manifest."""
    manifest = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'
    count = 0

    if not manifest.exists():
        return 0

    try:
        with open(manifest, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get('type') == 'pin' and entry.get('auto_pinned'):
                        count += 1
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except (FileNotFoundError, OSError):
        pass

    return count


def should_auto_pin(
    exit_code: int,
    cmd: str,
    cmd_group: str,
    output_bytes: int,
    output_content: Optional[str],
    config: Dict,
    cwd: str
) -> tuple[bool, str]:
    """
    Determine if output should be auto-pinned.

    Returns (should_pin, reason).
    """
    auto_pin_config = config.get('auto_pin', {})

    # Check if auto-pin is disabled
    if not any([
        auto_pin_config.get('on_fail'),
        auto_pin_config.get('match'),
        auto_pin_config.get('cmds'),
        auto_pin_config.get('exit_codes'),
        auto_pin_config.get('size_min')
    ]):
        return False, ""

    # Check max_files limit
    max_files = auto_pin_config.get('max_files', 50)
    current_count = count_auto_pinned(cwd)
    if current_count >= max_files:
        return False, f"max auto-pinned files reached ({max_files})"

    # Check on_fail
    if auto_pin_config.get('on_fail') and exit_code != 0:
        return True, "auto_pin.on_fail"

    # Check exit_codes
    exit_codes = auto_pin_config.get('exit_codes', [])
    exit_codes = exit_codes if isinstance(exit_codes, (list, tuple, set)) else [exit_codes]
    if exit_codes and exit_code in exit_codes:
        return True, f"auto_pin.exit_codes ({exit_code})"

    # Check cmds
    cmds = auto_pin_config.get('cmds', [])
    cmds = cmds if isinstance(cmds, (list, tuple, set)) else [cmds]
    if cmds and (cmd in cmds or cmd_group in cmds):
        return True, f"auto_pin.cmds ({cmd})"

    # Check size_min
    size_min = auto_pin_config.get('size_min', 0)
    if size_min and output_bytes >= size_min:
        return True, f"auto_pin.size_min ({output_bytes} >= {size_min})"

    # Check match pattern
    match_pattern = auto_pin_config.get('match', '')
    if match_pattern and output_content:
        try:
            if re.search(match_pattern, output_content):
                return True, f"auto_pin.match ({match_pattern})"
        except re.error:
            pass

    return False, ""


def perform_auto_pin(
    output_id: str,
    output_path: str,
    reason: str,
    cwd: str
) -> bool:
    """
    Perform auto-pin: copy to memory/pinned and record in manifest.

    Returns True if successful.
    """
    source = Path(cwd) / output_path
    if not source.exists():
        return False

    # Create pinned directory
    pinned_dir = Path(cwd) / '.fewword' / 'memory' / 'pinned'
    pinned_dir.mkdir(parents=True, exist_ok=True)

    # Copy file to pinned (don't move - leave in scratch until TTL)
    # Include output_id in filename to prevent collisions (same cmd can have multiple pinned outputs)
    stem = source.stem  # filename without extension
    suffix = source.suffix  # .txt
    dest = pinned_dir / f"{stem}_{output_id}{suffix}"
    try:
        shutil.copy2(str(source), str(dest))
    except (OSError, IOError, PermissionError):
        return False

    # Record pin in manifest
    manifest = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'
    pin_entry = {
        'type': 'pin',
        'id': output_id.upper(),
        'pinned_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'pinned_path': str(dest.relative_to(cwd)),
        'auto_pinned': True,
        'reason': reason
    }

    # P1 fix #27: json.dumps() never raises JSONDecodeError - catch TypeError for non-serializable objects
    try:
        manifest.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest, 'a') as f:
            f.write(json.dumps(pin_entry) + '\n')
        return True
    except (IOError, OSError, TypeError):
        return False


def auto_pin_check(
    output_id: str,
    output_path: str,
    exit_code: int,
    cmd: str,
    cmd_group: str,
    output_bytes: int,
    config: Dict,
    cwd: str
) -> Optional[str]:
    """
    Check and perform auto-pin if rules match.

    Returns reason if pinned, None otherwise.
    """
    # Read output content for pattern matching (only if match pattern exists)
    output_content = None
    match_pattern = config.get('auto_pin', {}).get('match', '')
    if match_pattern:
        full_path = Path(cwd) / output_path
        if full_path.exists():
            try:
                # Only read first 100KB for pattern matching
                with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                    output_content = f.read(102400)
            except (FileNotFoundError, OSError, UnicodeDecodeError):
                pass

    should_pin, reason = should_auto_pin(
        exit_code=exit_code,
        cmd=cmd,
        cmd_group=cmd_group,
        output_bytes=output_bytes,
        output_content=output_content,
        config=config,
        cwd=cwd
    )

    if should_pin:
        if perform_auto_pin(output_id, output_path, reason, cwd):
            return reason

    return None


# === CLI ===

def main():
    """CLI for testing auto-pin."""
    if len(sys.argv) < 2:
        print("Usage: auto_pin.py <command>")
        print("")
        print("Commands:")
        print("  check <id> <path> <exit> <cmd> <cmd_group> <bytes>  Check if should auto-pin")
        print("  count [cwd]                                         Count auto-pinned files")
        sys.exit(1)

    command = sys.argv[1]

    if command == 'check':
        if len(sys.argv) < 8:
            print("Usage: auto_pin.py check <id> <path> <exit> <cmd> <cmd_group> <bytes>")
            sys.exit(1)

        output_id = sys.argv[2]
        output_path = sys.argv[3]
        try:
            exit_code = int(sys.argv[4])
        except ValueError:
            print("Invalid exit code: expected integer")
            sys.exit(1)
        cmd = sys.argv[5]
        cmd_group = sys.argv[6]
        try:
            output_bytes = int(sys.argv[7])
        except ValueError:
            print("Invalid output_bytes: expected integer")
            sys.exit(1)
        cwd = get_cwd()

        # Load config
        try:
            from config_loader import get_config
            config = get_config(cwd).to_dict()
        except ImportError:
            config = {'auto_pin': {}}

        result = auto_pin_check(
            output_id=output_id,
            output_path=output_path,
            exit_code=exit_code,
            cmd=cmd,
            cmd_group=cmd_group,
            output_bytes=output_bytes,
            config=config,
            cwd=cwd
        )

        if result:
            print(f"Auto-pinned: {result}")
        else:
            print("Not auto-pinned")

    elif command == 'count':
        cwd = sys.argv[2] if len(sys.argv) > 2 else get_cwd()
        count = count_auto_pinned(cwd)
        print(f"Auto-pinned files: {count}")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == '__main__':
    main()
