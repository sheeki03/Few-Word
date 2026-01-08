---
description: Show recent offloaded outputs from scratch
---

# Context Recent

Show recent offloaded outputs with their status. Primary recovery path after context compaction.

## Steps

1. Check if manifest exists and read it:
   ```bash
   if [ -f ".fewword/index/tool_outputs.jsonl" ]; then
     echo "=== Recent Offloaded Outputs ==="
     echo ""
     # Show last 10 entries (reverse order, newest first)
     tail -20 .fewword/index/tool_outputs.jsonl | grep '"type":"offload"' | tail -10 | while IFS= read -r line; do
       id=$(echo "$line" | sed 's/.*"id":"\([^"]*\)".*/\1/')
       cmd=$(echo "$line" | sed 's/.*"cmd":"\([^"]*\)".*/\1/')
       exit_code=$(echo "$line" | sed 's/.*"exit_code":\([0-9-]*\).*/\1/')
       bytes=$(echo "$line" | sed 's/.*"bytes":\([0-9]*\).*/\1/')
       path=$(echo "$line" | sed 's/.*"path":"\([^"]*\)".*/\1/')

       # Check if file still exists
       if [ -f "$path" ]; then
         status="exists"
       else
         status="DELETED"
       fi

       echo "[$id] $cmd exit=$exit_code ${bytes}B - $status"
       echo "    $path"
     done
   else
     echo "No manifest found. Run a command that produces large output first."
   fi
   ```

2. Show LATEST aliases if they exist:
   ```bash
   echo ""
   echo "=== LATEST Aliases ==="
   for f in .fewword/scratch/tool_outputs/LATEST*.txt; do
     if [ -L "$f" ]; then
       target=$(readlink "$f")
       echo "$(basename "$f") -> $(basename "$target")"
     elif [ -f "$f" ]; then
       echo "$(basename "$f") (pointer file)"
     fi
   done 2>/dev/null || echo "No LATEST aliases"
   ```

3. Show summary stats:
   ```bash
   echo ""
   echo "=== Summary ==="
   count=$(find .fewword/scratch/tool_outputs -maxdepth 1 -type f -name "*_exit*.txt" 2>/dev/null | wc -l | tr -d ' ')
   size=$(du -sh .fewword/scratch/tool_outputs 2>/dev/null | cut -f1 || echo "0")
   echo "Files: $count, Size: $size"
   echo ""
   echo "Retrieval: cat <path> | Read the full output"
   echo "Pin: /context-pin <id> | Prevent auto-cleanup"
   ```

## Usage Examples

- `/context-recent` - Show last 10 offloaded outputs
- After compaction, use this to rediscover file pointers
- Use the ID with `/context-pin` to preserve important outputs
