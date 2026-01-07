---
description: Clean up scratch files and show context storage stats
---

# Context Cleanup

Analyze and clean the filesystem context storage.

## Steps

1. Show current storage usage:
   ```bash
   echo "=== FewWord Storage Stats ==="
   du -sh .fsctx/scratch/ .fsctx/memory/ .fsctx/index/ 2>/dev/null || echo "No .fsctx/ directory found"
   echo ""
   echo "=== Scratch Breakdown ==="
   du -sh .fsctx/scratch/*/ 2>/dev/null || echo "Empty"
   echo ""
   echo "=== File Counts ==="
   find .fsctx/scratch -type f 2>/dev/null | wc -l | xargs echo "Scratch files:"
   find .fsctx/memory -type f 2>/dev/null | wc -l | xargs echo "Memory files:"
   find .fsctx/index -type f 2>/dev/null | wc -l | xargs echo "Index files:"
   ```

2. Ask user what to clean:
   - **All scratch**: Remove everything in `.fsctx/scratch/`
   - **Old files only**: Remove files older than 1 hour
   - **Tool outputs only**: Clear `.fsctx/scratch/tool_outputs/`
   - **Nothing**: Just show stats

3. Execute cleanup based on choice:
   - All scratch: `rm -rf .fsctx/scratch/*`
   - Old files: `find .fsctx/scratch -type f -mmin +60 -delete`
   - Tool outputs: `rm -rf .fsctx/scratch/tool_outputs/*`

4. Show results after cleanup

**Note**: `index/` is never auto-cleaned - it contains the active plan and tool metadata.
