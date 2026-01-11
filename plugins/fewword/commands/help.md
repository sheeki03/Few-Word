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

## How It Works (v1.3.4 Tiered Offloading)

| Output Size | What Happens |
|-------------|--------------|
| < 512B | Shown inline (normal behavior) |
| 512B - 4KB | Compact pointer only (~35 tokens) |
| > 4KB | Compact pointer + tail preview (failures only) |

**Compact pointer (~35 tokens):**
```
[fw A1B2C3D4] pytest e=0 45K 882L | /open A1B2C3D4
```

**With failure preview (exit != 0):**
```
[fw E5F6G7H8] pytest e=1 45K 234L | /open E5F6G7H8
FAILED test_auth.py::test_login - AssertionError
FAILED test_api.py::test_endpoint - TimeoutError
2 failed, 48 passed in 12.34s
```

## Available Commands (v1.3.4)

### Retrieval Commands

| Command | Description |
|---------|-------------|
| `/open <id>` | Retrieve output by ID, number, or command name |
| `/recent` | Show recent outputs with numbered list |
| `/search <pattern>` | Search across all outputs (with hard caps) |
| `/diff <cmd>` | Compare two command outputs |

### Organization Commands

| Command | Description |
|---------|-------------|
| `/pin <id>` | Pin output to prevent cleanup |
| `/unpin <id>` | Unpin a pinned output |
| `/tag <id> <tags>` | Add tags to output |
| `/note <id> "note"` | Add notes to output |

### Analysis Commands

| Command | Description |
|---------|-------------|
| `/stats` | Token savings and session statistics |
| `/timeline` | Visual session history |
| `/correlate <id>` | Find related failures |

### System Commands

| Command | Description |
|---------|-------------|
| `/help` | This help information |
| `/onboarding` | Interactive tutorial |
| `/doctor` | System health check |
| `/config` | Show effective configuration |
| `/init` | Manual setup (usually automatic) |
| `/cleanup` | View storage and clean up |
| `/save <title>` | Manually save content to FewWord storage |
| `/export` | Export session history as markdown report |

---

## Command Details

### /open

Retrieve an offloaded output with multiple selector options.

```bash
/open A1B2             # By hex ID
/open 1                # By number from /recent
/open pytest           # Latest output from 'pytest'
/open --last           # Most recent output (any command)
/open --last pytest    # Most recent pytest output
/open --last-fail      # Most recent failed output
/open --nth 2 pytest   # 2nd most recent pytest output

# Output flags
/open A1B2 --full      # Full content
/open A1B2 --head 50   # First 50 lines
/open A1B2 --tail 50   # Last 50 lines
/open A1B2 --grep "pattern"  # Search within output
```

### /recent

Show recent offloaded outputs. **Primary recovery path after context compaction.**

```bash
/recent                # Last 10 outputs
/recent --all          # All outputs
/recent --pinned       # Pinned outputs only
/recent --tag <tag>    # Filter by tag
```

### /search

Search across all outputs with hard caps to prevent context explosion.

```bash
/search "AssertionError"
/search "error" --cmd pytest
/search "pattern" --since 24h
/search "FAILED" --pinned-only
/search "pattern" --full       # More results (still capped)
```

**Hard caps:** 50 files, 2MB/file, 50 lines output

### /diff

Compare two command outputs with noise stripping.

```bash
/diff pytest              # Diff last 2 pytest runs
/diff A1B2 --prev         # Diff A1B2 vs previous
/diff A1B2 C3D4           # Diff two specific outputs
/diff pytest --stat       # Summary only (default)
/diff pytest --full       # Full unified diff
```

### /stats

Show comprehensive statistics and token savings.

```bash
/stats                # Current session
/stats --json         # Machine-readable
/stats --all-time     # Across all sessions
```

### /timeline

Visual timeline of session activity.

```bash
/timeline             # Current session
/timeline --last 2h   # Last 2 hours
/timeline --cmd pytest
/timeline --failures
```

### /correlate

Find related failures through pattern matching.

```bash
/correlate A1B2       # Find related failures
/correlate --cluster  # Group failures by similarity
```

### /doctor

Self-diagnostics with optional repair.

```bash
/doctor               # Health check
/doctor --fix         # Attempt safe repairs
```

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
- Commands matching deny list

## Smart Retention

FewWord uses intelligent cleanup based on command exit codes:
- **Exit 0 (success)**: Retained for 24 hours
- **Exit != 0 (failure)**: Retained for 48 hours
- **LRU eviction**: When scratch exceeds 250MB
- **LATEST aliases**: Always point to most recent output
- **Pinned outputs**: Never auto-deleted

## Security Features (v1.3.4)

### Secret Redaction (ON by default)

Secrets are redacted BEFORE writing to disk:
- AWS keys (AKIA...)
- GitHub tokens (ghp_..., gho_...)
- Bearer tokens
- API keys
- Private keys
- Connection strings with passwords

### Do Not Store Mode

Configure commands that should never be stored:
```toml
# .fewwordrc.toml
[deny]
cmds = ["vault", "1password", "aws"]
patterns = ["--password", "--token"]
```

## Auto-Pin Rules (v1.3.4)

Automatically pin outputs based on rules:
```toml
[auto_pin]
on_fail = true                # Pin all failures
match = "FATAL|panic"         # Pin if matches pattern
cmds = ["pytest"]             # Pin specific commands
size_min = 102400             # Pin outputs > 100KB
max_files = 50                # Cap total auto-pinned
```

## Configuration (v1.3.4)

### Config Files

FewWord supports TOML (Python 3.11+) or JSON config files:
- **Repo config:** `.fewwordrc.toml` or `.fewwordrc.json`
- **User config:** `~/.fewwordrc.toml` or `~/.fewwordrc.json`

**Precedence (higher wins):**
1. Environment variables
2. Repo config
3. User config
4. Built-in defaults

### Example .fewwordrc.toml

```toml
[thresholds]
inline_max = 256
preview_min = 2048

[retention]
# P3 fix #24: Update to match documented defaults (24h/48h)
success_min = 1440   # 24 hours (default)
fail_min = 2880      # 48 hours (default)

[auto_pin]
on_fail = true
cmds = ["pytest", "cargo test"]

[redaction]
enabled = true
patterns = ["MY_SECRET_.*"]

[deny]
cmds = ["vault", "1password"]

[aliases]
pytest = ["py.test", "python -m pytest"]
npm = ["pnpm", "yarn", "bun"]
```

### Environment Variables

```bash
FEWWORD_INLINE_MAX=512
FEWWORD_PREVIEW_MIN=4096
FEWWORD_AUTO_PIN_FAIL=1
FEWWORD_DENY_CMDS=vault,1password
FEWWORD_REDACT_ENABLED=1
FEWWORD_DISABLE=1              # Disable all offloading
```

## Escape Hatch

If you need to disable FewWord temporarily:

```bash
# Option 1: Create disable file
touch .fewword/DISABLE_OFFLOAD

# Option 2: Environment variable
export FEWWORD_DISABLE=1
```

## Directory Structure

```
.fewword/
├── scratch/           # Ephemeral (auto-cleaned by TTL + LRU)
│   └── tool_outputs/  # Command outputs
├── memory/            # Persistent
│   ├── plans/         # Archived plans
│   └── pinned/        # Pinned outputs
└── index/             # Metadata
    ├── tool_outputs.jsonl    # Append-only manifest
    ├── session.json          # Current session info
    └── .recent_index         # Numbered lookup index
```

## Learn More

- Tutorial: `/onboarding`
- Health check: `/doctor`
- Current config: `/config`
- GitHub: https://github.com/sheeki03/Few-Word
