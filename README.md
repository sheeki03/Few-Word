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
│   │  📁 Write to Disk   │      │  📋 Return to Context   │      │
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

**Result**: 45KB output → ~200 tokens in context + full data on disk when needed.

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

**The 82% savings (21.3k tokens) is specifically on Message tokens** — that's where your actual conversation and command outputs live. The other categories (system prompt, tools) are constant overhead that exists regardless of what you do.

**Why this matters:**
- Message tokens are what fills up as you work
- Without FewWord: 3 commands = 26k tokens of outputs sitting in context forever
- With FewWord: Same 3 commands = 4.7k tokens (pointers + previews only)
- Full outputs saved to `.fewword/scratch/` for retrieval when needed

---

## The Problem

AI coding agents hit a wall when:
- **Tool outputs bloat your context** — One big test run or log dump eats 10k tokens that sit there forever
- **Plans get lost** — After context summarization, Claude forgets what it was doing
- **You're paying for waste** — Most of your context is irrelevant to the current step

## The Solution

FewWord implements **dynamic context discovery** — patterns from [Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) and [LangChain](https://blog.langchain.com/how-agents-can-use-filesystems-for-context-engineering/) that use the filesystem as infinite, searchable memory.

**Instead of this:**
```
[26,000 tokens of command outputs sitting in context forever]
```

**You get this:**
```
=== [FewWord: Output offloaded] ===
File: .fewword/scratch/tool_outputs/find_143022_a1b2c3d4.txt
Size: 15534 bytes, 882 lines
Exit: 0

=== First 10 lines ===
/usr/bin/uux
/usr/bin/cpan
...

=== Last 10 lines ===
/usr/bin/gunzip
...

=== Retrieval commands ===
  Full: cat .fewword/scratch/tool_outputs/find_143022_a1b2c3d4.txt
  Grep: grep 'pattern' .fewword/scratch/tool_outputs/find_143022_a1b2c3d4.txt
```

---

## What It Does

### Automatic Behaviors

| Feature | What Happens |
|---------|--------------|
| **Bash Output Offloading** | Large outputs (>8KB) → written to file, pointer + preview returned. Small outputs → shown normally. |
| **Plan Persistence** | Active plan in `.fewword/index/current_plan.yaml`, auto-archived on completion |
| **Auto-cleanup** | Old scratch files deleted on session start (>60min for outputs, >120min for subagents) |

### Hook Events

| Event | Action |
|-------|--------|
| **SessionStart** | Creates directories, cleans stale files, updates .gitignore |
| **PreToolUse** | Intercepts Bash commands, wraps large outputs |
| **SessionEnd** | Archives completed plans |
| **Stop** | Warns if scratch storage exceeds 100MB |

### Manual Commands

| Command | What It Does |
|---------|--------------|
| `/context-init` | Set up FewWord directory structure |
| `/context-cleanup` | See storage stats, clean old files |
| `/context-search <term>` | Search through all offloaded context |

---

## Installation

```bash
claude plugin install fewword@sheeki03-Few-Word
```

**Important**: Start a new session after installation for hooks to load.

---

## Directory Structure

```
your-project/
└── .fewword/
    ├── scratch/                     # Ephemeral (auto-cleaned)
    │   ├── tool_outputs/            # Command outputs (cleaned >60min)
    │   └── subagents/               # Agent workspaces (cleaned >120min)
    ├── memory/                      # Persistent
    │   ├── plans/                   # Archived completed plans
    │   └── history/                 # Archived sessions
    ├── index/                       # Metadata (never auto-cleaned)
    │   └── current_plan.yaml        # Active plan
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

### Defaults (v1)

| Setting | Value |
|---------|-------|
| Size threshold | 8KB (~2000 tokens) |
| Preview lines | 10 (first + last) |
| Tool output retention | 60 minutes |
| Subagent retention | 120 minutes |
| Scratch size warning | 100MB |

---

## Example: Before & After

### Before (Traditional)
```
You: Run the full test suite
Claude: [15,000 tokens of test output in context]
You: Now fix the auth bug
Claude: [still carrying 15,000 tokens of test output]
You: What tests are failing?
Claude: [context summarized, test details lost]
```

### After (With FewWord)
```
You: Run the full test suite
Claude: [Output offloaded to .fewword/scratch/tool_outputs/pytest_143022.txt]
        Size: 45678 bytes, Exit: 1
        === Last 10 lines ===
        FAILED auth_test.py::test_login - AssertionError
You: Now fix the auth bug
Claude: [working with clean context]
You: What tests are failing?
Claude: grep FAILED .fewword/scratch/tool_outputs/pytest_143022.txt
        → FAILED auth_test.py::test_login - expected 200, got 401
```

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
  "input_keys": ["query", "repo", "limit"],  // Keys only, NOT values
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