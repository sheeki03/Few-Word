#!/usr/bin/env python3
"""
FewWord Correlation Module

Computes failure correlations ON-DEMAND (never stored in manifest).
Finds related failures by comparing failure signatures.

Key design decisions:
- Correlations are computed when requested, not at capture time
- Never store correlation results in manifest (keeps it simple)
- Only correlate within same cmd_group (pytest with pytest, not npm)
- Limit scan to recent failures (50) to prevent full history scan
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# Import failure signature module
try:
    from failure_signature import (
        extract_failure_signature,
        compute_similarity,
        explain_similarity
    )
except ImportError:
    # Inline fallback implementations
    import re
    import hashlib

    def extract_failure_signature(content: str, cmd_group: Optional[str] = None) -> Dict:
        if not content:
            return {}

        # P2 fix #10: Use sorted(set(...)) for deterministic output
        error_types = sorted(set(re.findall(r'(\w+Error):', content)))[:3]
        test_files = sorted(set(re.findall(r'(test_\w+\.py)', content)))[:5]

        lines = [l.strip() for l in content.split('\n') if l.strip()][-10:]
        normalized = [re.sub(r'\d+', 'N', l) for l in lines]
        tail_hash = hashlib.md5('\n'.join(normalized).encode()).hexdigest()[:8]

        return {
            'error_types': error_types,
            'test_files': test_files,
            'tail_hash': tail_hash
        }

    def compute_similarity(sig1: Dict, sig2: Dict) -> float:
        if not sig1 or not sig2:
            return 0.0

        score = 0.0
        errors1 = set(sig1.get('error_types', []))
        errors2 = set(sig2.get('error_types', []))
        if errors1 and errors2:
            score += 0.3 * len(errors1 & errors2) / max(len(errors1), len(errors2))

        files1 = set(sig1.get('test_files', []))
        files2 = set(sig2.get('test_files', []))
        if files1 and files2:
            score += 0.4 * len(files1 & files2) / max(len(files1), len(files2))

        if sig1.get('tail_hash') == sig2.get('tail_hash'):
            score += 0.3

        return score

    def explain_similarity(sig1: Dict, sig2: Dict) -> str:
        reasons = []
        common_errors = set(sig1.get('error_types', [])) & set(sig2.get('error_types', []))
        if common_errors:
            # P2 fix #12: Use min() or sorted()[0] for deterministic output
            reasons.append(f"same error: {min(common_errors)}")
        common_files = set(sig1.get('test_files', [])) & set(sig2.get('test_files', []))
        if common_files:
            # P2 fix #12: Use min() for deterministic output
            reasons.append(f"same test: {min(common_files)}")
        if sig1.get('tail_hash') == sig2.get('tail_hash'):
            reasons.append("similar output")
        return ", ".join(reasons) if reasons else "similar pattern"


# Correlation thresholds
SIMILARITY_THRESHOLD = 0.3  # Minimum score to consider related
MAX_CANDIDATES = 50  # Max failures to scan
MAX_RESULTS = 5  # Max correlations to return


def get_manifest_failures(
    cwd: str,
    cmd_group: Optional[str] = None,
    exclude_id: Optional[str] = None,
    limit: int = MAX_CANDIDATES
) -> List[Dict]:
    """
    Get recent failures from manifest.

    Args:
        cwd: Working directory
        cmd_group: Filter by command group (optional)
        exclude_id: ID to exclude from results
        limit: Maximum entries to return

    Returns:
        List of manifest entries (most recent first)
    """
    manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'
    failures = []

    if not manifest_path.exists():
        return failures

    try:
        with open(manifest_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)

                    # Only offload entries
                    if entry.get('type') != 'offload':
                        continue

                    # Only failures
                    if entry.get('exit_code', 0) == 0:
                        continue

                    # Exclude specified ID
                    if exclude_id and entry.get('id', '').upper() == exclude_id.upper():
                        continue

                    # Filter by cmd_group
                    if cmd_group:
                        entry_group = entry.get('cmd_group') or entry.get('cmd')
                        if entry_group != cmd_group:
                            continue

                    failures.append(entry)
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass

    # Return most recent first, limited
    return list(reversed(failures))[:limit]


def get_entry_signature(entry: Dict, cwd: str) -> Optional[Dict]:
    """
    Get or compute failure signature for an entry.

    First checks if signature is stored in manifest entry,
    otherwise reads file and computes signature.

    Args:
        entry: Manifest entry
        cwd: Working directory

    Returns:
        Failure signature dict, or None if unavailable
    """
    # Check for stored signature (compact format)
    if 'failure_sig' in entry:
        return entry['failure_sig']

    # Check for compact format fields
    if 'err' in entry or 'tst' in entry or 'th' in entry:
        return {
            'error_types': entry.get('err', []),
            'test_files': entry.get('tst', []),
            'tail_hash': entry.get('th', '')
        }

    # Compute from file
    path_str = entry.get('path')
    if not path_str:
        return None
    path = Path(cwd) / path_str
    if not path.is_file():
        return None

    try:
        # P2 fix #11: Add explicit encoding to prevent platform-dependent failures
        content = path.read_text(encoding='utf-8', errors='replace')
        cmd_group = entry.get('cmd_group') or entry.get('cmd')
        return extract_failure_signature(content, cmd_group)
    except Exception:
        return None


def find_correlations(
    current_entry: Dict,
    cwd: str,
    threshold: float = SIMILARITY_THRESHOLD,
    max_results: int = MAX_RESULTS
) -> List[Dict]:
    """
    Find correlated failures for a given entry.

    Args:
        current_entry: The entry to find correlations for
        cwd: Working directory
        threshold: Minimum similarity score
        max_results: Maximum correlations to return

    Returns:
        List of dicts with keys: entry, score, reason
    """
    # Only correlate failures
    if current_entry.get('exit_code', 0) == 0:
        return []

    current_id = current_entry.get('id', '')
    cmd_group = current_entry.get('cmd_group') or current_entry.get('cmd')

    # Get current signature
    current_sig = get_entry_signature(current_entry, cwd)
    if not current_sig:
        return []

    # Get candidate failures
    candidates = get_manifest_failures(
        cwd,
        cmd_group=cmd_group,
        exclude_id=current_id,
        limit=MAX_CANDIDATES
    )

    # Score each candidate
    matches = []
    for entry in candidates:
        entry_sig = get_entry_signature(entry, cwd)
        if not entry_sig:
            continue

        score = compute_similarity(current_sig, entry_sig)
        if score >= threshold:
            matches.append({
                'entry': entry,
                'score': score,
                'reason': explain_similarity(current_sig, entry_sig)
            })

    # Sort by score descending
    matches.sort(key=lambda x: -x['score'])

    return matches[:max_results]


def cluster_failures(
    cwd: str,
    limit: int = 20
) -> List[Tuple[str, List[Dict]]]:
    """
    Cluster recent failures by similarity.

    Uses tail_hash as primary clustering key for simplicity.

    Args:
        cwd: Working directory
        limit: Maximum failures to consider

    Returns:
        List of (cluster_key, entries) tuples, only clusters with 2+ entries
    """
    failures = get_manifest_failures(cwd, limit=limit)

    if not failures:
        return []

    # Group by tail_hash
    clusters = defaultdict(list)
    for entry in failures:
        sig = get_entry_signature(entry, cwd)
        if sig:
            cluster_key = sig.get('tail_hash', 'unknown')
            clusters[cluster_key].append(entry)

    # Return only clusters with 2+ entries
    return [(k, v) for k, v in clusters.items() if len(v) >= 2]


def get_correlation_summary(correlations: List[Dict]) -> str:
    """
    Generate a one-line summary of correlations.

    Args:
        correlations: List of correlation results

    Returns:
        Summary string for pointer display
    """
    if not correlations:
        return ""

    count = len(correlations)
    top = correlations[0]
    top_id = top.get('entry', {}).get('id', '????')[:4]
    top_reason = (str(top.get('reason', ''))).split(',')[0] or 'unknown'

    if count == 1:
        return f"Similar to [{top_id}] ({top_reason})"
    else:
        return f"Similar to [{top_id}] +{count-1} more ({top_reason})"


# === CLI for testing ===

def main():
    """CLI for testing correlation."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: correlation.py <command>")
        print("")
        print("Commands:")
        print("  find <id>     Find correlations for output")
        print("  cluster       Show failure clusters")
        sys.exit(1)

    cwd = os.environ.get('FEWWORD_CWD', os.getcwd())
    command = sys.argv[1]

    if command == 'find' and len(sys.argv) >= 3:
        entry_id = sys.argv[2].upper()

        # Find entry (P2 fix: add file read error handling)
        manifest_path = Path(cwd) / '.fewword' / 'index' / 'tool_outputs.jsonl'
        entry = None

        if not manifest_path.exists():
            print(f"Error: Manifest file not found at {manifest_path}")
            sys.exit(1)

        try:
            with open(manifest_path, 'r') as f:
                for line in f:
                    try:
                        e = json.loads(line)
                        if e.get('id', '').upper() == entry_id:
                            entry = e
                    except (json.JSONDecodeError, KeyError, TypeError):
                        pass
        except (IOError, OSError) as err:
            print(f"Error reading manifest: {err}")
            sys.exit(1)

        if not entry:
            print(f"Entry not found: {entry_id}")
            sys.exit(1)

        correlations = find_correlations(entry, cwd)

        if not correlations:
            print(f"No correlations found for [{entry_id}]")
        else:
            print(f"Correlations for [{entry_id}]:")
            for c in correlations:
                c_entry = c['entry']
                c_id = c_entry.get('id', '????')[:8]
                score = c['score']
                reason = c['reason']
                print(f"  [{c_id}] {score:.0%} - {reason}")

    elif command == 'cluster':
        clusters = cluster_failures(cwd)

        if not clusters:
            print("No failure clusters found")
        else:
            print(f"Found {len(clusters)} clusters:")
            for key, entries in clusters:
                print(f"\nCluster {key}:")
                for e in entries[:5]:
                    cmd = e.get('cmd_group') or e.get('cmd', '?')
                    e_id = e.get('id', '????')[:8]
                    print(f"  [{e_id}] {cmd}")
                if len(entries) > 5:
                    print(f"  ...and {len(entries)-5} more")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == '__main__':
    main()
