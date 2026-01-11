---
description: "Show effective FewWord configuration with sources"
---

# FewWord Config

Display the effective FewWord configuration and where each setting comes from.

## Usage

```bash
# Show full config
/config

# Show specific section
/config thresholds

# Validate config file syntax
/config --validate

# Output as JSON
/config --json
```

## Implementation

Run this Python script to display configuration:

```python
#!/usr/bin/env python3
"""FewWord Config - Show effective configuration."""

import json
import os
import sys
from pathlib import Path

# Try to import config_loader from hooks/scripts
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir.parent / 'hooks' / 'scripts'))

try:
    from config_loader import FewWordConfig, HAS_TOML
except ImportError:
    # Fallback inline implementation (ship-blocker fix: proper __init__)
    HAS_TOML = False
    class FewWordConfig:
        def __init__(self, config, sources):
            self._config = config
            self._sources = sources
        @classmethod
        def load(cls, cwd=None):
            return cls({}, {})
        def to_dict(self):
            return self._config
        @property
        def sources(self):
            return self._sources

def main():
    args = sys.argv[1:]
    cwd = os.getcwd()

    # Parse args
    validate_mode = '--validate' in args
    json_mode = '--json' in args
    section = None

    for arg in args:
        if not arg.startswith('--'):
            section = arg
            break

    # Load config
    config = FewWordConfig.load(cwd)

    # Validate mode
    if validate_mode:
        print("Configuration Validation")
        print("=" * 50)

        # Check for config files
        repo_toml = Path(cwd) / '.fewwordrc.toml'
        repo_json = Path(cwd) / '.fewwordrc.json'
        home_toml = Path.home() / '.fewwordrc.toml'
        home_json = Path.home() / '.fewwordrc.json'

        found_any = False

        if repo_toml.exists():
            found_any = True
            print(f"Repo TOML: {repo_toml}")
            if HAS_TOML:
                try:
                    import tomllib
                    with open(repo_toml, 'rb') as f:
                        tomllib.load(f)
                    print("  Status: Valid TOML syntax")
                except Exception as e:
                    print(f"  Status: INVALID - {e}")
            else:
                print("  Status: Cannot validate (Python < 3.11, no tomllib)")

        if repo_json.exists():
            found_any = True
            print(f"Repo JSON: {repo_json}")
            try:
                with open(repo_json, 'r') as f:
                    json.load(f)
                print("  Status: Valid JSON syntax")
            except Exception as e:
                print(f"  Status: INVALID - {e}")

        if home_toml.exists():
            found_any = True
            print(f"User TOML: {home_toml}")
            if HAS_TOML:
                try:
                    import tomllib
                    with open(home_toml, 'rb') as f:
                        tomllib.load(f)
                    print("  Status: Valid TOML syntax")
                except Exception as e:
                    print(f"  Status: INVALID - {e}")
            else:
                print("  Status: Cannot validate (Python < 3.11)")

        if home_json.exists():
            found_any = True
            print(f"User JSON: {home_json}")
            try:
                with open(home_json, 'r') as f:
                    json.load(f)
                print("  Status: Valid JSON syntax")
            except Exception as e:
                print(f"  Status: INVALID - {e}")

        if not found_any:
            print("No config files found. Using defaults + env vars.")

        # Check for FEWWORD_* env vars
        env_vars = [k for k in os.environ if k.startswith('FEWWORD_')]
        if env_vars:
            print()
            print("Environment variables:")
            for var in sorted(env_vars):
                val = os.environ[var]
                # Mask potentially sensitive values
                if 'KEY' in var.upper() or 'SECRET' in var.upper() or 'TOKEN' in var.upper():
                    val = val[:4] + '...' if len(val) > 4 else '***'
                print(f"  {var}={val}")

        return

    # JSON output mode
    if json_mode:
        if section:
            print(json.dumps(config.to_dict().get(section, {}), indent=2))
        else:
            print(json.dumps(config.to_dict(), indent=2))
        return

    # Default: human-readable output
    print("FewWord Configuration")
    print("=" * 50)
    print()

    # Show TOML support status
    print(f"TOML support: {'Yes (Python 3.11+)' if HAS_TOML else 'No (using JSON fallback)'}")
    print()

    # Show sources
    print("Configuration sources (higher wins):")
    sources = config.sources
    if 'env' in sources:
        print(f"  1. {sources['env']}")
    if 'repo' in sources:
        print(f"  2. {sources['repo']}")
    if 'user' in sources:
        print(f"  3. {sources['user']}")
    print(f"  4. Built-in defaults")
    print()

    # Show config
    full_config = config.to_dict()

    if section:
        if section in full_config:
            print(f"[{section}]")
            section_config = full_config[section]
            if isinstance(section_config, dict):
                for k, v in section_config.items():
                    print(f"  {k} = {json.dumps(v)}")
            else:
                print(f"  {json.dumps(section_config)}")
        else:
            print(f"Unknown section: {section}")
            print(f"Available: {', '.join(full_config.keys())}")
    else:
        for section_name, section_config in full_config.items():
            print(f"[{section_name}]")
            if isinstance(section_config, dict):
                for k, v in section_config.items():
                    # Format value nicely
                    if isinstance(v, list):
                        if len(v) > 3:
                            v_str = f"[{', '.join(repr(x) for x in v[:3])}, ...{len(v)-3} more]"
                        else:
                            v_str = json.dumps(v)
                    else:
                        v_str = json.dumps(v)
                    print(f"  {k} = {v_str}")
            else:
                print(f"  {json.dumps(section_config)}")
            print()

if __name__ == '__main__':
    main()
```

## Output Example

```
FewWord Configuration
==================================================

TOML support: Yes (Python 3.11+)

Configuration sources (higher wins):
  1. FEWWORD_* environment variables
  2. /path/to/project/.fewwordrc.toml
  3. ~/.fewwordrc.toml (user config)
  4. Built-in defaults

[thresholds]
  inline_max = 512
  preview_min = 4096
  preview_lines = 5
  scratch_max_mb = 250

[retention]
  success_min = 1440
  fail_min = 2880

[auto_pin]
  on_fail = false
  match = ""
  cmds = []
  exit_codes = []
  size_min = 0
  max_files = 50

[redaction]
  enabled = true
  patterns = []
  replacement = "[REDACTED]"

[deny]
  cmds = []
  patterns = []

[aliases]
  pytest = ["py.test", "python -m pytest", ...2 more]
  npm = ["pnpm", "yarn", "bun"]
  cargo = ["cargo test", "cargo build", "cargo run"]
  git = ["gh"]
  make = ["gmake", "cmake --build"]

[pointer]
  open_cmd = "/open"
  show_path = false
  verbose = false
  peek_on_pointer = false
  peek_tier2_lines = 2
  peek_tier3_lines = 5

[summary]
  enabled = true
  extractors = {}
  fallback_max_chars = 120
```

## Config File Examples

### .fewwordrc.toml (Python 3.11+)
```toml
[thresholds]
inline_max = 256
preview_min = 2048
scratch_max_mb = 500

[retention]
success_min = 720   # 12h
fail_min = 4320     # 72h

[auto_pin]
on_fail = true
match = "FATAL|panic"
cmds = ["pytest", "cargo test"]

[redaction]
enabled = true
patterns = ["INTERNAL_API_KEY_.*"]

[deny]
cmds = ["vault", "1password"]

[aliases]
pytest = ["py.test", "python -m pytest"]
npm = ["pnpm", "yarn", "bun"]
```

### .fewwordrc.json (all Python versions)
```json
{
  "thresholds": {
    "inline_max": 256,
    "scratch_max_mb": 500
  },
  "retention": {
    "success_min": 720,
    "fail_min": 4320
  },
  "auto_pin": {
    "on_fail": true
  }
}
```
