#!/usr/bin/env python3
"""
PreToolUse hook for MCP tools: logging + pagination clamping.

This hook:
1. Logs sanitized metadata to .fsctx/index/mcp_metadata.jsonl
2. Clamps pagination parameters to prevent excessive results

NOTE: Does NOT use permissionDecision: "ask" (VS Code extension ignores it).
Write-like MCP operations are gated via PermissionRequest hook instead.
"""

import json
import sys
import os
import uuid
from pathlib import Path
from datetime import datetime


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
    disable_file = Path(cwd) / '.fsctx' / 'DISABLE_OFFLOAD'
    if disable_file.exists():
        return True
    return False


def log_metadata(cwd: str, session_id: str, tool_name: str, tool_input: dict):
    """
    Log sanitized metadata to index file.

    Privacy-safe: logs only tool name, input keys, coarse metrics.
    Does NOT log raw argument values (may contain secrets).
    """
    index_file = Path(cwd) / '.fsctx' / 'index' / 'mcp_metadata.jsonl'

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

    # Always log metadata (sanitized)
    log_metadata(cwd, session_id, tool_name, tool_input)

    # Clamp pagination parameters
    pagination_updates = clamp_pagination(tool_input)

    # Only output JSON if we have updates
    if pagination_updates:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "updatedInput": pagination_updates
            }
        }
        print(json.dumps(output))

    sys.exit(0)


if __name__ == "__main__":
    main()
