---
description: "Find related failures through pattern matching"
arguments:
  - name: selector
    description: "Output ID, number, or command name to find correlations for"
    required: false
---

# Context Correlate

Find related failures through pattern matching. Computed on-demand, never stored in manifest.

## Usage

```bash
/context-correlate A1B2           # Show related failures for specific output
/context-correlate pytest         # Show related failures for latest pytest
/context-correlate --cluster      # Group recent failures by similarity
```

## Implementation

Run this Python script to compute correlations:

```python
#!/usr/bin/env python3
"""Context Correlate - Find related failures on-demand."""

import json
import os
import re
import sys
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

def get_cwd():
    return os.environ.get('FEWWORD_CWD', os.getcwd())

# P2 fix #15: Maximum file size to read (2MB)
MAX_OUTPUT_SIZE = 2 * 1024 * 1024

def read_bounded_text(path, max_size=MAX_OUTPUT_SIZE):
    """P2 fix #15: Read file with size limit to prevent loading arbitrarily large files."""
    try:
        file_size = path.stat().st_size
        if file_size > max_size:
            return None  # File too large
        return path.read_text(encoding='utf-8', errors='replace')
    except (OSError, IOError):
        return None

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

def resolve_id(selector, cwd):
    """Resolve selector to manifest entry."""
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'
    index_path = Path(cwd) / '.fewword' / 'index' / '.recent_index'

    entries = []
    try:
        with open(manifest_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get('type') == 'offload':
                        entries.append(entry)
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except (FileNotFoundError, IOError):
        return None

    # Number resolution
    if selector.isdigit():
        try:
            with open(index_path, 'r') as f:
                lines = f.readlines()
            num = int(selector)
            if 1 <= num <= len(lines):
                parts = lines[num - 1].strip().split(':')
                if len(parts) >= 2:
                    hex_id = parts[1].upper()
                    for entry in reversed(entries):
                        if entry.get('id', '').upper() == hex_id:
                            return entry
        except (FileNotFoundError, IndexError, ValueError, IOError):
            pass

    # Hex ID resolution
    if len(selector) == 8 and all(c in '0123456789ABCDEFabcdef' for c in selector):
        hex_id = selector.upper()
        for entry in reversed(entries):
            if entry.get('id', '').upper() == hex_id:
                return entry

    # Command name - find latest
    for entry in reversed(entries):
        cmd = entry.get('cmd_group') or entry.get('cmd')
        if cmd == selector:
            return entry

    return None

def extract_failure_signature(content, cmd_group):
    """Extract compact failure signature from output content."""
    if not content:
        return {}

    lines = content.split('\n')

    # Extract error types
    error_patterns = [
        r'(\w+Error):',
        r'(\w+Exception):',
        r'FAILED\s+(\S+)',
        r'error\[E\d+\]',
        r'panic:',
        r'FATAL',
    ]

    error_types = []
    for pattern in error_patterns:
        matches = re.findall(pattern, content)
        error_types.extend(matches[:3])
    # Use sorted() for deterministic output
    error_types = sorted(set(error_types))[:3]

    # Extract test files (for pytest, jest, etc.)
    test_files = []
    test_patterns = [
        r'(test_\w+\.py)',
        r'(\w+\.test\.[jt]s)',
        r'(\w+_test\.go)',
        r'(tests/\S+)',
    ]
    for pattern in test_patterns:
        matches = re.findall(pattern, content)
        test_files.extend(matches[:5])
    # Use sorted() for deterministic output
    test_files = sorted(set(test_files))[:5]

    # Hash of normalized last 10 lines (for fuzzy matching)
    last_lines = [l.strip() for l in lines[-10:] if l.strip()]
    # Normalize: remove timestamps, numbers
    normalized = []
    for line in last_lines:
        line = re.sub(r'\d+', 'N', line)
        line = re.sub(r'\s+', ' ', line)
        normalized.append(line)
    tail_hash = hashlib.md5('\n'.join(normalized).encode()).hexdigest()[:8]

    return {
        'error_types': error_types,
        'test_files': test_files,
        'tail_hash': tail_hash
    }

def compute_similarity(sig1, sig2):
    """Compute similarity score between two failure signatures."""
    if not sig1 or not sig2:
        return 0.0

    score = 0.0

    # Error types overlap
    errors1 = set(sig1.get('error_types', []))
    errors2 = set(sig2.get('error_types', []))
    if errors1 and errors2:
        overlap = len(errors1 & errors2)
        score += 0.3 * (overlap / max(len(errors1), len(errors2)))

    # Test files overlap
    files1 = set(sig1.get('test_files', []))
    files2 = set(sig2.get('test_files', []))
    if files1 and files2:
        overlap = len(files1 & files2)
        score += 0.4 * (overlap / max(len(files1), len(files2)))

    # Tail hash match
    if sig1.get('tail_hash') == sig2.get('tail_hash'):
        score += 0.3

    return score

def explain_match(sig1, sig2):
    """Generate human-readable explanation of why two failures match."""
    reasons = []

    # Error types
    errors1 = set(sig1.get('error_types', []))
    errors2 = set(sig2.get('error_types', []))
    common_errors = errors1 & errors2
    if common_errors:
        # Use min() for deterministic output
        reasons.append(f"same error: {min(common_errors)}")

    # Test files
    files1 = set(sig1.get('test_files', []))
    files2 = set(sig2.get('test_files', []))
    common_files = files1 & files2
    if common_files:
        # Use min() for deterministic output
        reasons.append(f"same test: {min(common_files)}")

    # Tail hash
    if sig1.get('tail_hash') == sig2.get('tail_hash'):
        reasons.append("similar output")

    return ", ".join(reasons) if reasons else "similar pattern"

def get_recent_failures(cwd, cmd_group=None, limit=50, exclude_id=None):
    """Get recent failures from manifest."""
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'
    failures = []

    try:
        with open(manifest_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get('type') != 'offload':
                        continue
                    if entry.get('exit_code', 0) == 0:
                        continue
                    if exclude_id and entry.get('id', '').upper() == exclude_id.upper():
                        continue
                    if cmd_group:
                        entry_group = entry.get('cmd_group') or entry.get('cmd')
                        if entry_group != cmd_group:
                            continue
                    failures.append(entry)
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
    except (FileNotFoundError, IOError):
        pass

    return list(reversed(failures))[:limit]

def find_correlations(current_entry, cwd):
    """Find correlated failures for a given entry."""
    if current_entry.get('exit_code', 0) == 0:
        return []  # Only correlate failures

    cmd_group = current_entry.get('cmd_group') or current_entry.get('cmd')
    current_id = current_entry.get('id', '')

    # Read current output
    path = Path(cwd) / current_entry.get('path', '')
    if not path.exists():
        return []

    # P2 fix #15: Use bounded read to prevent loading huge files
    content = read_bounded_text(path)
    if content is None:
        return []  # File too large or unreadable
    current_sig = extract_failure_signature(content, cmd_group)

    # Get recent failures
    candidates = get_recent_failures(cwd, cmd_group=cmd_group, limit=50, exclude_id=current_id)

    matches = []
    for entry in candidates:
        entry_path = Path(cwd) / entry.get('path', '')
        if not entry_path.exists():
            continue

        # P2 fix #15: Use bounded read to prevent loading huge files
        entry_content = read_bounded_text(entry_path)
        if entry_content is None:
            continue  # Skip files too large or unreadable
        entry_sig = extract_failure_signature(entry_content, cmd_group)

        score = compute_similarity(current_sig, entry_sig)
        if score > 0.3:  # Threshold
            matches.append({
                'entry': entry,
                'score': score,
                'reason': explain_match(current_sig, entry_sig)
            })

    # Sort by score descending
    matches.sort(key=lambda x: -x['score'])
    return matches[:5]

def cluster_failures(cwd, limit=20):
    """Cluster recent failures by similarity."""
    failures = get_recent_failures(cwd, limit=limit)

    if not failures:
        return []

    # Build signatures for all failures
    signatures = {}
    for entry in failures:
        entry_path = Path(cwd) / entry.get('path', '')
        if entry_path.exists():
            # P2 fix #15: Use bounded read to prevent loading huge files
            content = read_bounded_text(entry_path)
            if content is None:
                continue  # Skip files too large or unreadable
            cmd_group = entry.get('cmd_group') or entry.get('cmd')
            signatures[entry['id']] = extract_failure_signature(content, cmd_group)

    # Simple clustering: group by tail_hash
    clusters = defaultdict(list)
    for entry in failures:
        sig = signatures.get(entry['id'], {})
        cluster_key = sig.get('tail_hash', 'unknown')
        clusters[cluster_key].append(entry)

    return [(k, v) for k, v in clusters.items() if len(v) > 1]

def main():
    args = sys.argv[1:]
    cwd = get_cwd()

    # Cluster mode
    if '--cluster' in args:
        clusters = cluster_failures(cwd)
        if not clusters:
            print("No failure clusters found.")
            print("Clusters form when multiple failures have similar output patterns.")
            sys.exit(0)

        print("Failure Clusters")
        print("=" * 50)
        print("")

        for i, (cluster_key, entries) in enumerate(clusters[:5], 1):
            print(f"Cluster {i}: {len(entries)} similar failures")
            for entry in entries[:3]:
                cmd = entry.get('cmd_group') or entry.get('cmd', '?')
                age = calculate_age(entry.get('created_at', ''))
                entry_id = entry.get('id', '????')[:8]
                print(f"  [{entry_id}] {cmd} ({age})")
            if len(entries) > 3:
                print(f"  ... and {len(entries) - 3} more")
            print("")

        sys.exit(0)

    # Single output correlation mode
    if not args or args[0].startswith('--'):
        print("Usage:")
        print("  /context-correlate <selector>  # Find related failures")
        print("  /context-correlate --cluster   # Group failures by similarity")
        sys.exit(1)

    selector = args[0]
    entry = resolve_id(selector, cwd)

    if not entry:
        print(f"Error: Could not resolve '{selector}' to an output.")
        print("Use /context-recent to see available outputs.")
        sys.exit(1)

    if entry.get('exit_code', 0) == 0:
        print(f"[{entry.get('id')}] is not a failure (exit=0).")
        print("Correlation only works for failed outputs.")
        sys.exit(0)

    # Find correlations
    matches = find_correlations(entry, cwd)

    cmd = entry.get('cmd_group') or entry.get('cmd', '?')
    entry_id = entry.get('id', '????')[:8]

    print(f"Related failures for [{entry_id}] {cmd}")
    print("=" * 50)

    if not matches:
        print("")
        print("No related failures found.")
        print(f"This may be the first failure of this type for '{cmd}'.")
        sys.exit(0)

    print("")
    for match in matches:
        m_entry = match['entry']
        m_id = m_entry.get('id', '????')[:8]
        m_cmd = m_entry.get('cmd_group') or m_entry.get('cmd', '?')
        m_age = calculate_age(m_entry.get('created_at', ''))
        m_reason = match['reason']
        score_pct = int(match['score'] * 100)

        print(f"  [{m_id}] {m_cmd} ({m_age}) - {score_pct}% match")
        print(f"    └─ {m_reason}")
        print("")

    print(f"Tip: /context-diff {entry_id} {matches[0]['entry'].get('id', '')[:8]}")

if __name__ == '__main__':
    main()
```

## Output Example

### Single output correlation
```
Related failures for [A1B2C3D4] pytest
==================================================

  [C3D4E5F6] pytest (2h ago) - 85% match
    └─ same test: test_auth.py, same error: AssertionError

  [E5F6G7H8] pytest (1d ago) - 60% match
    └─ same test: test_auth.py

Tip: /context-diff A1B2 C3D4
```

### Cluster mode
```
Failure Clusters
==================================================

Cluster 1: 3 similar failures
  [A1B2C3D4] pytest (5m ago)
  [C3D4E5F6] pytest (2h ago)
  [E5F6G7H8] pytest (1d ago)

Cluster 2: 2 similar failures
  [G7H8I9J0] npm (1h ago)
  [K1L2M3N4] npm (3h ago)
```

## Notes

- Correlations are computed on-demand (never stored in manifest)
- Only correlates within same cmd_group (pytest with pytest, not npm)
- Signals used: error types, test files, normalized tail hash
- Threshold: 30% similarity required to show as match
- Limited to last 50 failures to prevent full history scan
- Use `/context-diff` to compare correlated failures
- **Tool failures only**: Correlate only works with offload entries that have failed (exit_code != 0). Manual and export entries are not supported - they lack the failure semantics needed for correlation analysis.
