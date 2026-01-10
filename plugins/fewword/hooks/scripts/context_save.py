#!/usr/bin/env python3
"""Manual content offload to FewWord scratch."""

import json
import os
import re
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone

# Add hooks/scripts to path for shared module imports
_scripts_dir = None
if os.environ.get('CLAUDE_PLUGIN_ROOT'):
    _scripts_dir = Path(os.environ['CLAUDE_PLUGIN_ROOT']) / 'hooks' / 'scripts'
else:
    # Try relative to cwd or file location
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
    from redaction import Redactor
    HAS_REDACTION = True
except ImportError:
    pass

# Import shared config loader for consistent precedence
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

def sanitize_for_filename(title: str) -> str:
    """Sanitize title for safe filename use only (not for storage)."""
    # Remove dangerous chars for filename
    safe = re.sub(r'[^\w\s\-]', '', title)
    safe = re.sub(r'\s+', '_', safe)
    return safe[:40]  # Cap length for filename

def _load_config_from_files(cwd: str) -> dict:
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

def create_redactor(cwd: str):
    """
    Create a Redactor instance with built-in patterns + config patterns.

    Uses redaction.py Redactor (has built-in secret patterns) when available,
    falls back to basic implementation otherwise.
    """
    # Get config (try shared loader, fallback to file loading)
    if HAS_CONFIG_LOADER:
        try:
            cfg = get_config(cwd)
            redaction_config = cfg.get_section('redaction')
        except Exception:
            redaction_config = _load_config_from_files(cwd)
    else:
        redaction_config = _load_config_from_files(cwd)

    # Use full Redactor with built-in patterns if available
    if HAS_REDACTION and Redactor:
        return Redactor(
            enabled=redaction_config.get('enabled', True),
            custom_patterns=redaction_config.get('patterns', []),
            replacement=redaction_config.get('replacement', '[REDACTED]')
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
    return BasicRedactor(redaction_config)

def apply_redaction(content: str, cwd: str) -> tuple:
    """Apply redaction using shared Redactor. Returns (redacted_content, count)."""
    redactor = create_redactor(cwd)
    return redactor.redact(content)

def format_size(byte_count: int) -> str:
    """Format byte count as human-readable string."""
    if byte_count >= 1048576:
        return f"{byte_count / 1048576:.1f}MB"
    elif byte_count >= 1024:
        return f"{byte_count / 1024:.1f}KB"
    else:
        return f"{byte_count}B"

def get_session_id(cwd: str) -> str:
    """Get current session ID from session.json."""
    session_file = Path(cwd) / '.fewword' / 'index' / 'session.json'
    if session_file.exists():
        try:
            data = json.loads(session_file.read_text())
            return data.get('session_id', 'unknown')
        except Exception:
            pass
    return 'unknown'

def main():
    args = sys.argv[1:]
    cwd = get_cwd()

    # Parse arguments
    title = None
    file_path = None
    source = "manual"

    i = 0
    while i < len(args):
        if args[i] == '--file' and i + 1 < len(args):
            file_path = args[i + 1]
            i += 2
        elif args[i] == '--source' and i + 1 < len(args):
            source = args[i + 1]
            i += 2
        elif args[i] in ('--help', '-h'):
            print("Usage: /context-save \"title\" [--file path] [--source hint]")
            print("")
            print("Save large content to FewWord scratch with pointer.")
            print("")
            print("Arguments:")
            print("  title       Short title for the saved content (required)")
            print("  --file      Read content from file path instead of stdin")
            print("  --source    Source hint: subagent, paste, tool (default: manual)")
            print("")
            print("Examples:")
            print("  echo \"output\" | /context-save \"My output\"")
            print("  /context-save \"Build log\" --file /tmp/build.log")
            sys.exit(0)
        elif not args[i].startswith('--') and title is None:
            title = args[i]
            i += 1
        else:
            i += 1

    # Validate title
    if not title:
        print("Error: title required")
        print("")
        print("Usage: /context-save \"title\" [--file path] [--source hint]")
        print("")
        print("Examples:")
        print("  echo \"output\" | /context-save \"My output\"")
        print("  /context-save \"Build log\" --file /tmp/build.log")
        sys.exit(1)

    # Read content
    if file_path:
        path = Path(file_path)
        if not path.exists():
            print(f"Error: file not found: {file_path}")
            sys.exit(1)
        try:
            content = path.read_text(errors='replace')
        except Exception as e:
            print(f"Error reading file: {e}")
            sys.exit(1)
    else:
        # Read from stdin
        if sys.stdin.isatty():
            print("Error: no content provided")
            print("")
            print("Pipe content to stdin or use --file:")
            print("  echo \"output\" | /context-save \"title\"")
            print("  /context-save \"title\" --file /path/to/file")
            sys.exit(1)
        content = sys.stdin.read()

    # Validate content
    if not content.strip():
        print("Error: empty content")
        sys.exit(1)

    # Apply redaction BEFORE saving
    content, redact_count = apply_redaction(content, cwd)

    # Generate ID (8-char hex, standard format)
    event_id = uuid.uuid4().hex[:8]

    # Timestamp
    now = datetime.now(timezone.utc)
    ts = now.strftime('%Y%m%d_%H%M%S')

    # Create scratch directory
    scratch_dir = Path(cwd) / '.fewword' / 'scratch' / 'tool_outputs'
    scratch_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize title for filename only (raw title stored in manifest)
    safe_filename = sanitize_for_filename(title)
    if safe_filename:
        filename = f"manual_{ts}_{event_id}_{safe_filename}.txt"
    else:
        filename = f"manual_{ts}_{event_id}.txt"

    output_path = scratch_dir / filename

    # Write content
    try:
        output_path.write_text(content)
    except Exception as e:
        print(f"Error writing file: {e}")
        sys.exit(1)

    # Calculate metrics
    byte_count = len(content.encode('utf-8'))
    line_count = content.count('\n') + (1 if content and not content.endswith('\n') else 0)

    # Get session ID
    session_id = get_session_id(cwd)

    # Create manifest entry (no exit_code for manual entries)
    entry = {
        "type": "manual",
        "id": event_id,
        "session_id": session_id,
        "created_at": now.isoformat().replace('+00:00', 'Z'),
        "title": title,  # Raw title, json.dumps handles escaping
        "source": source,
        "bytes": byte_count,
        "lines": line_count,
        "path": f".fewword/scratch/tool_outputs/{filename}"
    }

    # Append to manifest
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(manifest_path, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception as e:
        print(f"Error writing manifest: {e}")
        sys.exit(1)

    # Output pointer (truncate title for display)
    size_str = format_size(byte_count)
    display_title = title[:40] + '...' if len(title) > 40 else title

    print(f"[fw {event_id}] {display_title} {size_str} {line_count}L | /context-open {event_id}")

    if redact_count > 0:
        print(f"  ({redact_count} items redacted)", file=sys.stderr)

if __name__ == '__main__':
    main()
