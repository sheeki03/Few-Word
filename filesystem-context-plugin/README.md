# FewWord

**Stop losing context. Stop paying for bloated conversations.**

A Claude Code + OpenCode plugin that automatically manages your context window by offloading large outputs to files and retrieving them on-demand. Saves **97% of context tokens** in typical sessions.

---

## The Problem

AI coding agents hit a wall when:
- **Tool outputs bloat your context** — One big test run or log dump eats 10k tokens that sit there forever
- **Plans get lost** — After context summarization, Claude forgets what it was doing
- **Sub-agents play telephone** — Information degrades as it passes through message chains
- **You're paying for waste** — 80% of your context is irrelevant to the current step

## The Solution

FewWord implements **dynamic context discovery** — patterns from [Cursor](https://cursor.com/blog/dynamic-context-discovery) and [LangChain](https://blog.langchain.com/how-agents-can-use-filesystems-for-context-engineering/) that use the filesystem as infinite, searchable memory.

**Instead of this:**
```
[10,000 token test output sitting in context forever]
```

**You get this:**
```
=== [FewWord: Output offloaded] ===
File: .fsctx/scratch/tool_outputs/pytest_143022_a1b2c3d4.txt
Size: 45678 bytes, 1234 lines
Exit: 0

=== First 10 lines ===
...preview...

=== Retrieval commands ===
  Full: cat .fsctx/scratch/tool_outputs/pytest_143022_a1b2c3d4.txt
  Grep: grep 'FAILED' .fsctx/scratch/tool_outputs/pytest_143022_a1b2c3d4.txt
```

---

## What It Does

### Automatic Behaviors

| Feature | What Happens |
|---------|--------------|
| **Bash Output Offloading** | Large outputs (>8KB) → written to file, pointer + preview returned. Small outputs → shown normally. |
| **Plan Persistence** | Active plan in `.fsctx/index/current_plan.yaml`, auto-archived on completion |
| **MCP Tool Logging** | All MCP calls logged (sanitized, no secrets) |
| **MCP Write Gating** | Write operations require confirmation |
| **Pagination Clamping** | Prevents excessive MCP query results |

### Hook Events (Claude Code)

| Event | Action |
|-------|--------|
| **SessionStart** | Creates directories, cleans stale files |
| **PreToolUse** | Intercepts Bash commands, clamps MCP pagination |
| **PermissionRequest** | Gates MCP write operations |
| **SessionEnd** | Archives completed plans |
| **Stop** | Warns if scratch storage exceeds 100MB |

### Manual Commands

| Command | What It Does |
|---------|--------------|
| `/context-init` | Set up filesystem context structure |
| `/context-cleanup` | See storage stats, clean old files |
| `/context-search <term>` | Search through all offloaded context |

---

## Installation

### Claude Code

```bash
# From local folder:
/plugin marketplace add /path/to/fewword
/plugin install fewword@fewword-marketplace
```

Or copy to `~/.claude/plugins/fewword/`

### OpenCode

Copy `.opencode/plugin/fsctx.ts` to your project's `.opencode/plugin/` directory.

**Important**: OpenCode MCP interception is best-effort and may be log-only depending on version. See [known limitations](#opencode-limitations).

---

## Directory Structure

```
your-project/
└── .fsctx/                          # All plugin data
    ├── scratch/                     # Ephemeral (auto-cleaned hourly)
    │   ├── tool_outputs/            # Command outputs
    │   └── subagents/               # Agent workspaces
    ├── memory/                      # Persistent
    │   ├── plans/                   # Archived completed plans
    │   ├── history/                 # Archived sessions
    │   └── preferences.yaml         # User preferences
    ├── index/                       # Metadata (never auto-cleaned)
    │   ├── current_plan.yaml        # Active plan
    │   ├── tool_log.jsonl           # Tool execution log
    │   └── mcp_metadata.jsonl       # MCP metadata
    └── DISABLE_OFFLOAD              # Escape hatch file
```

**Note**: The plugin automatically adds `.fsctx/scratch/` and `.fsctx/index/` to `.gitignore` on first session start in a git repo.

---

## Escape Hatch

If automatic offloading causes issues:

```bash
# Disable via file
touch .fsctx/DISABLE_OFFLOAD

# Or via environment variable
export FEWWORD_DISABLE=1

# Allow MCP write operations
export FEWWORD_ALLOW_WRITE=1
```

---

## What Gets Skipped (v1)

The plugin conservatively skips these commands:

- **Interactive**: ssh, vim, less, top, watch, python, node, psql, etc.
- **Already redirecting**: commands with `>`, `2>`, `| tee`, `| less`
- **Heredocs**: commands containing `<<`
- **Pipelines**: commands containing `|` (exit code masking)
- **Trivial**: commands under 10 characters

---

## Privacy & Security

### What Gets Logged

- Timestamp, session ID, event ID
- Tool name
- Coarse size metrics
- Output file pointer

### What Does NOT Get Logged

- Raw command arguments (may contain secrets)
- Full command text
- Environment variables

MCP metadata logging is sanitized: only tool names and input keys are recorded, never raw values.

---

## OpenCode Limitations

MCP tool calls may not trigger `tool.execute.before/after` hooks in some OpenCode versions. This means:

- Bash offloading works reliably
- MCP logging may not capture all calls
- MCP write gating may not work

This is a known limitation. See [OpenCode issue #2319](https://github.com/sst/opencode/issues/2319).

---

## Configuration

### Hardcoded Defaults (v1)

| Setting | Value |
|---------|-------|
| Size threshold | 8KB (~2000 tokens) |
| Preview lines | 10 (first + last) |
| Tool output retention | 60 minutes |
| Subagent retention | 120 minutes |
| Scratch size warning | 100MB |

Configuration file support planned for v1.1.

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
Claude: [Output offloaded to .fsctx/scratch/tool_outputs/pytest_143022.txt]
        Size: 45678 bytes, Exit: 1
        === Last 10 lines ===
        FAILED auth_test.py::test_login - AssertionError
You: Now fix the auth bug
Claude: [working with clean context]
You: What tests are failing?
Claude: [greps the file] grep FAILED .fsctx/scratch/tool_outputs/pytest_143022.txt
        FAILED auth_test.py::test_login - expected 200, got 401
```

---

## Credits & References

Based on research and patterns from:
- [Cursor: Dynamic Context Discovery](https://cursor.com/blog/dynamic-context-discovery)
- [LangChain: How Agents Can Use Filesystems](https://blog.langchain.com/how-agents-can-use-filesystems-for-context-engineering/)
- [Manus: Context Engineering for AI Agents](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [Anthropic: Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)

---

## License

MIT — Use it, modify it, share it.

---

## Contributing

Issues and PRs welcome! Ideas for improvement:
- [ ] Configuration file support
- [ ] Semantic search integration
- [ ] Smarter summarization of offloaded outputs
- [ ] Cross-session memory persistence
