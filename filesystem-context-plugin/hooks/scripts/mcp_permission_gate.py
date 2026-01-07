#!/usr/bin/env python3
"""
PermissionRequest hook for MCP write-like operations.

This hook gates MCP tools that perform write operations by returning
behavior: "deny" with a message explaining why.

IMPORTANT: Keep this hook FAST (no slow I/O) - there's a known race
where the permission dialog can appear if the hook takes too long.

Output format (VERIFIED against Claude Code docs):
{
  "hookSpecificOutput": {
    "hookEventName": "PermissionRequest",
    "decision": {
      "behavior": "deny",  // or "allow"
      "message": "...",    // goes to MODEL, not user
      "interrupt": false
    }
  }
}

Note: There is NO "ask" option for PermissionRequest - only allow/deny.
"""

import json
import sys
import os
from pathlib import Path


def is_disabled(cwd: str) -> bool:
    """Check if gating is disabled via env var or file."""
    if os.environ.get('FEWWORD_DISABLE'):
        return True
    # Also check for explicit allow-write flag
    if os.environ.get('FEWWORD_ALLOW_WRITE'):
        return True
    disable_file = Path(cwd) / '.fsctx' / 'DISABLE_OFFLOAD'
    if disable_file.exists():
        return True
    return False


def main():
    try:
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            sys.exit(0)
        input_data = json.loads(raw_input)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    cwd = input_data.get("cwd", os.getcwd())

    # Only process MCP tools (matcher should handle this, but double-check)
    if not tool_name.startswith("mcp__"):
        sys.exit(0)

    # Check escape hatch - if disabled, allow all
    if is_disabled(cwd):
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {
                    "behavior": "allow"
                }
            }
        }
        print(json.dumps(output))
        sys.exit(0)

    # Gate write-like operations with deny + message to model
    # The matcher already filtered for write-like tools, so deny here
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {
                "behavior": "deny",
                "message": f"[fewword] MCP write operation '{tool_name}' blocked. Set FEWWORD_ALLOW_WRITE=1 to allow.",
                "interrupt": False
            }
        }
    }

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
