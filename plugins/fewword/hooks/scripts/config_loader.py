#!/usr/bin/env python3
"""
FewWord Configuration Loader

Loads configuration with proper precedence:
1. Environment variables (highest - can hotfix without file edits)
2. Repo config (.fewwordrc.toml or .fewwordrc.json in project root)
3. User config (~/.fewwordrc.toml or ~/.fewwordrc.json)
4. Built-in defaults (lowest)

Within same tier: TOML checked before JSON (first found wins).

Supports Python 3.11+ with tomllib (stdlib), falls back to JSON for older Python.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Try to import tomllib (Python 3.11+)
try:
    import tomllib
    HAS_TOML = True
except ImportError:
    HAS_TOML = False


# === Default Configuration ===
DEFAULTS = {
    'thresholds': {
        'inline_max': 512,
        'preview_min': 4096,
        'preview_lines': 5,
        'scratch_max_mb': 250,
    },
    'retention': {
        'success_min': 1440,   # 24h
        'fail_min': 2880,      # 48h
    },
    'auto_pin': {
        'on_fail': False,
        'match': '',
        'cmds': [],
        'exit_codes': [],
        'size_min': 0,
        'max_files': 50,
    },
    'redaction': {
        'enabled': True,  # ON by default per user decision
        'patterns': [],
        'replacement': '[REDACTED]',
    },
    'deny': {
        'cmds': [],
        'patterns': [],
    },
    'aliases': {
        'pytest': ['py.test', 'python -m pytest', 'python3 -m pytest'],
        'npm': ['pnpm', 'yarn', 'bun'],
        'cargo': ['cargo test', 'cargo build', 'cargo run'],
        'git': ['gh'],
        'make': ['gmake', 'cmake --build'],
    },
    'pointer': {
        'open_cmd': '/open',
        'show_path': False,
        'verbose': False,
        'peek_on_pointer': False,
        'peek_tier2_lines': 2,
        'peek_tier3_lines': 5,
    },
    'summary': {
        'enabled': True,
        'extractors': {},  # Custom extractors in TOML
        'fallback_max_chars': 120,
    },
    'compression': {
        'enabled': False,
        'min_bytes': 1048576,  # 1MB - only compress files larger than this
        'level': 6,  # gzip compression level (1-9)
    },
    'manifest': {
        'max_mb': 50,  # Rotate when manifest exceeds this size
        'keep_rotated': 5,  # Number of rotated manifests to keep
    },
}


def _deep_merge(base: Dict, overlay: Dict) -> Dict:
    """Deep merge overlay into base, returning new dict."""
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_toml(path: Path) -> Optional[Dict]:
    """Load TOML file if tomllib available and file exists."""
    if not HAS_TOML:
        return None
    if not path.exists():
        return None
    try:
        with open(path, 'rb') as f:
            return tomllib.load(f)
    except Exception:
        return None


def _load_json(path: Path) -> Optional[Dict]:
    """Load JSON file if exists."""
    if not path.exists():
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _load_config_file(directory: Path) -> Tuple[Optional[Dict], Optional[Path]]:
    """
    Try to load config from directory.
    TOML checked before JSON (first found wins within tier).

    P2 fix #20: Return (config, loaded_path) tuple for accurate source reporting.
    """
    # Try TOML first (only if we have tomllib)
    toml_path = directory / '.fewwordrc.toml'
    config = _load_toml(toml_path)
    if config is not None:
        return config, toml_path

    # Fall back to JSON
    json_path = directory / '.fewwordrc.json'
    config = _load_json(json_path)
    if config is not None:
        return config, json_path

    return None, None


def _env_to_config() -> Dict:
    """
    Convert FEWWORD_* environment variables to config dict.

    Mapping:
    - FEWWORD_INLINE_MAX -> thresholds.inline_max
    - FEWWORD_PREVIEW_MIN -> thresholds.preview_min
    - FEWWORD_PREVIEW_LINES -> thresholds.preview_lines
    - FEWWORD_SCRATCH_MAX_MB -> thresholds.scratch_max_mb
    - FEWWORD_RETENTION_SUCCESS_MIN -> retention.success_min
    - FEWWORD_RETENTION_FAIL_MIN -> retention.fail_min
    - FEWWORD_AUTO_PIN_FAIL -> auto_pin.on_fail
    - FEWWORD_AUTO_PIN_MATCH -> auto_pin.match
    - FEWWORD_AUTO_PIN_CMDS -> auto_pin.cmds (comma-separated)
    - FEWWORD_AUTO_PIN_EXIT -> auto_pin.exit_codes (comma-separated)
    - FEWWORD_AUTO_PIN_SIZE_MIN -> auto_pin.size_min
    - FEWWORD_AUTO_PIN_MAX -> auto_pin.max_files
    - FEWWORD_REDACT_ENABLED -> redaction.enabled
    - FEWWORD_REDACT_PATTERNS -> redaction.patterns (pipe-separated)
    - FEWWORD_REDACT_REPLACEMENT -> redaction.replacement
    - FEWWORD_DENY_CMDS -> deny.cmds (comma-separated)
    - FEWWORD_DENY_PATTERNS -> deny.patterns (pipe-separated)
    - FEWWORD_OPEN_CMD -> pointer.open_cmd
    - FEWWORD_SHOW_PATH -> pointer.show_path
    - FEWWORD_VERBOSE_POINTER -> pointer.verbose
    - FEWWORD_PEEK_ON_POINTER -> pointer.peek_on_pointer
    - FEWWORD_PEEK_TIER2_LINES -> pointer.peek_tier2_lines
    - FEWWORD_PEEK_TIER3_LINES -> pointer.peek_tier3_lines
    """
    config: Dict[str, Any] = {}

    def _int(key: str) -> Optional[int]:
        val = os.environ.get(key)
        if val is None:
            return None
        try:
            return int(val)
        except ValueError:
            return None

    def _bool(key: str) -> Optional[bool]:
        val = os.environ.get(key)
        if val is None:
            return None
        return val.lower() in ('1', 'true', 'yes', 'on')

    def _str(key: str) -> Optional[str]:
        return os.environ.get(key)

    def _list_comma(key: str) -> Optional[list]:
        val = os.environ.get(key)
        if val is None:
            return None
        return [x.strip() for x in val.split(',') if x.strip()]

    def _list_pipe(key: str) -> Optional[list]:
        val = os.environ.get(key)
        if val is None:
            return None
        return [x.strip() for x in val.split('|') if x.strip()]

    # Thresholds
    thresholds = {}
    if (v := _int('FEWWORD_INLINE_MAX')) is not None:
        thresholds['inline_max'] = v
    if (v := _int('FEWWORD_PREVIEW_MIN')) is not None:
        thresholds['preview_min'] = v
    if (v := _int('FEWWORD_PREVIEW_LINES')) is not None:
        thresholds['preview_lines'] = v
    if (v := _int('FEWWORD_SCRATCH_MAX_MB')) is not None:
        thresholds['scratch_max_mb'] = v
    if thresholds:
        config['thresholds'] = thresholds

    # Retention
    retention = {}
    if (v := _int('FEWWORD_RETENTION_SUCCESS_MIN')) is not None:
        retention['success_min'] = v
    if (v := _int('FEWWORD_RETENTION_FAIL_MIN')) is not None:
        retention['fail_min'] = v
    if retention:
        config['retention'] = retention

    # Auto-pin
    auto_pin = {}
    if (v := _bool('FEWWORD_AUTO_PIN_FAIL')) is not None:
        auto_pin['on_fail'] = v
    if (v := _str('FEWWORD_AUTO_PIN_MATCH')) is not None:
        auto_pin['match'] = v
    if (v := _list_comma('FEWWORD_AUTO_PIN_CMDS')) is not None:
        auto_pin['cmds'] = v
    if (v := _list_comma('FEWWORD_AUTO_PIN_EXIT')) is not None:
        # P1 fix #19: isdigit() drops negative numbers, use try/int() instead
        exit_codes = []
        for x in v:
            try:
                exit_codes.append(int(x))
            except ValueError:
                pass
        auto_pin['exit_codes'] = exit_codes
    if (v := _int('FEWWORD_AUTO_PIN_SIZE_MIN')) is not None:
        auto_pin['size_min'] = v
    if (v := _int('FEWWORD_AUTO_PIN_MAX')) is not None:
        auto_pin['max_files'] = v
    if auto_pin:
        config['auto_pin'] = auto_pin

    # Redaction
    redaction = {}
    if (v := _bool('FEWWORD_REDACT_ENABLED')) is not None:
        redaction['enabled'] = v
    if (v := _list_pipe('FEWWORD_REDACT_PATTERNS')) is not None:
        redaction['patterns'] = v
    if (v := _str('FEWWORD_REDACT_REPLACEMENT')) is not None:
        redaction['replacement'] = v
    if redaction:
        config['redaction'] = redaction

    # Deny
    deny = {}
    if (v := _list_comma('FEWWORD_DENY_CMDS')) is not None:
        deny['cmds'] = v
    if (v := _list_pipe('FEWWORD_DENY_PATTERNS')) is not None:
        deny['patterns'] = v
    if deny:
        config['deny'] = deny

    # Pointer
    pointer = {}
    if (v := _str('FEWWORD_OPEN_CMD')) is not None:
        pointer['open_cmd'] = v
    if (v := _bool('FEWWORD_SHOW_PATH')) is not None:
        pointer['show_path'] = v
    if (v := _bool('FEWWORD_VERBOSE_POINTER')) is not None:
        pointer['verbose'] = v
    if (v := _bool('FEWWORD_PEEK_ON_POINTER')) is not None:
        pointer['peek_on_pointer'] = v
    if (v := _int('FEWWORD_PEEK_TIER2_LINES')) is not None:
        pointer['peek_tier2_lines'] = v
    if (v := _int('FEWWORD_PEEK_TIER3_LINES')) is not None:
        pointer['peek_tier3_lines'] = v
    if pointer:
        config['pointer'] = pointer

    # Compression
    compression = {}
    if (v := _bool('FEWWORD_COMPRESS_ENABLED')) is not None:
        compression['enabled'] = v
    if (v := _int('FEWWORD_COMPRESS_MIN')) is not None:
        compression['min_bytes'] = v
    if (v := _int('FEWWORD_COMPRESS_LEVEL')) is not None:
        compression['level'] = v
    if compression:
        config['compression'] = compression

    # Manifest
    manifest = {}
    if (v := _int('FEWWORD_MANIFEST_MAX_MB')) is not None:
        manifest['max_mb'] = v
    if (v := _int('FEWWORD_MANIFEST_KEEP_ROTATED')) is not None:
        manifest['keep_rotated'] = v
    if manifest:
        config['manifest'] = manifest

    return config


class FewWordConfig:
    """
    FewWord configuration with proper precedence.

    Usage:
        config = FewWordConfig.load(cwd='/path/to/project')
        inline_max = config.get('thresholds.inline_max')
        aliases = config.get('aliases')
    """

    def __init__(self, merged_config: Dict, sources: Dict[str, str]):
        self._config = merged_config
        self._sources = sources  # Track where each value came from

    @classmethod
    def load(cls, cwd: Optional[str] = None) -> 'FewWordConfig':
        """
        Load configuration with proper precedence.

        Precedence (higher wins, merges down):
        1. Environment variables
        2. Repo config (.fewwordrc.toml/.json in cwd)
        3. User config (~/.fewwordrc.toml/.json)
        4. Built-in defaults
        """
        sources = {}

        # Start with defaults (P0 fix: use deepcopy to prevent nested dict mutation)
        config = copy.deepcopy(DEFAULTS)
        sources['base'] = 'defaults'

        # Layer 3: User config (~/.fewwordrc.toml or ~/.fewwordrc.json)
        home = Path.home()
        user_config, user_config_path = _load_config_file(home)
        if user_config:
            config = _deep_merge(config, user_config)
            # P2 fix #20: Use actual loaded path instead of checking existence
            sources['user'] = str(user_config_path)

        # Layer 2: Repo config (.fewwordrc.toml or .fewwordrc.json in cwd)
        if cwd:
            cwd_path = Path(cwd)
            repo_config, repo_config_path = _load_config_file(cwd_path)
            if repo_config:
                config = _deep_merge(config, repo_config)
                # P2 fix #20: Use actual loaded path instead of checking existence
                sources['repo'] = str(repo_config_path)

        # Layer 1: Environment variables (highest priority)
        env_config = _env_to_config()
        if env_config:
            config = _deep_merge(config, env_config)
            sources['env'] = 'FEWWORD_* environment variables'

        return cls(config, sources)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get config value by dot-notation key.

        Examples:
            config.get('thresholds.inline_max')  # -> 512
            config.get('aliases.pytest')  # -> ['py.test', ...]
            config.get('redaction.enabled')  # -> True
        """
        parts = key.split('.')
        value = self._config
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value

    def get_section(self, section: str) -> Dict:
        """Get entire config section."""
        return self._config.get(section, {})

    @property
    def sources(self) -> Dict[str, str]:
        """Get mapping of config layers to their sources."""
        return self._sources.copy()

    def to_dict(self) -> Dict:
        """Get full config as dict."""
        return self._config.copy()

    def format_sources(self) -> str:
        """Format sources for display."""
        lines = []
        for layer, source in self._sources.items():
            lines.append(f"  {layer}: {source}")
        return '\n'.join(lines)


# === Convenience functions for direct use ===

_cached_config: Optional[FewWordConfig] = None
_cached_cwd: Optional[str] = None


def get_config(cwd: Optional[str] = None, force_reload: bool = False) -> FewWordConfig:
    """
    Get cached config, reloading if cwd changed or force_reload=True.

    This is the main entry point for other scripts.
    """
    global _cached_config, _cached_cwd

    if force_reload or _cached_config is None or _cached_cwd != cwd:
        _cached_config = FewWordConfig.load(cwd)
        _cached_cwd = cwd

    return _cached_config


def get_value(key: str, default: Any = None, cwd: Optional[str] = None) -> Any:
    """Convenience function to get a single config value."""
    return get_config(cwd).get(key, default)


# === CLI for testing/debugging ===

def main():
    """CLI for debugging config loading."""
    import argparse

    parser = argparse.ArgumentParser(description='FewWord Config Loader')
    parser.add_argument('--cwd', default=os.getcwd(), help='Working directory')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--sources', action='store_true', help='Show config sources')
    parser.add_argument('key', nargs='?', help='Config key to get (dot notation)')

    args = parser.parse_args()

    config = FewWordConfig.load(args.cwd)

    if args.sources:
        print("Configuration sources:")
        print(config.format_sources())
        print()

    if args.key:
        value = config.get(args.key)
        if args.json:
            print(json.dumps(value, indent=2))
        else:
            print(f"{args.key} = {value}")
    elif args.json:
        print(json.dumps(config.to_dict(), indent=2))
    else:
        print("Full configuration:")
        print(json.dumps(config.to_dict(), indent=2))


if __name__ == '__main__':
    main()
