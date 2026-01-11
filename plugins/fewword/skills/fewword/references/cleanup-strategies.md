# Cleanup Strategies

Managing scratch file lifecycle to prevent unbounded growth.

> **Windows Note**: The `find` and `du` commands shown below are Unix/Linux commands. On Windows, use Python equivalents or Git Bash. The `/cleanup` command uses cross-platform Python internally.

## Automatic Cleanup Rules

### By Age

```bash
# Delete tool outputs older than 1 hour
find .fewword/scratch/tool_outputs -type f -mmin +60 -delete

# Delete subagent files older than 2 hours
find .fewword/scratch/subagents -type f -mmin +120 -delete

# Note: index/ is NEVER auto-cleaned (contains active plan)
```

### By Size

```bash
# Delete files larger than 10MB (likely logs that got out of hand)
find .fewword/scratch -type f -size +10M -delete

# Alert on scratch dir size
du -sh .fewword/scratch/
```

### By Pattern

```bash
# Clean all temp files
find .fewword/scratch -name "*.tmp" -delete
find .fewword/scratch -name "*_temp_*" -delete

# Clean empty directories
find .fewword/scratch -type d -empty -delete
```

## Retention Policies

| Directory | Retention | Rationale |
|-----------|-----------|-----------|
| `.fewword/scratch/tool_outputs/` | 1 hour | Ephemeral, task-specific |
| `.fewword/scratch/subagents/` | 2 hours | Task-specific coordination |
| `.fewword/index/` | **Never** | Contains active plan + metadata |
| `.fewword/memory/history/` | 7 days | May need to reference |
| `.fewword/memory/plans/` | Permanent | Archived completed plans |
| `.fewword/memory/preferences.yaml` | Permanent | Learned user preferences |

## Hook Integration

The plugin includes hooks that automatically:

1. **On session start**: Clean files older than retention policy
2. **On session end**: Archive completed plans to `memory/plans/`
3. **On each response**: Warn if `.fewword/scratch/` exceeds 100MB

## Manual Cleanup Commands

```bash
# Full scratch reset
rm -rf .fewword/scratch/*

# Preserve structure, clear contents
find .fewword/scratch -type f -delete

# Selective cleanup
rm -rf .fewword/scratch/tool_outputs/*
rm -rf .fewword/scratch/subagents/*

# Use the cleanup script
python skills/fewword/scripts/cleanup_scratch.py --stats
python skills/fewword/scripts/cleanup_scratch.py --all --dry-run
python skills/fewword/scripts/cleanup_scratch.py --all
```

## Best Practices

1. **Use timestamps in filenames** - Enables age-based cleanup
2. **Separate scratch from memory** - `.fewword/scratch/` vs `.fewword/memory/`
3. **Don't store originals in scratch** - Only derived/generated content
4. **Include cleanup in task completion** - Part of "done" checklist
5. **Never manually delete index/** - Contains active plan that survives sessions
