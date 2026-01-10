---
description: "Run FewWord self-diagnostics to check health and fix common issues"
---

# FewWord Doctor

Run a health check on FewWord installation and optionally fix common issues.

## Usage

```bash
# Basic health check
/fewword-doctor

# Attempt to fix common issues
/fewword-doctor --fix
```

## Implementation

Run this Python script to check FewWord health:

```python
#!/usr/bin/env python3
"""FewWord Doctor - Self-diagnostics and repair."""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

def get_cwd():
    return os.environ.get('FEWWORD_CWD', os.getcwd())

def check_health(fix=False):
    cwd = Path(get_cwd())
    issues = []
    fixed = []

    print("FewWord Health Check")
    print("=" * 50)

    # 1. Check scratch directory
    scratch_dir = cwd / '.fewword' / 'scratch' / 'tool_outputs'
    if scratch_dir.exists():
        # Check if writable
        test_file = scratch_dir / '.write_test'
        try:
            test_file.write_text('test')
            test_file.unlink()
            writable = True
        except (OSError, PermissionError, IOError):
            writable = False

        # Get size (P2 fix: handle permission/access errors gracefully)
        total_bytes = 0
        for f in scratch_dir.rglob('*'):
            try:
                if f.is_file():
                    total_bytes += f.stat().st_size
            except (OSError, PermissionError):
                pass  # Skip files we can't access
        total_mb = total_bytes / (1024 * 1024)
        cap_mb = int(os.environ.get('FEWWORD_SCRATCH_MAX_MB', 250))
        pct = (total_mb / cap_mb) * 100 if cap_mb > 0 else 0

        status = "exists, writable" if writable else "exists, NOT WRITABLE"
        print(f"Scratch dir: {status}, {total_mb:.1f}MB used ({pct:.0f}% of {cap_mb}MB cap)")

        if not writable:
            issues.append("Scratch directory not writable")
            if fix:
                try:
                    scratch_dir.chmod(0o755)
                    fixed.append("Fixed scratch directory permissions")
                except (OSError, PermissionError):
                    pass
    else:
        print("Scratch dir: MISSING")
        issues.append("Scratch directory missing")
        if fix:
            try:
                scratch_dir.mkdir(parents=True, exist_ok=True)
                fixed.append("Created scratch directory")
            except (OSError, PermissionError):
                pass

    # 2. Check symlinks
    latest_txt = scratch_dir / 'LATEST.txt'
    if latest_txt.exists() or latest_txt.is_symlink():
        if latest_txt.is_symlink():
            target = latest_txt.resolve() if latest_txt.exists() else None
            if target and target.exists():
                print(f"Symlinks: native (LATEST.txt -> {target.name})")
            else:
                print("Symlinks: DANGLING (target missing)")
                issues.append("LATEST.txt symlink is dangling")
                if fix:
                    try:
                        latest_txt.unlink()
                        fixed.append("Removed dangling LATEST.txt symlink")
                    except (OSError, PermissionError):
                        pass
        else:
            print("Symlinks: pointer fallback mode")
    else:
        print("Symlinks: not created yet")

    # 3. Check manifest
    manifest_path = cwd / '.fewword' / 'index' / 'tool_outputs.jsonl'
    if manifest_path.exists():
        line_count = 0
        malformed = 0
        offload_count = 0

        with open(manifest_path, 'r') as f:
            for line in f:
                line_count += 1
                try:
                    entry = json.loads(line)
                    if entry.get('type') == 'offload':
                        offload_count += 1
                except json.JSONDecodeError:
                    malformed += 1

        status = f"{line_count} entries, {malformed} malformed"
        if malformed > 0:
            print(f"Manifest: {status}")
            issues.append(f"{malformed} malformed manifest entries")
        else:
            print(f"Manifest: {offload_count} offloads, {line_count} total entries")
    else:
        print("Manifest: MISSING")
        issues.append("Manifest file missing")
        if fix:
            try:
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.touch()
                fixed.append("Created empty manifest file")
            except (OSError, PermissionError):
                pass

    # 4. Check session
    session_path = cwd / '.fewword' / 'index' / 'session.json'
    if session_path.exists():
        try:
            with open(session_path, 'r') as f:
                session = json.load(f)
            session_id = session.get('session_id', 'unknown')
            started = session.get('started_at', '')
            if started:
                try:
                    start_dt = datetime.fromisoformat(started.replace('Z', '+00:00'))
                    age = datetime.now(timezone.utc) - start_dt
                    hours = age.total_seconds() / 3600
                    age_str = f"{hours:.1f}h ago" if hours < 24 else f"{hours/24:.1f}d ago"
                except (ValueError, TypeError, AttributeError):
                    age_str = started
            else:
                age_str = 'unknown'
            print(f"Session: {session_id[:8]} (started {age_str})")
        except (json.JSONDecodeError, IOError, OSError):
            print("Session: CORRUPT")
            issues.append("Session file corrupt")
    else:
        print("Session: MISSING")
        issues.append("Session file missing")

    # 5. Check retention settings
    success_min = int(os.environ.get('FEWWORD_RETENTION_SUCCESS_MIN', 1440))
    fail_min = int(os.environ.get('FEWWORD_RETENTION_FAIL_MIN', 2880))
    print(f"Retention: {success_min//60}h success, {fail_min//60}h failure TTL")

    # 6. Check .gitignore
    gitignore_path = cwd / '.gitignore'
    fewword_in_gitignore = False
    if gitignore_path.exists():
        content = gitignore_path.read_text()
        if '.fewword/scratch' in content or '.fewword/' in content:
            fewword_in_gitignore = True

    if fewword_in_gitignore:
        print(".gitignore: .fewword patterns present")
    else:
        print(".gitignore: MISSING .fewword patterns")
        issues.append(".gitignore missing .fewword entries")
        if fix:
            try:
                with open(gitignore_path, 'a') as f:
                    f.write("\n# FewWord context engineering\n.fewword/scratch/\n.fewword/index/\n")
                fixed.append("Added .fewword to .gitignore")
            except (OSError, PermissionError, IOError):
                pass

    # 7. Check for orphan files (files in scratch not in manifest)
    if manifest_path.exists() and scratch_dir.exists():
        manifest_ids = set()
        with open(manifest_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if 'id' in entry:
                        manifest_ids.add(entry['id'].lower())
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass

        orphan_count = 0
        for f in scratch_dir.glob('*_exit*.txt'):
            # Extract ID from filename: cmd_ts_ID_exitN.txt
            parts = f.stem.split('_')
            if len(parts) >= 4:
                file_id = parts[-2].lower()  # ID is second to last
                if file_id not in manifest_ids and len(file_id) == 8:
                    orphan_count += 1

        if orphan_count > 0:
            print(f"Orphan files: {orphan_count} files not in manifest")
            issues.append(f"{orphan_count} orphan files")
        else:
            print("Orphan files: none detected")

    # 8. Check hooks
    # P2 fix: Don't use __file__ as it may not exist when run as embedded script
    hooks_json = cwd / 'plugins' / 'fewword' / 'hooks' / 'hooks.json'
    # Try standard install locations if not found
    if not hooks_json.exists():
        # Try relative to cwd
        alt_paths = [
            cwd / '.fewword' / 'hooks' / 'hooks.json',
            Path.home() / '.config' / 'fewword' / 'hooks.json',
        ]
        for alt in alt_paths:
            if alt.exists():
                hooks_json = alt
                break

    if hooks_json.exists():
        try:
            with open(hooks_json, 'r') as f:
                hooks = json.load(f)
            hook_count = sum(len(v) if isinstance(v, list) else 1 for v in hooks.values())
            print(f"Hooks: {hook_count} hooks configured")
        except (json.JSONDecodeError, IOError, OSError, TypeError):
            print("Hooks: config exists but unreadable")
    else:
        print("Hooks: config not found (may be normal)")

    # Summary
    print()
    print("=" * 50)

    if issues:
        print(f"Issues found: {len(issues)}")
        for issue in issues:
            print(f"  - {issue}")

        if fixed:
            print()
            print(f"Fixed: {len(fixed)}")
            for f in fixed:
                print(f"  + {f}")
        elif not fix:
            print()
            print("Run '/fewword-doctor --fix' to attempt repairs")
    else:
        print("All checks passed!")

# Parse args
fix_mode = '--fix' in sys.argv

check_health(fix=fix_mode)
```

## What Gets Checked

| Check | Description |
|-------|-------------|
| Scratch dir | Exists, writable, size vs cap |
| Symlinks | Native vs pointer fallback, dangling links |
| Manifest | Entry count, malformed lines |
| Session | Current session ID, age |
| Retention | TTL settings |
| .gitignore | Contains .fewword patterns |
| Orphan files | Files in scratch not in manifest |
| Hooks | Hook configuration exists |

## Safe Repairs (--fix)

The `--fix` flag only performs **safe repairs**:

| Repair | What It Does |
|--------|--------------|
| Create missing dirs | `mkdir -p .fewword/scratch/tool_outputs` |
| Fix permissions | `chmod 755` on scratch dir |
| Prune dangling symlinks | Remove LATEST.txt if target missing |
| Create empty manifest | `touch .fewword/index/tool_outputs.jsonl` |
| Update .gitignore | Append .fewword patterns |

**`--fix` does NOT:**
- Rewrite or "repair" manifest history
- Delete files without user confirmation
- Modify manifest entries in place

## Output Example

```
FewWord Health Check
==================================================
Scratch dir: exists, writable, 45.2MB used (18% of 250MB cap)
Symlinks: native (LATEST.txt -> pytest_20260109_143022_a1b2c3d4_exit0.txt)
Manifest: 1247 offloads, 1302 total entries
Session: b719edab (started 2.1h ago)
Retention: 24h success, 48h failure TTL
.gitignore: .fewword patterns present
Orphan files: none detected
Hooks: 5 hooks configured

==================================================
All checks passed!
```
