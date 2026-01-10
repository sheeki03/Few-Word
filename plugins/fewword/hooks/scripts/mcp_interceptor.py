#!/usr/bin/env python3
"""
PreToolUse hook for MCP tools: logging + pagination clamping.

This hook:
1. Logs sanitized metadata to .fewword/index/mcp_metadata.jsonl
2. Clamps pagination parameters to prevent excessive results

Supports allowlist/denylist filtering via config:
- mcp.log.enabled, mcp.log.allowlist, mcp.log.denylist
- mcp.clamp.enabled, mcp.clamp.allowlist, mcp.clamp.denylist

NOTE: Does NOT use permissionDecision: "ask" (VS Code extension ignores it).
Write-like MCP operations are gated via PermissionRequest hook instead.
"""

import json
import sys
import os
import uuid
import fnmatch
from pathlib import Path
from datetime import datetime

# Import shared config loader for consistent precedence
try:
    from config_loader import get_config
    HAS_CONFIG_LOADER = True
except ImportError:
    HAS_CONFIG_LOADER = False


# Pagination parameters to clamp (name -> max value)
PAGINATION_PARAMS = {
    'limit': 100,
    'max_results': 100,
    'page_size': 100,
    'per_page': 100,
    'top_k': 50,
    'n': 50,
    'count': 100,
    'size': 100,
}


def is_disabled(cwd: str) -> bool:
    """Check if offloading is disabled via env var or file."""
    if os.environ.get('FEWWORD_DISABLE'):
        return True
    disable_file = Path(cwd) / '.fewword' / 'DISABLE_OFFLOAD'
    if disable_file.exists():
        return True
    return False


def load_mcp_config(cwd: str) -> dict:
    """
    Load MCP config using shared config_loader for consistent precedence.

    Uses the shared config loader which properly merges:
    1. Environment variables (highest)
    2. Repo config (.fewwordrc.toml/.json in cwd)
    3. User config (~/.fewwordrc.toml/.json)
    4. Built-in defaults (lowest)

    Falls back to simple implementation if config_loader unavailable.
    """
    # Use shared config loader if available (ensures consistent precedence)
    if HAS_CONFIG_LOADER:
        try:
            cfg = get_config(cwd)
            mcp_section = cfg.get_section('mcp')
            return {
                'log': mcp_section.get('log', {'enabled': True, 'allowlist': [], 'denylist': []}),
                'clamp': mcp_section.get('clamp', {'enabled': True, 'allowlist': [], 'denylist': []}),
            }
        except Exception:
            pass  # Fall through to local implementation

    # Fallback: local implementation (for standalone use or import failure)
    config = {
        'log': {'enabled': True, 'allowlist': [], 'denylist': []},
        'clamp': {'enabled': True, 'allowlist': [], 'denylist': []},
    }

    # Check config files with proper precedence (user -> repo, merge not replace)
    config_layers = []

    # Load user config first (lowest priority in file layer)
    user_paths = [Path.home() / '.fewwordrc.toml', Path.home() / '.fewwordrc.json']
    for cfg_path in user_paths:
        if cfg_path.exists():
            try:
                if cfg_path.suffix == '.toml':
                    try:
                        import tomllib
                        with open(cfg_path, 'rb') as f:
                            config_layers.append(tomllib.load(f))
                    except ImportError:
                        continue
                else:
                    with open(cfg_path, 'r') as f:
                        config_layers.append(json.load(f))
                break  # First found in tier wins
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
                            config_layers.append(tomllib.load(f))
                    except ImportError:
                        continue
                else:
                    with open(cfg_path, 'r') as f:
                        config_layers.append(json.load(f))
                break  # First found in tier wins
            except Exception:
                continue

    # Merge config layers (later layers override earlier)
    for layer in config_layers:
        mcp = layer.get('mcp', {})
        if 'log' in mcp:
            log_cfg = mcp['log']
            if 'enabled' in log_cfg:
                config['log']['enabled'] = log_cfg['enabled']
            if 'allowlist' in log_cfg:
                config['log']['allowlist'] = log_cfg['allowlist']
            if 'denylist' in log_cfg:
                config['log']['denylist'] = log_cfg['denylist']
        if 'clamp' in mcp:
            clamp_cfg = mcp['clamp']
            if 'enabled' in clamp_cfg:
                config['clamp']['enabled'] = clamp_cfg['enabled']
            if 'allowlist' in clamp_cfg:
                config['clamp']['allowlist'] = clamp_cfg['allowlist']
            if 'denylist' in clamp_cfg:
                config['clamp']['denylist'] = clamp_cfg['denylist']

    # Environment overrides (highest priority)
    env_log_enabled = os.environ.get('FEWWORD_MCP_LOG_ENABLED')
    if env_log_enabled is not None:
        config['log']['enabled'] = env_log_enabled.lower() not in ('false', '0', 'no')

    env_log_allowlist = os.environ.get('FEWWORD_MCP_LOG_ALLOWLIST')
    if env_log_allowlist is not None:
        config['log']['allowlist'] = [p.strip() for p in env_log_allowlist.split('|') if p.strip()]

    env_log_denylist = os.environ.get('FEWWORD_MCP_LOG_DENYLIST')
    if env_log_denylist is not None:
        config['log']['denylist'] = [p.strip() for p in env_log_denylist.split('|') if p.strip()]

    env_clamp_enabled = os.environ.get('FEWWORD_MCP_CLAMP_ENABLED')
    if env_clamp_enabled is not None:
        config['clamp']['enabled'] = env_clamp_enabled.lower() not in ('false', '0', 'no')

    env_clamp_allowlist = os.environ.get('FEWWORD_MCP_CLAMP_ALLOWLIST')
    if env_clamp_allowlist is not None:
        config['clamp']['allowlist'] = [p.strip() for p in env_clamp_allowlist.split('|') if p.strip()]

    env_clamp_denylist = os.environ.get('FEWWORD_MCP_CLAMP_DENYLIST')
    if env_clamp_denylist is not None:
        config['clamp']['denylist'] = [p.strip() for p in env_clamp_denylist.split('|') if p.strip()]

    return config


def should_process(tool_name: str, allowlist: list, denylist: list) -> bool:
    """
    Check if a tool should be processed based on allowlist/denylist.

    Logic:
    - If denylist matches, skip (return False)
    - If allowlist is empty, process all (return True)
    - If allowlist is non-empty, only process if matches (return True/False)

    Supports glob patterns like "mcp__corridor__*"
    """
    # Check denylist first (deny takes precedence)
    for pattern in denylist:
        if fnmatch.fnmatch(tool_name, pattern):
            return False

    # If allowlist is empty, allow all
    if not allowlist:
        return True

    # Check allowlist
    for pattern in allowlist:
        if fnmatch.fnmatch(tool_name, pattern):
            return True

    return False


def log_metadata(cwd: str, session_id: str, tool_name: str, tool_input: dict):
    """
    Log sanitized metadata to index file.

    Privacy-safe: logs only tool name, input keys, coarse metrics.
    Does NOT log raw argument values (may contain secrets).
    """
    index_file = Path(cwd) / '.fewword' / 'index' / 'mcp_metadata.jsonl'

    try:
        index_file.parent.mkdir(parents=True, exist_ok=True)

        # Generate event ID for correlation
        event_id = uuid.uuid4().hex[:8]

        # Sanitized entry - NO raw values
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_id": event_id,
            "session_id": session_id,
            "tool": tool_name,
            "input_keys": list(tool_input.keys()),
            "input_count": len(tool_input),
        }

        with open(index_file, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        # Don't fail on logging errors
        pass


def clamp_pagination(tool_input: dict) -> dict:
    """
    Clamp pagination parameters to reasonable limits.
    Returns dict of clamped parameters (only if changes needed).
    """
    updates = {}
    for param, max_val in PAGINATION_PARAMS.items():
        if param in tool_input:
            current = tool_input[param]
            if isinstance(current, (int, float)) and current > max_val:
                updates[param] = max_val
    return updates


def main():
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            sys.exit(0)
        input_data = json.loads(raw_input)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    cwd = input_data.get("cwd", os.getcwd())
    session_id = input_data.get("session_id", "unknown")

    # Only process MCP tools
    if not tool_name.startswith("mcp__"):
        sys.exit(0)

    # Check escape hatch
    if is_disabled(cwd):
        sys.exit(0)

    # Load MCP config for allowlist/denylist filtering
    mcp_config = load_mcp_config(cwd)

    # Log metadata (if enabled and passes filter)
    log_cfg = mcp_config.get('log', {})
    if log_cfg.get('enabled', True):
        if should_process(tool_name, log_cfg.get('allowlist', []), log_cfg.get('denylist', [])):
            log_metadata(cwd, session_id, tool_name, tool_input)

    # Clamp pagination parameters (if enabled and passes filter)
    pagination_updates = {}
    clamp_cfg = mcp_config.get('clamp', {})
    if clamp_cfg.get('enabled', True):
        if should_process(tool_name, clamp_cfg.get('allowlist', []), clamp_cfg.get('denylist', [])):
            pagination_updates = clamp_pagination(tool_input)

    # Only output JSON if we have updates
    if pagination_updates:
        # IMPORTANT: Merge updates into full input, don't replace entirely
        # Otherwise we'd strip required params like 'cwd', 'plan', etc.
        full_updated_input = {**tool_input, **pagination_updates}
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "updatedInput": full_updated_input
            }
        }
        print(json.dumps(output))

    sys.exit(0)


if __name__ == "__main__":
    main()
