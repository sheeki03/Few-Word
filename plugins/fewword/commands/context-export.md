---
description: "Export session history as markdown report"
arguments:
  - name: --all-time
    description: "Export all sessions, not just current"
    required: false
  - name: --output
    description: "Output file path (default: auto-generated)"
    required: false
---

# Context Export

Export session history as a markdown report, saved to FewWord storage with a pointer for retrieval.

## Usage

```bash
/context-export                     # Export current session
/context-export --all-time          # Export all sessions
/context-export --output report.txt # Custom output path
```

## Output

Returns a compact pointer to the exported report:
```
[fw a1b2c3d4] Session export 2026-01-10 12.5KB 245L | /context-open a1b2c3d4
```

## Implementation

```python
#!/usr/bin/env python3
"""Context Export - Export session history as markdown report."""

import json
import os
import re
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

# Add hooks/scripts to path for redaction module import
# This ensures we can use the full Redactor with built-in patterns
_scripts_dir = None
if os.environ.get('CLAUDE_PLUGIN_ROOT'):
    _scripts_dir = Path(os.environ['CLAUDE_PLUGIN_ROOT']) / 'hooks' / 'scripts'
else:
    # Try relative to this file's expected location or cwd
    _cwd = os.environ.get('FEWWORD_CWD', os.getcwd())
    for candidate in [
        Path(_cwd) / 'plugins' / 'fewword' / 'hooks' / 'scripts',
        Path(_cwd) / 'hooks' / 'scripts',
        Path(__file__).parent.parent / 'hooks' / 'scripts' if '__file__' in dir() else None,
    ]:
        if candidate and candidate.exists():
            _scripts_dir = candidate
            break

if _scripts_dir and str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

# Import redaction module (with built-in patterns for secrets)
HAS_REDACTION = False
Redactor = None
try:
    from redaction import Redactor, create_redactor_from_config
    HAS_REDACTION = True
except ImportError:
    pass

# Import shared config loader
HAS_CONFIG_LOADER = False
try:
    from config_loader import get_config
    HAS_CONFIG_LOADER = True
except ImportError:
    pass

def get_cwd():
    """Get working directory with validation."""
    cwd = os.environ.get('FEWWORD_CWD', os.getcwd())
    return os.path.realpath(os.path.abspath(cwd))

def get_session_info(cwd):
    """Get current session info."""
    session_file = Path(cwd) / '.fewword' / 'index' / 'session.json'
    if session_file.exists():
        try:
            return json.loads(session_file.read_text())
        except Exception:
            pass
    return None

def _load_config_from_files(cwd):
    """
    Fallback config loader when config_loader.py unavailable.
    Uses proper precedence: user config -> repo config -> env vars.
    """
    config = {'enabled': True, 'patterns': [], 'replacement': '[REDACTED]'}

    # Load user config first (lowest priority)
    user_paths = [Path.home() / '.fewwordrc.toml', Path.home() / '.fewwordrc.json']
    for cfg_path in user_paths:
        if cfg_path.exists():
            try:
                if cfg_path.suffix == '.toml':
                    try:
                        import tomllib
                        with open(cfg_path, 'rb') as f:
                            data = tomllib.load(f)
                    except ImportError:
                        continue
                else:
                    with open(cfg_path, 'r') as f:
                        data = json.load(f)
                redaction = data.get('redaction', {})
                if 'enabled' in redaction:
                    config['enabled'] = redaction['enabled']
                if 'patterns' in redaction:
                    config['patterns'] = redaction['patterns']
                if 'replacement' in redaction:
                    config['replacement'] = redaction['replacement']
                break
            except Exception:
                continue

    # Load repo config (higher priority, overrides user)
    repo_paths = [Path(cwd) / '.fewwordrc.toml', Path(cwd) / '.fewwordrc.json']
    for cfg_path in repo_paths:
        if cfg_path.exists():
            try:
                if cfg_path.suffix == '.toml':
                    try:
                        import tomllib
                        with open(cfg_path, 'rb') as f:
                            data = tomllib.load(f)
                    except ImportError:
                        continue
                else:
                    with open(cfg_path, 'r') as f:
                        data = json.load(f)
                redaction = data.get('redaction', {})
                if 'enabled' in redaction:
                    config['enabled'] = redaction['enabled']
                if 'patterns' in redaction:
                    config['patterns'] = redaction['patterns']
                if 'replacement' in redaction:
                    config['replacement'] = redaction['replacement']
                break
            except Exception:
                continue

    # Environment overrides (highest priority)
    env_enabled = os.environ.get('FEWWORD_REDACT_ENABLED')
    if env_enabled is not None:
        config['enabled'] = env_enabled.lower() in ('1', 'true', 'yes', 'on')

    env_patterns = os.environ.get('FEWWORD_REDACT_PATTERNS')
    if env_patterns:
        config['patterns'] = [p.strip() for p in env_patterns.split('|') if p.strip()]

    env_replacement = os.environ.get('FEWWORD_REDACT_REPLACEMENT')
    if env_replacement:
        config['replacement'] = env_replacement

    return config

def create_redactor(cwd):
    """
    Create a Redactor instance with built-in patterns + config patterns.

    Uses redaction.py Redactor (has built-in secret patterns) when available,
    falls back to basic implementation otherwise.
    """
    # Get config (try shared loader, fallback to file loading)
    if HAS_CONFIG_LOADER:
        try:
            cfg = get_config(cwd)
            redactor = cfg.get_section('redaction')
        except Exception:
            redactor = _load_config_from_files(cwd)
    else:
        redactor = _load_config_from_files(cwd)

    # Use full Redactor with built-in patterns if available
    if HAS_REDACTION and Redactor:
        return Redactor(
            enabled=redactor.get('enabled', True),
            custom_patterns=redactor.get('patterns', []),
            replacement=redactor.get('replacement', '[REDACTED]')
        )

    # Fallback: basic redactor without built-in patterns
    # (logs warning since secrets may leak)
    class BasicRedactor:
        """Fallback redactor without built-in secret patterns."""
        def __init__(self, config):
            self.enabled = config.get('enabled', True)
            self.patterns = []
            self.replacement = config.get('replacement', '[REDACTED]')
            for p in config.get('patterns', []):
                try:
                    self.patterns.append(re.compile(p))
                except re.error:
                    pass

        def redact(self, text):
            if not self.enabled or not text:
                return text, 0
            result = text
            count = 0
            for pattern in self.patterns:
                result, n = pattern.subn(self.replacement, result)
                count += n
            return result, count

    print("[FewWord] Warning: redaction.py not found, built-in secret patterns unavailable", file=sys.stderr)
    return BasicRedactor(redactor)

def redact_text(text, redactor):
    """Apply redaction using the provided Redactor instance."""
    if not text:
        return text
    result, _ = redactor.redact(text)
    return result

def calculate_age(iso_timestamp):
    """Convert ISO timestamp to human-readable age."""
    try:
        ts = iso_timestamp.replace('Z', '+00:00')
        created = datetime.fromisoformat(ts)
        now = datetime.now(timezone.utc)
        diff = int((now - created).total_seconds())
        if diff < 60:
            return f"{diff}s ago"
        elif diff < 3600:
            return f"{diff // 60}m ago"
        elif diff < 86400:
            return f"{diff // 3600}h ago"
        else:
            return f"{diff // 86400}d ago"
    except (ValueError, TypeError, AttributeError):
        return "?"

def format_bytes(b):
    """Format bytes as human-readable."""
    if b >= 1048576:
        return f"{b / 1048576:.1f}MB"
    elif b >= 1024:
        return f"{b / 1024:.1f}KB"
    else:
        return f"{b}B"

def format_timestamp(iso_timestamp):
    """Format timestamp for display."""
    try:
        ts = iso_timestamp.replace('Z', '+00:00')
        dt = datetime.fromisoformat(ts)
        return dt.astimezone().strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError, AttributeError):
        return "?"

def get_all_manifests(cwd):
    """
    Get paths to current and archived manifests.
    Rotation format: tool_outputs_YYYY-MM.jsonl
    """
    index_dir = Path(cwd) / '.fewword' / 'index'
    manifests = []

    # Current manifest first
    current = index_dir / 'tool_outputs.jsonl'
    if current.exists():
        manifests.append(current)

    # Find archived manifests (tool_outputs_YYYY-MM.jsonl format)
    try:
        archived = sorted(
            index_dir.glob('tool_outputs_*.jsonl'),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        manifests.extend(archived[:10])  # Cap at 10 archives
    except Exception:
        pass

    return manifests

def get_manifest_entries(cwd, session_id=None, all_time=False):
    """Get all manifest entries, optionally filtered by session."""
    entries = []

    # Get manifests to read
    if all_time:
        manifests = get_all_manifests(cwd)
    else:
        manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'
        manifests = [manifest_path] if manifest_path.exists() else []

    for manifest_path in manifests:
        try:
            with open(manifest_path, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        entry_type = entry.get('type', '')

                        # Filter by session for offload/manual/export entries (unless all_time)
                        if session_id and not all_time and entry_type in ('offload', 'manual', 'export'):
                            if entry.get('session_id') != session_id:
                                continue

                        entries.append(entry)
                    except (json.JSONDecodeError, KeyError, TypeError):
                        pass
        except (FileNotFoundError, IOError):
            pass

    return entries

def generate_report(cwd, session_id=None, all_time=False):
    """Generate markdown report of session history."""
    entries = get_manifest_entries(cwd, session_id=None if all_time else session_id, all_time=all_time)

    if not entries:
        return None, "No entries found to export."

    # Create redactor for sanitizing notes/tags/titles (includes built-in patterns)
    redactor = create_redactor(cwd)

    # Separate by type
    offloads = [e for e in entries if e.get('type') == 'offload']
    manuals = [e for e in entries if e.get('type') == 'manual']
    exports = [e for e in entries if e.get('type') == 'export']
    pins = [e for e in entries if e.get('type') == 'pin']
    tags = [e for e in entries if e.get('type') == 'tag']
    notes = [e for e in entries if e.get('type') == 'note']

    # Build pinned IDs by replaying pin/unpin events in order (last event wins)
    # This correctly handles re-pinning after unpin
    # Note: pin entries use pinned_at, unpin entries use unpinned_at
    pin_events = []
    for e in entries:
        if e.get('type') == 'pin':
            pin_events.append((e.get('pinned_at', ''), 'pin', e.get('id', '').upper()))
        elif e.get('type') == 'unpin':
            pin_events.append((e.get('unpinned_at', ''), 'unpin', e.get('id', '').upper()))
    # Filter out events with empty timestamps (malformed entries), then sort
    pin_events = [e for e in pin_events if e[0]]
    pin_events.sort(key=lambda x: x[0])

    currently_pinned = set()
    for _, event_type, event_id in pin_events:
        if event_type == 'pin':
            currently_pinned.add(event_id)
        elif event_type == 'unpin':
            currently_pinned.discard(event_id)

    # Build tags map (with redaction)
    tags_map = defaultdict(set)
    for e in entries:
        if e.get('type') == 'tag':
            hex_id = e.get('id', '').upper()
            redacted_tags = [redact_text(t, redactor) for t in e.get('tags', [])]
            tags_map[hex_id].update(redacted_tags)
        elif e.get('type') == 'tag_remove':
            hex_id = e.get('id', '').upper()
            redacted_tags = set(redact_text(t, redactor) for t in e.get('tags', []))
            tags_map[hex_id] -= redacted_tags

    # Build notes map (with redaction)
    notes_map = defaultdict(list)
    for e in entries:
        if e.get('type') == 'note':
            hex_id = e.get('id', '').upper()
            redacted_note = redact_text(e.get('note', ''), redactor)
            notes_map[hex_id].append(redacted_note)

    # Calculate stats (include all content types)
    all_content = offloads + manuals + exports
    total_bytes = sum(e.get('bytes', 0) for e in all_content)
    total_count = len(all_content)
    failures = [e for e in offloads if e.get('exit_code', 0) != 0]

    # Session-scoped pinned count: count only pinned outputs in this export's scope
    session_output_ids = set(e.get('id', '').upper() for e in all_content)
    session_pinned_count = len(currently_pinned & session_output_ids)

    # Generate report
    lines = []
    now = datetime.now(timezone.utc)
    report_title = "All-Time Export" if all_time else f"Session Export"

    lines.append(f"# FewWord {report_title}")
    lines.append(f"")
    lines.append(f"Generated: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    if session_id and not all_time:
        lines.append(f"Session: {session_id[:8]}")
    lines.append(f"")

    # Summary
    lines.append("## Summary")
    lines.append(f"")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total outputs | {total_count} |")
    lines.append(f"| Tool outputs | {len(offloads)} |")
    lines.append(f"| Manual saves | {len(manuals)} |")
    lines.append(f"| Exports | {len(exports)} |")
    lines.append(f"| Failures | {len(failures)} |")
    lines.append(f"| Total size | {format_bytes(total_bytes)} |")
    lines.append(f"| Pinned | {session_pinned_count} |")
    lines.append(f"")

    # Command breakdown
    if offloads:
        lines.append("## Commands by Frequency")
        lines.append(f"")
        cmd_counts = defaultdict(lambda: {'count': 0, 'failures': 0, 'bytes': 0})
        for e in offloads:
            cmd = e.get('cmd_group') or e.get('cmd', 'unknown')
            cmd_counts[cmd]['count'] += 1
            cmd_counts[cmd]['bytes'] += e.get('bytes', 0)
            if e.get('exit_code', 0) != 0:
                cmd_counts[cmd]['failures'] += 1

        lines.append(f"| Command | Runs | Failures | Size |")
        lines.append(f"|---------|------|----------|------|")
        for cmd, stats in sorted(cmd_counts.items(), key=lambda x: -x[1]['count']):
            lines.append(f"| {cmd} | {stats['count']} | {stats['failures']} | {format_bytes(stats['bytes'])} |")
        lines.append(f"")

    # Timeline (recent 20)
    all_outputs = sorted(all_content, key=lambda e: e.get('created_at', ''), reverse=True)
    if all_outputs:
        lines.append("## Recent Outputs (Last 20)")
        lines.append(f"")
        lines.append(f"| Time | Type | ID | Command/Title | Exit | Size | Tags |")
        lines.append(f"|------|------|-----|---------------|------|------|------|")

        for entry in all_outputs[:20]:
            entry_type = entry.get('type', 'offload')
            hex_id = entry.get('id', '????')[:8]
            time_str = format_timestamp(entry.get('created_at', ''))

            if entry_type == 'offload':
                cmd = entry.get('cmd_group') or entry.get('cmd', '?')
                exit_code = str(entry.get('exit_code', '-'))
                type_label = "tool"
            else:
                # Redact titles for manual/export entries (may contain secrets)
                raw_title = entry.get('title', entry_type)[:30]
                cmd = redact_text(raw_title, redactor)
                exit_code = "-"
                type_label = entry_type

            size = format_bytes(entry.get('bytes', 0))
            entry_tags = ', '.join(sorted(tags_map.get(hex_id.upper(), [])))
            pinned = "[P]" if hex_id.upper() in currently_pinned else ""

            lines.append(f"| {time_str} | {type_label} | {hex_id}{pinned} | {cmd} | {exit_code} | {size} | {entry_tags} |")
        lines.append(f"")

    # Failures section
    if failures:
        lines.append("## Failures")
        lines.append(f"")
        for entry in failures[:10]:
            hex_id = entry.get('id', '????')[:8]
            cmd = entry.get('cmd_group') or entry.get('cmd', '?')
            exit_code = entry.get('exit_code', '?')
            age = calculate_age(entry.get('created_at', ''))
            entry_notes = notes_map.get(hex_id.upper(), [])

            lines.append(f"### [{hex_id}] {cmd} (exit={exit_code}, {age})")
            lines.append(f"")
            lines.append(f"- Size: {format_bytes(entry.get('bytes', 0))}")
            lines.append(f"- Lines: {entry.get('lines', '?')}")
            lines.append(f"- Retrieve: `/context-open {hex_id}`")

            if entry_notes:
                lines.append(f"- Notes:")
                for note in entry_notes:
                    lines.append(f"  - {note}")
            lines.append(f"")

    # Pinned outputs (only show section if there are pinned outputs in scope)
    if session_pinned_count > 0:
        lines.append("## Pinned Outputs")
        lines.append(f"")
        for entry in all_content:
            if entry.get('id', '').upper() in currently_pinned:
                hex_id = entry.get('id', '????')[:8]
                entry_type = entry.get('type', 'offload')

                if entry_type == 'offload':
                    label = entry.get('cmd_group') or entry.get('cmd', '?')
                else:
                    # Redact titles for manual/export entries
                    label = redact_text(entry.get('title', entry_type), redactor)

                lines.append(f"- [{hex_id}] {label} ({format_bytes(entry.get('bytes', 0))})")
        lines.append(f"")

    # Footer
    lines.append("---")
    lines.append(f"")
    lines.append(f"*Generated by FewWord v1.3.4*")

    return '\n'.join(lines), None

def main():
    args = sys.argv[1:]
    cwd = get_cwd()

    # Parse arguments
    all_time = '--all-time' in args
    custom_output = None

    i = 0
    while i < len(args):
        if args[i] == '--output' and i + 1 < len(args):
            custom_output = args[i + 1]
            i += 2
        else:
            i += 1

    # Get session info
    session = get_session_info(cwd)
    session_id = session.get('session_id') if session else None

    if not session_id and not all_time:
        print("No active session found.")
        print("Use --all-time to export all historical data.")
        sys.exit(1)

    # Generate report
    report, error = generate_report(cwd, session_id=session_id, all_time=all_time)

    if error:
        print(f"Error: {error}")
        sys.exit(1)

    # Generate ID and filename
    event_id = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    ts = now.strftime('%Y%m%d_%H%M%S')
    date_str = now.strftime('%Y-%m-%d')

    if custom_output:
        output_path = Path(custom_output)
    else:
        # Save to scratch directory with .txt extension for cleanup compatibility
        scratch_dir = Path(cwd) / '.fewword' / 'scratch' / 'tool_outputs'
        scratch_dir.mkdir(parents=True, exist_ok=True)
        filename = f"export_{ts}_{event_id}_session_{date_str}.txt"
        output_path = scratch_dir / filename

    # Write report
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report)
    except Exception as e:
        print(f"Error writing report: {e}")
        sys.exit(1)

    # Calculate metrics
    byte_count = len(report.encode('utf-8'))
    line_count = report.count('\n') + 1

    # Create manifest entry (only for auto-generated paths)
    if not custom_output:
        entry = {
            "type": "export",
            "id": event_id,
            "session_id": session_id or "all",
            "created_at": now.isoformat().replace('+00:00', 'Z'),
            "title": f"Session export {date_str}",
            "source": "context-export",
            "bytes": byte_count,
            "lines": line_count,
            "path": f".fewword/scratch/tool_outputs/{filename}"
        }

        manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'
        manifest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(manifest_path, 'a') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception as e:
            print(f"Warning: Could not write manifest entry: {e}", file=sys.stderr)

        # Output pointer
        size_str = format_bytes(byte_count)
        title = f"Session export {date_str}"
        print(f"[fw {event_id}] {title} {size_str} {line_count}L | /context-open {event_id}")
    else:
        size_str = format_bytes(byte_count)
        print(f"Exported to: {output_path}")
        print(f"Size: {size_str}, {line_count} lines")

if __name__ == '__main__':
    main()
```

## Output Example

The exported report looks like:

```markdown
# FewWord Session Export

Generated: 2026-01-10 14:30:00 UTC
Session: b719edab

## Summary

| Metric | Value |
|--------|-------|
| Total outputs | 42 |
| Tool outputs | 38 |
| Manual saves | 4 |
| Failures | 8 |
| Total size | 15.3MB |
| Pinned | 3 |

## Commands by Frequency

| Command | Runs | Failures | Size |
|---------|------|----------|------|
| pytest | 19 | 5 | 8.2MB |
| npm | 8 | 1 | 4.1MB |
| cargo | 7 | 2 | 2.8MB |

## Recent Outputs (Last 20)

| Time | Type | ID | Command/Title | Exit | Size | Tags |
|------|------|-----|---------------|------|------|------|
| 2026-01-10 14:25:00 | tool | A1B2C3D4[P] | pytest | 1 | 2.1MB | regression |
| 2026-01-10 14:20:00 | manual | E5F6G7H8 | API analysis | - | 45KB | |
...

## Failures

### [A1B2C3D4] pytest (exit=1, 5m ago)

- Size: 2.1MB
- Lines: 4523
- Retrieve: `/context-open A1B2C3D4`
- Notes:
  - Regression in auth module

---

*Generated by FewWord v1.3.4*
```

## Notes

- Reports saved to `.fewword/scratch/tool_outputs/` with `.txt` extension for cleanup compatibility
- Creates `export` type manifest entry for tracking
- Use `--all-time` to include all historical sessions
- Use `--output` for custom output path (no manifest entry created)
- Pinned outputs marked with `[P]` suffix
