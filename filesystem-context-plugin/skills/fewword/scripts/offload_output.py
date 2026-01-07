#!/usr/bin/env python3
"""
Offload large tool outputs to filesystem, return summary reference.

Usage:
    echo "large output" | python offload_output.py --tool search
    python offload_output.py --tool query --input results.json
"""

import argparse
import sys
import os
from datetime import datetime
from pathlib import Path


SCRATCH_DIR = Path(".fsctx/scratch/tool_outputs")
TOKEN_THRESHOLD = 2000  # Approximate token count threshold


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token)."""
    return len(text) // 4


def extract_summary(text: str, max_chars: int = 200) -> str:
    """Extract a meaningful summary from the beginning of text."""
    lines = text.strip().split('\n')
    summary_lines = []
    char_count = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if char_count + len(line) > max_chars:
            break
        summary_lines.append(line)
        char_count += len(line)
    
    summary = ' '.join(summary_lines)
    if len(text) > len(summary):
        summary += "..."
    return summary


def offload_output(tool_name: str, output: str) -> str:
    """
    Offload output if it exceeds threshold.
    Returns either the original output or a file reference.
    """
    tokens = estimate_tokens(output)
    
    if tokens < TOKEN_THRESHOLD:
        return output
    
    # Ensure directory exists
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    
    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{tool_name}_{timestamp}.txt"
    file_path = SCRATCH_DIR / filename
    
    # Write output
    file_path.write_text(output)
    
    # Generate reference
    summary = extract_summary(output)
    line_count = output.count('\n') + 1
    
    return f"""[Output offloaded to filesystem]
- File: {file_path}
- Size: {len(output):,} chars (~{tokens:,} tokens)
- Lines: {line_count:,}
- Summary: {summary}

Use grep/sed/tail to retrieve specific content."""


def main():
    parser = argparse.ArgumentParser(description="Offload large tool outputs")
    parser.add_argument("--tool", required=True, help="Tool name for filename")
    parser.add_argument("--input", help="Input file (default: stdin)")
    parser.add_argument("--threshold", type=int, default=TOKEN_THRESHOLD,
                        help=f"Token threshold (default: {TOKEN_THRESHOLD})")
    
    args = parser.parse_args()
    
    global TOKEN_THRESHOLD
    TOKEN_THRESHOLD = args.threshold
    
    # Read input
    if args.input:
        output = Path(args.input).read_text()
    else:
        output = sys.stdin.read()
    
    # Process and print result
    result = offload_output(args.tool, output)
    print(result)


if __name__ == "__main__":
    main()
