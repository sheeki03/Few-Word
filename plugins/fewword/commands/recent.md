---
description: Show recent offloaded outputs from scratch
---

# Context Recent

Show recent offloaded outputs with numbered list for easy reference. Primary recovery path after context compaction.

## Output Format

```
Recent Offloaded Outputs
────────────────────────
 #  ID       CMD      EXIT   SIZE    AGE     STATUS
 1) A1B2     pytest   1      45K     2h      exists
 2) C3D4     npm      0      12K     3h      exists
 3) E5F6     ls       0      900B    4h      cleaned

Use: /open 1  or  /open pytest  or  /open A1B2
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
   printf " %-3s %-8s %-12s %-4s %-7s %-6s %s\n" "#" "ID" "CMD" "EXIT" "SIZE" "AGE" "STATUS"

   # Prepare index file (session-scoped)
   index_path=".fewword/index/.recent_index_${session_id:-default}"
   pointer_path=".fewword/index/.recent_index"

   # Clear/create index file
   > "$index_path"

   # Read last 10 offload entries
   num=0
   tail -30 "$manifest" | grep '"type":"offload"' | tail -10 | while IFS= read -r line; do
     num=$((num + 1))

     # Extract fields
     id=$(echo "$line" | sed 's/.*"id":"\([^"]*\)".*/\1/')
     cmd=$(echo "$line" | sed 's/.*"cmd":"\([^"]*\)".*/\1/')
     exit_code=$(echo "$line" | sed 's/.*"exit_code":\([0-9-]*\).*/\1/')
     bytes=$(echo "$line" | sed 's/.*"bytes":\([0-9]*\).*/\1/')
     path=$(echo "$line" | sed 's/.*"path":"\([^"]*\)".*/\1/')
     created_at=$(echo "$line" | sed 's/.*"created_at":"\([^"]*\)".*/\1/')

     # Format size
     if [ "$bytes" -ge 1048576 ]; then
       size="$((bytes / 1048576))M"
     elif [ "$bytes" -ge 1024 ]; then
       size="$((bytes / 1024))K"
     else
       size="${bytes}B"
     fi

     # Calculate age using Python helper
     age=$(python "$helper" age "$created_at" 2>/dev/null || echo "?")

     # Check if file still exists
     if [ -f "$path" ]; then
       status="exists"
     else
       status="cleaned"
     fi

     # Print row
     printf " %-3s %-8s %-12s %-4s %-7s %-6s %s\n" "${num})" "${id:0:8}" "${cmd:0:12}" "$exit_code" "$size" "$age" "$status"

     # Write to index file for /open resolution
     echo "${num}:${id}:${cmd}" >> "$index_path"
   done

   # Create symlink or pointer to active index (Windows-safe)
   ln -sf "$index_path" "$pointer_path" 2>/dev/null || echo "$index_path" > "$pointer_path"

   echo ""
   echo "Use: /open 1  or  /open pytest  or  /open A1B2"
   ```

3. Show summary stats (cross-platform):
   ```bash
   echo ""
   echo "────────────────────────"
   # Cross-platform stats using Python (works on Windows, macOS, Linux)
   python -c "
import os
from pathlib import Path
d = Path('.fewword/scratch/tool_outputs')
if d.exists():
    files = list(d.glob('*_exit*.txt'))
    count = len(files)
    total_bytes = sum(f.stat().st_size for f in files if f.is_file())
    if total_bytes >= 1048576:
        size = f'{total_bytes // 1048576}M'
    elif total_bytes >= 1024:
        size = f'{total_bytes // 1024}K'
    else:
        size = f'{total_bytes}B'
    print(f'Total: {count} files, {size}')
else:
    print('Total: 0 files, 0B')
" 2>/dev/null || echo "Total: ? files"
   ```

## Usage Examples

- `/recent` - Show last 10 offloaded outputs with numbers
- `/open 1` - Open most recent output
- `/open pytest` - Open latest pytest output
- After compaction, use this to rediscover file pointers
