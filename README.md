<p align="center">
  <img src="banner.png" alt="Kevin Malone - Why waste time say lot word when few word do trick?" width="600">
</p>

# FewWord

> "Why waste time say lot word when few word do trick? Big output go file. Small word stay. Context happy. Me happy. Everyone go home by seven."
>
> — Kevin Malone

A Claude Code plugin that automatically offloads large command outputs to files, keeping your context clean and retrievable.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-Plugin-blueviolet)](https://claude.ai/claude-code)

---

## The Problem

AI coding agents hit a wall when:
- **Tool outputs bloat your context** — One big test run or log dump eats 10k tokens that sit there forever
- **Plans get lost** — After context summarization, Claude forgets what it was doing
- **You're paying for waste** — Most of your context is irrelevant to the current step

---

## The Solution

FewWord implements **dynamic context discovery** — patterns from [Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) and [LangChain](https://blog.langchain.com/how-agents-can-use-filesystems-for-context-engineering/) that use the filesystem as infinite, searchable memory.

**Instead of this:**
```
[26,000 tokens of command outputs sitting in context forever]
```

**You get this (~35 tokens):**
```
[fw A1B2C3D4] find e=0 15K 882L | /context-open A1B2C3D4
```

For failures, you also get a preview:
```
[fw E5F6G7H8] pytest e=1 45K 234L | /context-open E5F6G7H8
FAILED test_auth.py::test_login - AssertionError
FAILED test_api.py::test_endpoint - TimeoutError
2 failed, 48 passed in 12.34s
```

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                        Claude Code Session                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   You: "Run the test suite"                                     │
│                              │                                   │
│                              ▼                                   │
│   ┌──────────────────────────────────────────┐                  │
│   │  PreToolUse Hook Intercepts              │                  │
│   │  ─────────────────────────               │                  │
│   │  Command: pytest                         │                  │
│   │  Output: 45,678 bytes (>8KB threshold)   │                  │
│   └──────────────────────────────────────────┘                  │
│                              │                                   │
│              ┌───────────────┴───────────────┐                  │
│              ▼                               ▼                   │
│   ┌─────────────────────┐      ┌─────────────────────────┐      │
│   │  Write to Disk      │      │  Return to Context      │      │
│   │  ─────────────────  │      │  ────────────────────   │      │
│   │  .fewword/scratch/  │      │  File: pytest_143022.txt│      │
│   │  tool_outputs/      │      │  Size: 45KB, Exit: 1    │      │
│   │  pytest_143022.txt  │      │  === Last 10 lines ===  │      │
│   │                     │      │  FAILED auth_test...    │      │
│   │  [Full 45KB output] │      │  [~200 tokens only]     │      │
│   └─────────────────────┘      └─────────────────────────┘      │
│                                                                  │
│   Later: "What tests failed?"                                   │
│                              │                                   │
│                              ▼                                   │
│   Claude: grep FAILED .fewword/scratch/tool_outputs/pytest.txt  │
│           → Retrieves exactly what's needed                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Result**: 45KB output → ~35 tokens in context + full data on disk when needed.

---

## Test Results

We ran the same 3 commands (`find`, `ls -la`, `env`) in two fresh Claude Code sessions:

| Metric | WITH Plugin | WITHOUT Plugin |
|--------|-------------|----------------|
| **Message Tokens** | **4.7k** | 26.0k |
| **Tokens Saved** | **21.3k** | — |
| **Savings** | **82%** | — |

### Understanding the Numbers

When you run `/context`, you see several categories:

```
Total Context: 84k tokens (with plugin) vs 105k tokens (without)
├── System prompt:  3.8k  (constant - Claude's instructions)
├── System tools:  15.8k  (constant - built-in tools)
├── MCP tools:     14.7k  (constant - browser automation, etc.)
├── Messages:       4.7k  ← THIS IS WHAT FEWWORD REDUCES (was 26k)
└── Free space:      ...
```

**The 82% savings (21.3k tokens) is specifically on Message tokens** — that's where your actual conversation and command outputs live.

---

## Installation

```bash
claude plugin install fewword@sheeki03-Few-Word
```

**Important**: Start a new session after installation for hooks to load.

**That's it!** FewWord works automatically — no configuration needed.

---

## Commands

| Command | What It Does |
|---------|--------------|
| `/fewword-help` | Show detailed help and how the plugin works |
| `/fewword-stats` | Show session statistics and estimated token savings |
| `/context-open <id>` | Retrieve an offloaded output by ID |
| `/context-recent` | Show recent offloaded outputs (recovery after compaction) |
| `/context-pin <id>` | Pin an output to prevent auto-cleanup |
| `/context-init` | Set up FewWord directory structure |
| `/context-cleanup` | See storage stats, clean old files |
| `/context-search <term>` | Search through all offloaded context |

---

## What It Does

### Automatic Behaviors

| Feature | What Happens |
|---------|--------------|
| **Tiered Offloading** | < 512B: inline. 512B-4KB: compact pointer (~35 tokens). > 4KB: pointer + preview (failures only). |
| **Smart Retention** | Exit 0 (success) → 24h retention. Exit != 0 (failure) → 48h retention. LRU eviction at 250MB. |
| **LATEST Aliases** | `LATEST.txt` and `LATEST_{cmd}.txt` symlinks for quick retrieval |
| **Session Tracking** | Per-session stats for `/fewword-stats` |
| **Plan Persistence** | Active plan in `.fewword/index/current_plan.yaml`, auto-archived on completion |

### Hook Events

| Event | Action |
|-------|--------|
| **SessionStart** | Creates directories, runs smart cleanup (TTL + LRU), shows inventory, updates .gitignore |
| **PreToolUse** | Intercepts Bash commands, wraps large outputs, writes manifest, creates LATEST aliases |
| **SessionEnd** | Archives completed plans |
| **Stop** | Warns if scratch storage exceeds 100MB |

---

## Directory Structure

```
your-project/
└── .fewword/
    ├── scratch/                     # Ephemeral (auto-cleaned by TTL + LRU)
    │   ├── tool_outputs/            # Command outputs (24h success, 48h failure)
    │   │   ├── LATEST.txt           # Symlink to most recent output
    │   │   ├── LATEST_{cmd}.txt     # Symlink to most recent per command
    │   │   └── {cmd}_{ts}_{id}_exit{code}.txt
    │   └── subagents/               # Agent workspaces
    ├── memory/                      # Persistent (never auto-cleaned)
    │   ├── plans/                   # Archived completed plans
    │   ├── pinned/                  # Pinned outputs (via /context-pin)
    │   └── history/                 # Archived sessions
    ├── index/                       # Metadata
    │   ├── session.json             # Current session ID
    │   ├── current_plan.yaml        # Active plan
    │   └── tool_outputs.jsonl       # Append-only manifest
    └── DISABLE_OFFLOAD              # Escape hatch file
```

**Note**: The plugin automatically adds `.fewword/scratch/` and `.fewword/index/` to `.gitignore`.

---

## Escape Hatch

If automatic offloading causes issues:

```bash
# Disable via file
touch .fewword/DISABLE_OFFLOAD

# Or via environment variable
export FEWWORD_DISABLE=1
```

---

## What Gets Skipped

The plugin conservatively skips these commands:

- **Interactive**: ssh, vim, less, top, python, node, psql, etc.
- **Already redirecting**: commands with `>`, `2>`, `| tee`
- **Heredocs**: commands containing `<<`
- **Pipelines**: commands containing `|` (v1 limitation)
- **Trivial**: commands under 10 characters

---

## Configuration

### Defaults (v1.3)

| Setting | Value |
|---------|-------|
| Inline threshold | 512B (outputs below this shown inline) |
| Preview threshold | 4KB (outputs above this get tail preview on failure) |
| Preview lines | 5 (tail only, for failures) |
| Success retention (exit 0) | 24 hours |
| Failure retention (exit != 0) | 48 hours |
| Scratch max size | 250MB (LRU eviction) |

### Environment Variable Overrides

```bash
# Tiered offloading thresholds
FEWWORD_INLINE_MAX=512              # Below this: show inline
FEWWORD_PREVIEW_MIN=4096            # Above this: add preview (failures only)
FEWWORD_PREVIEW_LINES=5             # Max preview lines

# Pointer customization
FEWWORD_OPEN_CMD=/context-open      # Command shown in pointer
FEWWORD_SHOW_PATH=1                 # Append file path to pointer
FEWWORD_VERBOSE_POINTER=1           # Use old verbose format (v2.0 style)

# Retention settings
FEWWORD_RETENTION_SUCCESS_MIN=1440  # 24h default
FEWWORD_RETENTION_FAIL_MIN=2880     # 48h default
FEWWORD_SCRATCH_MAX_MB=250          # LRU cap
```

> **Note:** Longer retention keeps command outputs on disk longer. If you work with sensitive data, consider lowering TTLs via environment variables or adding `.fewword/scratch/` to your backup exclusions.

---

## Privacy & Security

### Bash Commands

| Logged | NOT Logged |
|--------|------------|
| Timestamp, session ID | Raw command arguments (may contain secrets) |
| Tool name (e.g., "find", "pytest") | Full command text |
| Output file path | Environment variables |

### MCP Tools (Browser automation, GitHub, etc.)

FewWord intercepts MCP tool calls (`mcp__*`) for two purposes:

| What We Do | What We DON'T Do |
|------------|------------------|
| Log tool name (e.g., `mcp__github__create_issue`) | Log argument values (may contain tokens, secrets) |
| Log input parameter keys (e.g., `["repo", "title"]`) | Store or transmit your data anywhere |
| Clamp pagination (limit requests to 100 results max) | Block read-only operations |

**Example metadata entry:**
```json
{
  "timestamp": "2026-01-08T14:30:00",
  "tool": "mcp__github__search_issues",
  "input_keys": ["query", "repo", "limit"],
  "input_count": 3
}
```

Your actual query strings, repo names, and other sensitive values are **never logged**.

---

## License

MIT — Use it, modify it, share it.

---

## Contributing

Issues and PRs welcome! Ideas for improvement:
- [ ] Opencode Support
