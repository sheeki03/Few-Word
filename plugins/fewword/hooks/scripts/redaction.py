#!/usr/bin/env python3
"""
FewWord Redaction Module

Redacts secrets from command output BEFORE writing to disk.
One-way redaction at capture time - no --no-redact flag exists.

Built-in patterns (ON by default):
- AWS access keys (AKIA...)
- GitHub tokens (ghp_..., gho_..., ghu_..., ghs_..., ghr_...)
- GitLab tokens (glpat-...)
- Bearer tokens
- Generic API keys
- Private keys
- Connection strings with passwords

Security notes:
- Redaction is one-way: unredacted output is NEVER stored
- Replacement text includes char count for debugging
- Custom patterns supported via config
"""

from __future__ import annotations

import re
from typing import List, Tuple, Optional


# === Built-in redaction patterns ===
# Format: (name, pattern, replacement_template)
# replacement_template can use {length} for matched length

BUILTIN_PATTERNS: List[Tuple[str, str, str]] = [
    # AWS
    ('AWS_ACCESS_KEY', r'AKIA[0-9A-Z]{16}', '[REDACTED:AWS_KEY]'),
    ('AWS_SECRET_KEY', r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*[\'"]?([a-zA-Z0-9/+=]{40})[\'"]?',
     '[REDACTED:AWS_SECRET:{length}chars]'),

    # GitHub
    ('GITHUB_PAT', r'ghp_[a-zA-Z0-9]{36}', '[REDACTED:GITHUB_PAT]'),
    ('GITHUB_OAUTH', r'gho_[a-zA-Z0-9]{36}', '[REDACTED:GITHUB_OAUTH]'),
    ('GITHUB_USER', r'ghu_[a-zA-Z0-9]{36}', '[REDACTED:GITHUB_USER]'),
    ('GITHUB_SERVER', r'ghs_[a-zA-Z0-9]{36}', '[REDACTED:GITHUB_SERVER]'),
    ('GITHUB_REFRESH', r'ghr_[a-zA-Z0-9]{36}', '[REDACTED:GITHUB_REFRESH]'),

    # GitLab
    ('GITLAB_PAT', r'glpat-[a-zA-Z0-9_-]{20}', '[REDACTED:GITLAB_PAT]'),

    # Bearer tokens (common in API calls)
    ('BEARER_TOKEN', r'(?i)bearer\s+([a-zA-Z0-9._-]{20,})', 'Bearer [REDACTED:{length}chars]'),
    ('AUTHORIZATION_HEADER', r'(?i)authorization:\s*bearer\s+([a-zA-Z0-9._-]{20,})',
     'Authorization: Bearer [REDACTED:{length}chars]'),

    # Generic API keys
    ('API_KEY_ASSIGNMENT', r'(?i)api[_-]?key\s*[=:]\s*[\'"]?([a-zA-Z0-9_-]{20,})[\'"]?',
     'api_key=[REDACTED:{length}chars]'),
    ('SECRET_KEY_ASSIGNMENT', r'(?i)secret[_-]?key\s*[=:]\s*[\'"]?([a-zA-Z0-9_-]{20,})[\'"]?',
     'secret_key=[REDACTED:{length}chars]'),
    ('PASSWORD_ASSIGNMENT', r'(?i)password\s*[=:]\s*[\'"]?([^\s\'"]{8,})[\'"]?',
     'password=[REDACTED:{length}chars]'),
    ('TOKEN_ASSIGNMENT', r'(?i)token\s*[=:]\s*[\'"]?([a-zA-Z0-9._-]{20,})[\'"]?',
     'token=[REDACTED:{length}chars]'),

    # Connection strings with credentials
    ('DB_CONNECTION_STRING', r'(?i)(mysql|postgres|postgresql|mongodb|redis)://[^:]+:([^@]+)@',
     r'\1://user:[REDACTED]@'),

    # Private keys (PEM format)
    ('PRIVATE_KEY_BEGIN', r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----',
     '-----BEGIN PRIVATE KEY----- [REDACTED]'),
    # P1 fix #7: Replace variable-length lookbehind with non-lookbehind pattern
    # Original used (?<=-----BEGIN\s) which Python's re cannot compile
    ('PRIVATE_KEY_CONTENT', r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(RSA\s+)?PRIVATE\s+KEY-----',
     '-----BEGIN PRIVATE KEY----- [REDACTED:KEY_CONTENT] -----END PRIVATE KEY-----'),

    # NPM tokens
    ('NPM_TOKEN', r'npm_[a-zA-Z0-9]{36}', '[REDACTED:NPM_TOKEN]'),

    # Slack tokens
    ('SLACK_TOKEN', r'xox[baprs]-[a-zA-Z0-9-]+', '[REDACTED:SLACK_TOKEN]'),

    # Stripe keys
    ('STRIPE_KEY', r'sk_live_[a-zA-Z0-9]{24,}', '[REDACTED:STRIPE_KEY]'),
    ('STRIPE_TEST_KEY', r'sk_test_[a-zA-Z0-9]{24,}', '[REDACTED:STRIPE_TEST_KEY]'),

    # Heroku
    ('HEROKU_API_KEY', r'(?i)heroku[_-]?api[_-]?key\s*[=:]\s*[\'"]?([a-f0-9-]{36})[\'"]?',
     'heroku_api_key=[REDACTED:UUID]'),

    # Generic hex secrets (32+ chars, likely tokens)
    # P1 fix #9: Changed (?:...) to capturing group (...) since replacement uses \1
    # Group 1 = prefix (key|token|etc), Group 2 = the hex secret
    ('HEX_SECRET', r'(?i)(key|token|secret|password|credential)[_-]?\s*[=:]\s*[\'"]?([a-f0-9]{32,})[\'"]?',
     r'\1=[REDACTED:{length}chars]'),

    # JWT tokens (3 base64 parts separated by dots)
    ('JWT_TOKEN', r'eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*',
     '[REDACTED:JWT_TOKEN]'),

    # SSH private key content
    ('SSH_PRIVATE_KEY', r'-----BEGIN\s+OPENSSH\s+PRIVATE\s+KEY-----[\s\S]*?-----END\s+OPENSSH\s+PRIVATE\s+KEY-----',
     '-----BEGIN OPENSSH PRIVATE KEY----- [REDACTED] -----END OPENSSH PRIVATE KEY-----'),
]


class Redactor:
    """
    Redacts secrets from text.

    Usage:
        redactor = Redactor(enabled=True, custom_patterns=['my-secret-.*'])
        clean_text, count = redactor.redact(text)
    """

    def __init__(self,
                 enabled: bool = True,
                 custom_patterns: Optional[List[str]] = None,
                 replacement: str = '[REDACTED]'):
        """
        Initialize redactor.

        Args:
            enabled: If False, redact() returns text unchanged
            custom_patterns: Additional regex patterns to redact
            replacement: Default replacement text for custom patterns
        """
        self.enabled = enabled
        self.replacement = replacement

        # Compile built-in patterns (P2 fix: warn on builtin compilation failure)
        self._patterns: List[Tuple[str, re.Pattern, str]] = []
        for name, pattern, repl in BUILTIN_PATTERNS:
            try:
                compiled = re.compile(pattern)
                self._patterns.append((name, compiled, repl))
            except re.error as e:
                # Warn about builtin pattern failures - these indicate a bug in BUILTIN_PATTERNS
                import sys
                print(f"[FewWord] Warning: Built-in redaction pattern '{name}' failed to compile: {e}", file=sys.stderr)

        # Compile custom patterns
        if custom_patterns:
            for i, pattern in enumerate(custom_patterns):
                try:
                    compiled = re.compile(pattern)
                    self._patterns.append((f'custom_{i}', compiled, replacement))
                except re.error as e:
                    # Warn user - they think pattern is working but it's not
                    import sys
                    print(f"[FewWord] Warning: Invalid redaction pattern '{pattern}': {e}", file=sys.stderr)

    def redact(self, text: str) -> Tuple[str, int]:
        """
        Redact secrets from text.

        Args:
            text: Text to redact

        Returns:
            Tuple of (redacted_text, redaction_count)
        """
        if not self.enabled or not text:
            return text, 0

        count = 0
        result = text

        for name, pattern, replacement_template in self._patterns:
            def make_replacement(match: re.Match, template: str = replacement_template) -> str:
                nonlocal count
                count += 1
                # P1 fix #8: Use lastindex to get the last captured group (usually the secret)
                # This fixes length calculation for multi-group patterns like HEX_SECRET
                if match.lastindex and match.lastindex >= 1:
                    matched = match.group(match.lastindex)  # Use last group, not always group 1
                else:
                    matched = match.group(0)

                # Format replacement with length
                repl = template.replace('{length}', str(len(matched)))

                # Handle backreferences like \1 (P1 fix: backrefs don't work with function replacement)
                # Replace \1, \2, etc. with actual match groups
                for i in range(1, pattern.groups + 1):
                    group_value = match.group(i)
                    if group_value is None:
                        group_value = ''
                    repl = repl.replace(f'\\{i}', group_value)

                return repl

            try:
                result = pattern.sub(make_replacement, result)
            except (re.error, TypeError) as e:
                import sys
                print(f"[FewWord] Warning: Redaction pattern '{name}' failed during substitution: {e}", file=sys.stderr)

        return result, count

    def test_pattern(self, text: str) -> List[Tuple[str, str]]:
        """
        Test which patterns match (for debugging).

        Returns list of (pattern_name, matched_text) tuples.
        """
        matches = []
        for name, pattern, _ in self._patterns:
            found = pattern.findall(text)
            if found:
                for match in found:
                    if isinstance(match, tuple):
                        for v in reversed(match):
                            if v:
                                match = v
                                break
                        else:
                            continue
                    matches.append((name, match))
        return matches


def create_redactor_from_config(config: dict) -> Redactor:
    """
    Create Redactor from FewWord config dict.

    Args:
        config: Config dict with 'redaction' section

    Returns:
        Configured Redactor instance
    """
    redaction_config = (config or {}).get('redaction', {})
    return Redactor(
        enabled=redaction_config.get('enabled', True),
        custom_patterns=redaction_config.get('patterns', []),
        replacement=redaction_config.get('replacement', '[REDACTED]')
    )


def redact_text(text: str,
                enabled: bool = True,
                custom_patterns: Optional[List[str]] = None) -> Tuple[str, int]:
    """
    Convenience function for one-shot redaction.

    Args:
        text: Text to redact
        enabled: If False, returns text unchanged
        custom_patterns: Additional patterns to redact

    Returns:
        Tuple of (redacted_text, redaction_count)
    """
    redactor = Redactor(enabled=enabled, custom_patterns=custom_patterns)
    return redactor.redact(text)


# === CLI for testing ===

def main():
    """CLI for testing redaction."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description='FewWord Redaction Tool')
    parser.add_argument('--file', '-f', help='Read from file instead of stdin')
    parser.add_argument('--test', '-t', action='store_true',
                        help='Test mode: show what would be redacted')
    parser.add_argument('--disabled', action='store_true',
                        help='Run with redaction disabled')
    parser.add_argument('--pattern', '-p', action='append',
                        help='Add custom pattern')
    # P0 fix #6: Make matched content display opt-in to prevent secret leakage
    parser.add_argument('--show-matches', action='store_true',
                        help='Show matched content (WARNING: may expose secrets)')

    args = parser.parse_args()

    if args.file:
        with open(args.file, 'r') as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    redactor = Redactor(
        enabled=not args.disabled,
        custom_patterns=args.pattern
    )

    if args.test:
        matches = redactor.test_pattern(text)
        if matches:
            print("Matches found:")
            for name, matched in matches:
                # P0 fix #6: Mask matched content by default to prevent secret exposure
                if args.show_matches:
                    # Only show if explicitly requested
                    print(f"  [{name}]: {matched[:50]}{'...' if len(matched) > 50 else ''}")
                else:
                    # Show masked version with length info only
                    print(f"  [{name}]: [MASKED:{len(matched)}chars]")
            if not args.show_matches:
                print("\nUse --show-matches to see actual matched content (WARNING: may expose secrets)")
        else:
            print("No matches found.")
    else:
        result, count = redactor.redact(text)
        print(result)
        print(f"\n--- Redacted {count} items ---", file=sys.stderr)


if __name__ == '__main__':
    main()
