#!/usr/bin/env python3
"""
FewWord Summary Extractors

Extract meaningful summary lines from tool outputs without using LLM.
Uses simple regex patterns to find status lines for popular tools.

Security note: Only extracts cmd_token (first token), NEVER full command line.
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

# === Built-in summary extractors ===
# Each pattern tries to capture meaningful status information
# Patterns are applied to the LAST 50 lines of output (more efficient)

BUILTIN_EXTRACTORS: Dict[str, list] = {
    # Test runners
    'pytest': [
        r'(\d+\s+(?:passed|failed|skipped|error|warning).*)',
        r'(PASSED|FAILED|ERROR)',
        r'(=+ .+ =+)',  # pytest summary line
    ],
    'jest': [
        r'(Tests:\s+\d+.*)',
        r'(Test Suites:\s+\d+.*)',
    ],
    'mocha': [
        r'(\d+\s+passing)',
        r'(\d+\s+failing)',
    ],
    'cargo': [
        r'(test result:.*)',
        r'(Compiling\s+\S+)',
        r'(Finished\s+.*)',
        r'(error\[E\d+\]:.*)',
    ],
    'go': [
        r'(PASS|FAIL)',
        r'(ok\s+\S+\s+[\d.]+s)',
        r'(--- FAIL:.*)',
    ],
    'rspec': [
        r'(\d+\s+examples?,\s+\d+\s+failures?)',
    ],

    # Package managers
    'npm': [
        r'(added\s+\d+\s+packages?.*)',
        r'(up to date.*)',
        r'(npm WARN.*)',
        r'(npm ERR!.*)',
    ],
    'pnpm': [
        r'(Packages:\s+\+\d+)',
        r'(Done in.*)',
    ],
    'yarn': [
        r'(Done in.*)',
        r'(success\s+.*)',
        r'(error\s+.*)',
    ],
    'bun': [
        r'(bun add.*)',
        r'(installed\s+\d+.*)',
    ],
    'pip': [
        r'(Successfully installed.*)',
        r'(Requirement already satisfied.*)',
    ],
    'pip3': [
        r'(Successfully installed.*)',
        r'(Requirement already satisfied.*)',
    ],

    # Build tools
    'make': [
        r'(make\[\d+\]:.*Error\s+\d+)',
        r'(make:.*Error\s+\d+)',
        r'(warning:.*)',
    ],
    'cmake': [
        r'(-- Build files have been written.*)',
        r'(CMake Error.*)',
    ],
    'tsc': [
        r'(Found\s+\d+\s+errors?)',
        r'(error\s+TS\d+:.*)',
    ],
    'webpack': [
        r'(compiled.*successfully)',
        r'(ERROR in.*)',
    ],
    'vite': [
        r'(ready in.*)',
        r'(build completed.*)',
    ],

    # Git
    'git': [
        r'(\d+\s+files?\s+changed.*)',
        r'(Your branch is.*)',
        r'(Already up to date.*)',
        r'(Fast-forward)',
        r'(CONFLICT.*)',
    ],

    # Search tools
    'rg': [
        r'(\d+\s+matches?)',
    ],
    'grep': [
        r'(\d+:.*)',  # line number match
    ],
    'find': [
        r'(.*/[^/]+$)',  # file path
    ],

    # Docker
    'docker': [
        r'(Successfully built\s+\S+)',
        r'(Successfully tagged.*)',
        r'(Step\s+\d+/\d+.*)',
        r'(ERROR.*)',
    ],

    # Database
    'psql': [
        r'(INSERT\s+\d+\s+\d+)',
        r'(UPDATE\s+\d+)',
        r'(DELETE\s+\d+)',
        r'(SELECT\s+\d+)',
        r'(ERROR:.*)',
    ],

    # Terraform/Infrastructure
    'terraform': [
        r'(Plan:\s+\d+\s+to\s+add.*)',
        r'(Apply complete!.*)',
        r'(Error:.*)',
    ],

    # Linters
    'eslint': [
        r'(\d+\s+problems?\s+\(\d+\s+errors?,\s+\d+\s+warnings?\))',
        r'(no-problems.*)',
    ],
    'pylint': [
        r'(Your code has been rated.*)',
    ],
    'flake8': [
        r'(\d+:\d+:\s+[A-Z]\d+.*)',
    ],
    'mypy': [
        r'(Found\s+\d+\s+errors?.*)',
        r'(Success:.*)',
    ],
    'black': [
        r'(\d+\s+files?\s+reformatted)',
        r'(\d+\s+files?\s+left\s+unchanged)',
        r'(would reformat.*)',
    ],

    # Python
    'python': [
        r'(Traceback.*)',
        r'(\w+Error:.*)',
        r'(\w+Exception:.*)',
    ],
    'python3': [
        r'(Traceback.*)',
        r'(\w+Error:.*)',
        r'(\w+Exception:.*)',
    ],

    # Rust
    'rustc': [
        r'(error\[E\d+\]:.*)',
        r'(warning:.*)',
    ],

    # General fallback patterns (applied to any command)
    '__fallback__': [
        r'(error:.*)',
        r'(Error:.*)',
        r'(ERROR:.*)',
        r'(failed.*)',
        r'(FAILED.*)',
        r'(success.*)',
        r'(SUCCESS.*)',
        r'(warning:.*)',
        r'(Warning:.*)',
    ],
}


def get_cmd_token(full_command: str) -> str:
    """
    Extract first token only. NEVER store full command (secrets risk).

    Handles common prefixes like sudo, env, etc.
    """
    if not full_command or not full_command.strip():
        return 'unknown'

    cmd = full_command.strip()
    prefixes = {'sudo', 'env', 'nohup', 'nice', 'time', 'strace', 'ltrace'}
    words = cmd.split()

    # P1 fix #22: Removed unreachable first_non_skipped logic
    for word in words:
        # Skip environment variable assignments (VAR=value)
        if '=' in word and not word.startswith('-'):
            continue
        # Skip known prefixes
        if word in prefixes:
            continue
        # Return the actual command (handle full paths)
        return word.split('/')[-1]

    # If all words were skipped (prefixes/env vars only), return 'unknown'
    return 'unknown'


def resolve_cmd_group(cmd_token: str, aliases: Dict[str, list]) -> str:
    """
    Resolve canonical group at capture time.

    Args:
        cmd_token: First token of command (e.g., 'pnpm')
        aliases: Dict of canonical -> [aliases] from config

    Returns:
        Canonical group name (e.g., 'npm' for 'pnpm')
    """
    for canonical, patterns in aliases.items():
        if cmd_token == canonical:
            return canonical
        if isinstance(patterns, str):
            if cmd_token == patterns:
                return canonical
        elif cmd_token in patterns:
            return canonical
    return cmd_token  # Self is canonical if no alias


def extract_summary(output: str, cmd_token: str, cmd_group: str,
                    custom_extractors: Optional[Dict[str, list]] = None,
                    max_chars: int = 120) -> str:
    """
    Extract a meaningful summary line from command output.

    Args:
        output: Full command output
        cmd_token: First token of command (for pattern matching)
        cmd_group: Canonical command group (for pattern matching)
        custom_extractors: Additional patterns from config
        max_chars: Maximum characters in summary

    Returns:
        Summary string (empty if none found)
    """
    if not output:
        return ''

    # Get last 50 lines (more efficient than scanning entire output)
    lines = output.strip().split('\n')
    tail_lines = lines[-50:] if len(lines) > 50 else lines
    tail_text = '\n'.join(tail_lines)

    # Build pattern list: custom > cmd_token > cmd_group > fallback
    patterns = []

    # Custom extractors (highest priority)
    if custom_extractors:
        if cmd_token in custom_extractors:
            patterns.extend(custom_extractors[cmd_token])
        if cmd_group in custom_extractors and cmd_group != cmd_token:
            patterns.extend(custom_extractors[cmd_group])

    # Built-in extractors
    if cmd_token in BUILTIN_EXTRACTORS:
        patterns.extend(BUILTIN_EXTRACTORS[cmd_token])
    if cmd_group in BUILTIN_EXTRACTORS and cmd_group != cmd_token:
        patterns.extend(BUILTIN_EXTRACTORS[cmd_group])

    # Fallback patterns
    patterns.extend(BUILTIN_EXTRACTORS.get('__fallback__', []))

    # Try each pattern, return first match
    for pattern in patterns:
        try:
            match = re.search(pattern, tail_text, re.IGNORECASE | re.MULTILINE)
            if match:
                # P1 fix: Check if pattern has capturing group, fallback to group(0)
                try:
                    summary = match.group(1).strip() if match.lastindex and match.lastindex >= 1 else match.group(0).strip()
                except IndexError:
                    summary = match.group(0).strip()
                # Truncate if too long
                if len(summary) > max_chars:
                    summary = summary[:max_chars - 3] + '...'
                return summary
        except re.error:
            continue

    # Fallback: last non-empty line, capped
    for line in reversed(tail_lines):
        line = line.strip()
        if line and not line.startswith('#'):
            if len(line) > max_chars:
                line = line[:max_chars - 3] + '...'
            return line

    return ''


def extract_with_context(output: str, full_command: str,
                         aliases: Optional[Dict[str, list]] = None,
                         custom_extractors: Optional[Dict[str, list]] = None,
                         max_chars: int = 120) -> Tuple[str, str, str]:
    """
    Extract cmd_token, cmd_group, and summary from command output.

    This is the main entry point for offload_bash.py.

    Args:
        output: Full command output
        full_command: Full command string (only first token used)
        aliases: Command aliases from config
        custom_extractors: Custom summary patterns from config
        max_chars: Maximum chars in summary

    Returns:
        Tuple of (cmd_token, cmd_group, summary)
    """
    cmd_token = get_cmd_token(full_command)
    cmd_group = resolve_cmd_group(cmd_token, aliases or {})
    summary = extract_summary(output, cmd_token, cmd_group, custom_extractors, max_chars)

    return cmd_token, cmd_group, summary


# === CLI for testing ===

def main():
    """CLI for testing summary extraction."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description='FewWord Summary Extractor')
    parser.add_argument('--command', '-c', required=True, help='Command that produced output')
    parser.add_argument('--file', '-f', help='Read output from file')
    parser.add_argument('--max-chars', type=int, default=120, help='Max summary chars')

    args = parser.parse_args()

    if args.file:
        # P2 fix #21: Add explicit encoding to prevent platform-dependent failures
        with open(args.file, 'r', encoding='utf-8', errors='replace') as f:
            output = f.read()
    else:
        output = sys.stdin.read()

    cmd_token, cmd_group, summary = extract_with_context(
        output=output,
        full_command=args.command,
        max_chars=args.max_chars
    )

    print(f"cmd_token: {cmd_token}")
    print(f"cmd_group: {cmd_group}")
    print(f"summary: {summary}")


if __name__ == '__main__':
    main()
