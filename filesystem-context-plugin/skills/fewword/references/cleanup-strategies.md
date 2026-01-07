# Cleanup Strategies

Managing scratch file lifecycle to prevent unbounded growth.

## Automatic Cleanup Rules

### By Age

```bash
# Delete tool outputs older than 1 hour
find .fsctx/scratch/tool_outputs -type f -mmin +60 -delete

# Delete subagent files older than 2 hours
find .fsctx/scratch/subagents -type f -mmin +120 -delete

# Note: index/ is NEVER auto-cleaned (contains active plan)
```

### By Size

```bash
# Delete files larger than 10MB (likely logs that got out of hand)
find .fsctx/scratch -type f -size +10M -delete

# Alert on scratch dir size
du -sh .fsctx/scratch/
```

### By Pattern

```bash
# Clean all temp files
find .fsctx/scratch -name "*.tmp" -delete
find .fsctx/scratch -name "*_temp_*" -delete

# Clean empty directories
find .fsctx/scratch -type d -empty -delete
```

## Retention Policies

| Directory | Retention | Rationale |
|-----------|-----------|-----------|
| `.fsctx/scratch/tool_outputs/` | 1 hour | Ephemeral, task-specific |
| `.fsctx/scratch/subagents/` | 2 hours | Task-specific coordination |
| `.fsctx/index/` | **Never** | Contains active plan + metadata |
| `.fsctx/memory/history/` | 7 days | May need to reference |
| `.fsctx/memory/plans/` | Permanent | Archived completed plans |
| `.fsctx/memory/preferences.yaml` | Permanent | Learned user preferences |

## Hook Integration

The plugin includes hooks that automatically:

1. **On session start**: Clean files older than retention policy
2. **On session end**: Archive completed plans to `memory/plans/`
3. **On each response**: Warn if `.fsctx/scratch/` exceeds 100MB

## Manual Cleanup Commands

```bash
# Full scratch reset
rm -rf .fsctx/scratch/*

# Preserve structure, clear contents
find .fsctx/scratch -type f -delete

# Selective cleanup
rm -rf .fsctx/scratch/tool_outputs/*
rm -rf .fsctx/scratch/subagents/*

# Use the cleanup script
python skills/fewword/scripts/cleanup_scratch.py --stats
python skills/fewword/scripts/cleanup_scratch.py --all --dry-run
python skills/fewword/scripts/cleanup_scratch.py --all
```

## Best Practices

1. **Use timestamps in filenames** - Enables age-based cleanup
2. **Separate scratch from memory** - `.fsctx/scratch/` vs `.fsctx/memory/`
3. **Don't store originals in scratch** - Only derived/generated content
4. **Include cleanup in task completion** - Part of "done" checklist
5. **Never manually delete index/** - Contains active plan that survives sessions
