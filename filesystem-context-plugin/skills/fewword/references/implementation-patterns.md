# Implementation Patterns

Detailed code examples for filesystem-based context engineering.

## Tool Output Offloading

### Python Implementation

```python
import os
from datetime import datetime
from pathlib import Path

SCRATCH_DIR = Path(".fsctx/scratch/tool_outputs")
TOKEN_THRESHOLD = 2000  # ~500 words

def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token"""
    return len(text) // 4

def handle_tool_output(tool_name: str, output: str) -> str:
    """Offload large outputs, return reference + summary."""
    if estimate_tokens(output) < TOKEN_THRESHOLD:
        return output

    # Ensure directory exists
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    # Write to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{tool_name}_{timestamp}.txt"
    file_path = SCRATCH_DIR / filename
    file_path.write_text(output)

    # Extract summary (first meaningful content)
    lines = output.strip().split('\n')
    summary_lines = [l for l in lines[:10] if l.strip()][:3]
    summary = ' '.join(summary_lines)[:200]

    return f"[Output ({len(output)} chars) saved to {file_path}. Preview: {summary}...]"
```

### Bash One-Liner

```bash
# For shell command outputs
output=$(some_command 2>&1)
if [ ${#output} -gt 8000 ]; then
  file=".fsctx/scratch/tool_outputs/cmd_$(date +%s).txt"
  mkdir -p "$(dirname "$file")"
  echo "$output" > "$file"
  echo "[Output saved to $file. Lines: $(echo "$output" | wc -l)]"
else
  echo "$output"
fi
```

## Plan Persistence

### YAML Structure

```yaml
# .fsctx/index/current_plan.yaml
meta:
  created: "2025-01-07T10:00:00Z"
  last_updated: "2025-01-07T14:30:00Z"

objective: "Implement user authentication system"
status: in_progress
success_criteria:
  - "JWT token generation works"
  - "Refresh token rotation implemented"
  - "All endpoints protected"

current_focus: "step-2"

steps:
  - id: step-1
    description: "Set up auth dependencies"
    status: completed
    notes: "Using python-jose for JWT"

  - id: step-2
    description: "Implement token generation"
    status: in_progress
    blockers: []

  - id: step-3
    description: "Add middleware protection"
    status: pending
    depends_on: [step-2]

decisions:
  - decision: "Use RS256 for JWT signing"
    rationale: "Better security for production"
    date: "2025-01-07"
```

### Plan Operations

```python
import yaml
from pathlib import Path
from datetime import datetime

PLAN_FILE = Path(".fsctx/index/current_plan.yaml")

def load_plan() -> dict:
    if PLAN_FILE.exists():
        return yaml.safe_load(PLAN_FILE.read_text())
    return None

def update_step_status(step_id: str, status: str, notes: str = None):
    plan = load_plan()
    for step in plan['steps']:
        if step['id'] == step_id:
            step['status'] = status
            if notes:
                step['notes'] = notes
    plan['meta']['last_updated'] = datetime.now().isoformat()
    PLAN_FILE.write_text(yaml.dump(plan, default_flow_style=False))

def get_current_focus() -> dict:
    plan = load_plan()
    focus_id = plan.get('current_focus')
    for step in plan['steps']:
        if step['id'] == focus_id:
            return step
    return None
```

## Sub-Agent Workspaces

### Directory Setup

```bash
mkdir -p .fsctx/scratch/subagents/{research,code,test,coordinator}
```

### Agent Output Format

```markdown
<!-- .fsctx/scratch/subagents/research/findings.md -->
# Research Findings

## Topic: Authentication Libraries

### Evaluated Options
1. **python-jose** - Recommended
   - Pros: Well-maintained, RS256 support
   - Cons: Slightly larger API surface

2. **PyJWT**
   - Pros: Simple API
   - Cons: Less algorithm support

### Recommendation
Use python-jose with RS256 signing.

### Sources
- https://github.com/mpdavis/python-jose
- JWT.io best practices guide

---
Updated: 2025-01-07T14:00:00Z
```

### Coordinator Pattern

```python
from pathlib import Path
import glob

def synthesize_agent_findings() -> str:
    """Read all agent findings and create synthesis."""
    findings = []

    for agent_dir in Path(".fsctx/scratch/subagents").iterdir():
        if agent_dir.is_dir() and agent_dir.name != "coordinator":
            findings_file = agent_dir / "findings.md"
            if findings_file.exists():
                findings.append({
                    'agent': agent_dir.name,
                    'content': findings_file.read_text()
                })

    # Write synthesis
    synthesis = "# Synthesis\n\n"
    for f in findings:
        synthesis += f"## From {f['agent']}\n{f['content']}\n\n"

    Path(".fsctx/scratch/subagents/coordinator/synthesis.md").write_text(synthesis)
    return synthesis
```

## Targeted Retrieval Commands

### Find Recent Errors

```bash
# Last 5 lines around each error
grep -B 2 -A 5 -i "error\|exception\|failed" .fsctx/scratch/tool_outputs/*.txt

# Just filenames with errors
grep -l "error" .fsctx/scratch/tool_outputs/*.txt
```

### Search Specific Sections

```bash
# Find function definitions
grep -n "^def \|^async def " .fsctx/scratch/tool_outputs/code_*.txt

# Extract JSON from mixed output
grep -o '{.*}' .fsctx/scratch/tool_outputs/api_response.txt | head -1
```

### Read Line Ranges

```bash
# Lines 100-150 of a file
sed -n '100,150p' .fsctx/scratch/tool_outputs/large_file.txt

# Last 50 lines
tail -50 .fsctx/scratch/tool_outputs/build_log.txt

# First 20 lines
head -20 .fsctx/scratch/tool_outputs/query_results.txt
```

## History Reference Pattern

```python
from pathlib import Path
from datetime import datetime

HISTORY_DIR = Path(".fsctx/memory/history")

def archive_conversation(messages: list, summary: str) -> str:
    """Archive full history, return reference for new context."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_file = HISTORY_DIR / f"session_{session_id}.txt"

    # Write full history
    content = "\n\n---\n\n".join([
        f"[{m['role']}]: {m['content']}" for m in messages
    ])
    history_file.write_text(content)

    # Return reference for new context
    return f"""## Previous Session Summary
{summary}

Full conversation history available at: {history_file}
Use grep to search for specific details if needed.
"""
```
