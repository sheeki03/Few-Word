---
description: Clean up scratch files and show context storage stats
---

# Context Cleanup

Analyze and clean FewWord storage.

## Steps

1. Show current storage usage:
   ```bash
   echo "=== FewWord Storage Stats ==="
   du -sh .fewword/scratch/ .fewword/memory/ .fewword/index/ 2>/dev/null || echo "No .fewword/ directory found"
   echo ""
   echo "=== Scratch Breakdown ==="
   du -sh .fewword/scratch/*/ 2>/dev/null || echo "Empty"
   echo ""
   echo "=== File Counts ==="
   find .fewword/scratch -type f 2>/dev/null | wc -l | xargs echo "Scratch files:"
   find .fewword/memory -type f 2>/dev/null | wc -l | xargs echo "Memory files:"
   find .fewword/index -type f 2>/dev/null | wc -l | xargs echo "Index files:"
   ```

2. Ask user what to clean:
   - **All scratch**: Remove everything in `.fewword/scratch/`
   - **Old files only**: Remove files older than 1 hour
   - **Tool outputs only**: Clear `.fewword/scratch/tool_outputs/`
   - **Nothing**: Just show stats

3. Execute cleanup based on choice:
   - All scratch: `rm -rf .fewword/scratch/*`
   - Old files: `find .fewword/scratch -type f -mmin +60 -delete`
   - Tool outputs: `rm -rf .fewword/scratch/tool_outputs/*`

4. Show results after cleanup

**Note**: `index/` is never auto-cleaned - it contains the active plan and tool metadata.
