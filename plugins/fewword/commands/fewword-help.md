---
description: "Explain FewWord plugin, how it works, and available commands"
---

# FewWord Plugin Help

Please explain the following to the user:

## What is FewWord?

FewWord is a context engineering plugin for Claude Code that automatically offloads large command outputs to the filesystem, keeping your conversation context clean and efficient.

**The Problem:** When you run commands that produce large outputs (test suites, find, logs), those outputs sit in your context forever, eating tokens and eventually getting lost when context summarizes.

**The Solution:** FewWord uses tiered offloading with ultra-compact pointers (~35 tokens). Small outputs shown inline, medium outputs get a compact pointer, large failures get a tail preview.

## Does it work automatically?

**Yes!** After installation, FewWord works automatically with zero configuration:

1. Install: `claude plugin install fewword@sheeki03-Few-Word`
2. Start a new session
3. Run commands as normal - large outputs are automatically offloaded

**No configuration needed.** The plugin hooks into Claude Code's PreToolUse event and intercepts Bash commands automatically.

## How It Works (v1.3 Tiered Offloading)

| Output Size | What Happens |
|-------------|--------------|
| < 512B | Shown inline (normal behavior) |
| 512B - 4KB | Compact pointer only (~35 tokens) |
| > 4KB | Compact pointer + tail preview (failures only) |

**Compact pointer (~35 tokens):**
```
[fw A1B2C3D4] pytest e=0 45K 882L | /context-open A1B2C3D4
```

**With failure preview (exit != 0):**
```
[fw E5F6G7H8] pytest e=1 45K 234L | /context-open E5F6G7H8
FAILED test_auth.py::test_login - AssertionError
FAILED test_api.py::test_endpoint - TimeoutError
2 failed, 48 passed in 12.34s
```

## Available Commands

### /fewword-stats

Show session statistics and estimated token savings.

**Shows:**
- Outputs offloaded this session
- Total bytes and estimated tokens saved
- Breakdown by tier (inline, compact, preview)

### /context-open <id>

Retrieve an offloaded output by its ID.

**Usage:**
```
/context-open A1B2C3D4
```

The ID is shown in the compact pointer: `[fw A1B2C3D4]`

### /context-recent

Show recent offloaded outputs from the manifest. **Primary recovery path after context compaction.**

**Usage:**
```
/context-recent
```

Shows:
- Last 10 offloaded outputs with ID, command, exit code, size
- File status (exists or deleted)
- LATEST aliases
- Retrieval commands

### /context-pin <id>

Pin an output to prevent auto-cleanup. Pinned files are stored permanently.

**Usage:**
```
/context-pin A1B2C3D4
```

The ID comes from `/context-recent` or the compact pointer. Pinned files move to `.fewword/memory/pinned/`.

### /fewword-help

Show this help information (what you're reading now).

### /context-init

Set up FewWord directory structure manually (usually not needed - SessionStart does this automatically).

### /context-cleanup

View storage statistics and clean up old scratch files.

### /context-search <term>

Search through all offloaded context files.

---

## What Gets Offloaded

| Size | Action |
|------|--------|
| < 512B | Shown inline (not offloaded) |
| 512B - 4KB | Offloaded, compact pointer |
| > 4KB | Offloaded, pointer + preview (failures) |

**Not offloaded:**
- Interactive commands (vim, ssh, python, etc.)
- Commands with existing redirects (`>`, `2>`, `| tee`)
- Pipelines (`|`)
- Commands under 10 characters

## Smart Retention

FewWord uses intelligent cleanup based on command exit codes:
- **Exit 0 (success)**: Retained for 24 hours
- **Exit != 0 (failure)**: Retained for 48 hours (you might need error logs later!)
- **LRU eviction**: When scratch exceeds 250MB, oldest files are removed first
- **LATEST aliases**: Never auto-deleted, always point to most recent output
- Cleanup runs on SessionStart and after each offload

## Escape Hatch

If you need to disable FewWord temporarily:

```bash
# Option 1: Create disable file
touch .fewword/DISABLE_OFFLOAD

# Option 2: Environment variable
export FEWWORD_DISABLE=1
```

## Privacy

FewWord logs only metadata (tool names, timestamps), never your actual data:
- Command arguments: NOT logged (may contain secrets)
- Output content: Written to local disk only, never transmitted
- MCP tools: Only parameter keys logged, not values

## Directory Structure

```
.fewword/
├── scratch/           # Ephemeral (auto-cleaned by TTL + LRU)
│   ├── tool_outputs/  # Command outputs (24h/48h retention)
│   │   ├── LATEST.txt           # Symlink to most recent
│   │   └── LATEST_{cmd}.txt     # Per-command symlink
│   └── subagents/     # Agent workspaces
├── memory/            # Persistent (never auto-cleaned)
│   ├── plans/         # Archived plans
│   └── pinned/        # Pinned outputs (/context-pin)
└── index/             # Metadata
    └── tool_outputs.jsonl  # Append-only manifest
```

## Configuration Defaults (v1.3)

| Setting | Value |
|---------|-------|
| Inline threshold | 512B |
| Preview threshold | 4KB |
| Preview lines | 5 (tail only, failures) |
| Success retention (exit 0) | 24 hours |
| Failure retention (exit != 0) | 48 hours |
| Scratch max size | 250MB (LRU eviction) |

**Environment overrides:**
```bash
FEWWORD_INLINE_MAX=512              # Below this: inline
FEWWORD_PREVIEW_MIN=4096            # Above this: add preview
FEWWORD_OPEN_CMD=/context-open      # Command in pointer
FEWWORD_SHOW_PATH=1                 # Append path to pointer
FEWWORD_VERBOSE_POINTER=1           # Old verbose format
```

## Learn More

- GitHub: https://github.com/sheeki03/Few-Word
- Inspired by: [Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus), [LangChain](https://blog.langchain.com/how-agents-can-use-filesystems-for-context-engineering/)
