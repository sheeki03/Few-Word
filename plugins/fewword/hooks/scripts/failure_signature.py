#!/usr/bin/env python3
"""
FewWord Failure Signature Module

Extracts compact failure signatures from command output for correlation.
Signals are stored in manifest for fast lookup, correlations computed on-demand.

Signals extracted:
- error_types: First 3 unique error class names (AssertionError, TypeError, etc.)
- test_files: First 5 test file names mentioned
- tail_hash: Hash of normalized last 10 lines (for fuzzy matching)

Security notes:
- Never stores full error messages (may contain secrets)
- Only stores normalized patterns, not actual values
- Hash is of structure, not content
"""

from __future__ import annotations

import re
import hashlib
from typing import Dict, List, Optional


# Error patterns by language/framework
ERROR_PATTERNS = [
    # Python
    (r'(\w+Error):', 'python_error'),
    (r'(\w+Exception):', 'python_exception'),
    (r'(\w+Warning):', 'python_warning'),

    # JavaScript/TypeScript
    (r'(\w+Error):', 'js_error'),
    (r'TypeError:', 'js_type_error'),
    (r'ReferenceError:', 'js_ref_error'),

    # Rust
    (r"error\[(E\d+)\]", 'rust_error'),
    (r"panicked at", 'rust_panic'),

    # Go
    (r'panic:', 'go_panic'),
    (r'fatal error:', 'go_fatal'),

    # Generic
    (r'FAILED\s+(\S+)', 'test_failed'),
    (r'FATAL', 'fatal'),
    (r'CRITICAL', 'critical'),
    (r'Traceback', 'traceback'),
]

# Test file patterns
TEST_FILE_PATTERNS = [
    # Python
    r'(test_\w+\.py)',
    r'(\w+_test\.py)',
    r'(tests/\S+\.py)',

    # JavaScript/TypeScript
    r'(\w+\.test\.[jt]sx?)',
    r'(\w+\.spec\.[jt]sx?)',
    r'(__tests__/[A-Za-z0-9_.-]+\.[jt]sx?)',

    # Go
    r'(\w+_test\.go)',

    # Rust
    r'(tests/\S+\.rs)',

    # Generic
    r'(test\S+\.\w+)',
]


def extract_error_types(content: str, max_count: int = 3) -> List[str]:
    """
    Extract unique error type names from output.

    Args:
        content: Command output text
        max_count: Maximum number of error types to return

    Returns:
        List of error type names (e.g., ['AssertionError', 'KeyError'])
    """
    errors = []
    seen = set()

    for pattern, _ in ERROR_PATTERNS:
        matches = re.findall(pattern, content)
        for match in matches:
            # Normalize: strip whitespace, take first part if tuple
            if isinstance(match, tuple):
                match = match[0]
            match = match.strip()

            if match and match not in seen:
                seen.add(match)
                errors.append(match)

                if len(errors) >= max_count:
                    return errors

    return errors


def extract_test_files(content: str, max_count: int = 5) -> List[str]:
    """
    Extract test file names from output.

    Args:
        content: Command output text
        max_count: Maximum number of test files to return

    Returns:
        List of test file names (e.g., ['test_auth.py', 'test_api.py'])
    """
    files = []
    seen = set()

    for pattern in TEST_FILE_PATTERNS:
        matches = re.findall(pattern, content)
        for match in matches:
            # Normalize: take basename only
            if '/' in match:
                match = match.split('/')[-1]

            if match and match not in seen:
                seen.add(match)
                files.append(match)

                if len(files) >= max_count:
                    return files

    return files


def compute_tail_hash(content: str, num_lines: int = 10) -> str:
    """
    Compute hash of normalized last N lines.

    Normalization:
    - Replace all numbers with 'N'
    - Collapse whitespace
    - Remove empty lines
    - Strip ANSI codes

    Args:
        content: Command output text
        num_lines: Number of lines from end to hash

    Returns:
        8-character hex hash of normalized tail
    """
    lines = content.split('\n')

    # Get last N non-empty lines
    tail_lines = []
    for line in reversed(lines):
        line = line.strip()
        if line:
            tail_lines.append(line)
            if len(tail_lines) >= num_lines:
                break

    tail_lines.reverse()

    # Normalize each line
    normalized = []
    for line in tail_lines:
        # Strip ANSI codes
        line = re.sub(r'\x1b\[[0-9;]*m', '', line)
        # Replace numbers with N
        line = re.sub(r'\d+', 'N', line)
        # Collapse whitespace
        line = re.sub(r'\s+', ' ', line)
        normalized.append(line)

    # Hash the normalized content
    content_hash = hashlib.md5('\n'.join(normalized).encode()).hexdigest()
    return content_hash[:8]


def extract_failure_signature(content: str, cmd_group: Optional[str] = None) -> Dict:
    """
    Extract complete failure signature from command output.

    Args:
        content: Command output text
        cmd_group: Optional command group for context-aware extraction

    Returns:
        Dict with keys: error_types, test_files, tail_hash
    """
    if not content:
        return {}

    return {
        'error_types': extract_error_types(content),
        'test_files': extract_test_files(content),
        'tail_hash': compute_tail_hash(content)
    }


def signature_to_manifest_format(signature: Dict) -> Dict:
    """
    Convert signature to compact format for manifest storage.

    Args:
        signature: Full signature dict

    Returns:
        Compact dict suitable for manifest entry
    """
    if not signature:
        return {}

    # Only include non-empty fields
    compact = {}

    if signature.get('error_types'):
        compact['err'] = signature['error_types']

    if signature.get('test_files'):
        compact['tst'] = signature['test_files']

    if signature.get('tail_hash'):
        compact['th'] = signature['tail_hash']

    return compact


def compute_similarity(sig1: Dict, sig2: Dict) -> float:
    """
    Compute similarity score between two failure signatures.

    Weights:
    - Error types overlap: 30%
    - Test files overlap: 40%
    - Tail hash match: 30%

    Args:
        sig1: First signature
        sig2: Second signature

    Returns:
        Similarity score from 0.0 to 1.0
    """
    if not sig1 or not sig2:
        return 0.0

    score = 0.0

    # Error types overlap (30%)
    errors1 = set(sig1.get('error_types', []) or sig1.get('err', []) or [])
    errors2 = set(sig2.get('error_types', []) or sig2.get('err', []) or [])
    if errors1 and errors2:
        overlap = len(errors1 & errors2)
        max_len = max(len(errors1), len(errors2))
        score += 0.3 * (overlap / max_len)

    # Test files overlap (40%)
    files1 = set(sig1.get('test_files', []) or sig1.get('tst', []) or [])
    files2 = set(sig2.get('test_files', []) or sig2.get('tst', []) or [])
    if files1 and files2:
        overlap = len(files1 & files2)
        max_len = max(len(files1), len(files2))
        score += 0.4 * (overlap / max_len)

    # Tail hash match (30%)
    hash1 = sig1.get('tail_hash') or sig1.get('th')
    hash2 = sig2.get('tail_hash') or sig2.get('th')
    if hash1 and hash2 and hash1 == hash2:
        score += 0.3

    return score


def explain_similarity(sig1: Dict, sig2: Dict) -> str:
    """
    Generate human-readable explanation of why signatures match.

    Args:
        sig1: First signature
        sig2: Second signature

    Returns:
        Explanation string (e.g., "same error: AssertionError, same test: test_auth.py")
    """
    reasons = []

    # Error types
    errors1 = set(sig1.get('error_types', []) or sig1.get('err', []))
    errors2 = set(sig2.get('error_types', []) or sig2.get('err', []))
    common_errors = errors1 & errors2
    if common_errors:
        reasons.append(f"same error: {list(common_errors)[0]}")

    # Test files
    files1 = set(sig1.get('test_files', []) or sig1.get('tst', []))
    files2 = set(sig2.get('test_files', []) or sig2.get('tst', []))
    common_files = files1 & files2
    if common_files:
        reasons.append(f"same test: {list(common_files)[0]}")

    # Tail hash
    hash1 = sig1.get('tail_hash') or sig1.get('th')
    hash2 = sig2.get('tail_hash') or sig2.get('th')
    if hash1 and hash2 and hash1 == hash2:
        reasons.append("similar output")

    return ", ".join(reasons) if reasons else "similar pattern"


# === CLI for testing ===

def main():
    """CLI for testing failure signature extraction."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: failure_signature.py <file> [--json]")
        print("       failure_signature.py --compare <file1> <file2>")
        sys.exit(1)

    if sys.argv[1] == '--compare' and len(sys.argv) < 4:
        print("Usage: failure_signature.py --compare <file1> <file2>")
        sys.exit(1)

    if sys.argv[1] == '--compare' and len(sys.argv) >= 4:
        # Compare two files (P2 fix: add file I/O guards)
        try:
            with open(sys.argv[2], 'r') as f:
                content1 = f.read()
        except (IOError, OSError) as e:
            print(f"Error reading {sys.argv[2]}: {e}")
            sys.exit(1)
        try:
            with open(sys.argv[3], 'r') as f:
                content2 = f.read()
        except (IOError, OSError) as e:
            print(f"Error reading {sys.argv[3]}: {e}")
            sys.exit(1)

        sig1 = extract_failure_signature(content1)
        sig2 = extract_failure_signature(content2)

        score = compute_similarity(sig1, sig2)
        explanation = explain_similarity(sig1, sig2)

        print(f"Similarity: {score:.0%}")
        print(f"Reason: {explanation}")
        print()
        print(f"Sig1: {sig1}")
        print(f"Sig2: {sig2}")
    else:
        # Extract signature from file (P2 fix: add file I/O guards)
        # Handle --json flag appearing before filename
        if sys.argv[1] == '--json':
            if len(sys.argv) < 3:
                print("Usage: failure_signature.py <file> [--json]")
                print("       failure_signature.py --json <file>")
                sys.exit(1)
            file_idx = 2
        else:
            file_idx = 1
        try:
            with open(sys.argv[file_idx], 'r') as f:
                content = f.read()
        except (IOError, OSError) as e:
            print(f"Error reading {sys.argv[file_idx]}: {e}")
            sys.exit(1)

        signature = extract_failure_signature(content)

        if '--json' in sys.argv:
            import json
            print(json.dumps(signature, indent=2))
        else:
            print("Failure Signature:")
            print(f"  Error types: {signature.get('error_types', [])}")
            print(f"  Test files:  {signature.get('test_files', [])}")
            print(f"  Tail hash:   {signature.get('tail_hash', '')}")


if __name__ == '__main__':
    main()
