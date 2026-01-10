---
description: Show recent offloaded outputs from scratch
---

# Context Recent

Show recent offloaded outputs (including manual saves) with numbered list for easy reference. Primary recovery path after context compaction.

## Output Format

```
Recent Offloaded Outputs
────────────────────────
 #  ID       CMD/TITLE    EXIT   SIZE    AGE     STATUS
 1) A1B2     pytest       1      45K     2h      exists
 2) C3D4     npm          0      12K     3h      exists
 3) E5F6     [manual] Ex  -      15K     1h      exists
 4) G7H8     ls           0      900B    4h      cleaned

Use: /context-open 1  or  /context-open pytest  or  /context-open A1B2
```

## Steps

1. Get session ID and set up paths:
   ```bash
   manifest=".fewword/index/tool_outputs.jsonl"
   session_file=".fewword/index/session.json"
   helper="$CLAUDE_PLUGIN_ROOT/hooks/scripts/context_helpers.py"

   # Get current session ID
   session_id=""
   if [ -f "$session_file" ]; then
     session_id=$(grep -o '"session_id":"[^"]*"' "$session_file" | cut -d'"' -f4)
   fi

   if [ ! -f "$manifest" ]; then
     echo "No manifest found. Run a command that produces large output first."
     exit 0
   fi
   ```

2. Read manifest and build numbered list:
   ```bash
   echo "Recent Offloaded Outputs"
   echo "────────────────────────"
   printf " %-3s %-8s %-12s %-4s %-7s %-6s %s\n" "#" "ID" "CMD/TITLE" "EXIT" "SIZE" "AGE" "STATUS"

   # Prepare index file (session-scoped)
   index_path=".fewword/index/.recent_index_${session_id:-default}"
   pointer_path=".fewword/index/.recent_index"

   # Use Python to parse entries (handles offload, manual, export types)
   python3 -c "
import json
import os
from datetime import datetime, timezone
from pathlib import Path

manifest_path = '$manifest'
index_path = '$index_path'
helper = '$helper'

# Read entries (last 30 lines, filter to offload/manual/export)
entries = []
try:
    with open(manifest_path, 'r') as f:
        lines = f.readlines()[-30:]
    for line in lines:
        try:
            entry = json.loads(line.strip())
            if entry.get('type') in ('offload', 'manual', 'export'):
                entries.append(entry)
        except:
            pass
except:
    pass

# Take last 10
entries = entries[-10:]

# Build index file
index_lines = []

for num, entry in enumerate(entries, 1):
    entry_type = entry.get('type', 'offload')
    id_str = entry.get('id', '????????')[:8]

    # Get label: cmd for offload, title for manual/export with type prefix
    if entry_type == 'offload':
        label = entry.get('cmd', 'unknown')[:12]
    else:
        title = entry.get('title', entry_type)[:8]
        label = f'[{entry_type[:3]}] {title}'[:12]

    # Exit code: - for manual/export
    if entry_type == 'offload':
        exit_code = str(entry.get('exit_code', 0))
    else:
        exit_code = '-'

    # Format size
    bytes_val = entry.get('bytes', 0)
    if bytes_val >= 1048576:
        size = f'{bytes_val // 1048576}M'
    elif bytes_val >= 1024:
        size = f'{bytes_val // 1024}K'
    else:
        size = f'{bytes_val}B'

    # Calculate age
    created_at = entry.get('created_at', '')
    try:
        ts = created_at.replace('Z', '+00:00')
        created = datetime.fromisoformat(ts)
        now = datetime.now(timezone.utc)
        diff = int((now - created).total_seconds())
        if diff < 60:
            age = f'{diff}s'
        elif diff < 3600:
            age = f'{diff // 60}m'
        elif diff < 86400:
            age = f'{diff // 3600}h'
        else:
            age = f'{diff // 86400}d'
    except:
        age = '?'

    # Check file exists
    path = entry.get('path', '')
    status = 'exists' if Path(path).exists() else 'cleaned'

    # Print row
    print(f' {num:2}  {id_str:8} {label:12} {exit_code:4} {size:7} {age:6} {status}')

    # For index: use cmd or title as label
    idx_label = entry.get('cmd') or entry.get('title') or entry_type
    index_lines.append(f'{num}:{id_str}:{idx_label}')

# Write index file
try:
    with open(index_path, 'w') as f:
        f.write('\\n'.join(index_lines))
except:
    pass
"

   # Create symlink or pointer to active index (Windows-safe)
   ln -sf "$index_path" "$pointer_path" 2>/dev/null || echo "$index_path" > "$pointer_path"

   echo ""
   echo "Use: /context-open 1  or  /context-open pytest  or  /context-open A1B2"
   ```

3. Show summary stats:
   ```bash
   echo ""
   echo "────────────────────────"
   count=$(find .fewword/scratch/tool_outputs -maxdepth 1 -type f -name "*_exit*.txt" 2>/dev/null | wc -l | tr -d ' ')
   size=$(du -sh .fewword/scratch/tool_outputs 2>/dev/null | cut -f1 || echo "0")
   echo "Total: $count files, $size"
   ```

## Usage Examples

- `/context-recent` - Show last 10 offloaded outputs with numbers
- `/context-open 1` - Open most recent output
- `/context-open pytest` - Open latest pytest output
- After compaction, use this to rediscover file pointers
