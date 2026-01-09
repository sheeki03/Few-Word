---
description: "Interactive tutorial for new FewWord users"
---

# FewWord Onboarding

Welcome tutorial that introduces FewWord concepts and common workflows.

## Usage

```bash
/fewword-onboarding              # Full tutorial
/fewword-onboarding --quick      # Quick start (essentials only)
/fewword-onboarding --examples   # Show example workflows
```

## Implementation

Display this tutorial content:

```bash
args="$@"

if [[ "$args" == *"--quick"* ]]; then
  cat << 'QUICK'
┌──────────────────────────────────────────────────────────────────┐
│                   FewWord Quick Start                            │
└──────────────────────────────────────────────────────────────────┘

FewWord automatically saves large command outputs to disk, showing
you compact pointers instead. This keeps your context window clean.

ESSENTIALS:

1. Run any command:
   $ pytest tests/

2. See offloaded outputs:
   /context-recent

3. Retrieve when needed:
   /context-open 1              # By number
   /context-open A1B2           # By ID
   /context-open pytest         # By command name
   /context-open --last-fail    # Last failure

That's it! FewWord works automatically in the background.

More: /fewword-help | /fewword-stats | /fewword-onboarding
QUICK
  exit 0
fi

if [[ "$args" == *"--examples"* ]]; then
  cat << 'EXAMPLES'
┌──────────────────────────────────────────────────────────────────┐
│                   FewWord Example Workflows                      │
└──────────────────────────────────────────────────────────────────┘

─── Debugging Test Failures ───

# Run tests
$ pytest tests/

# See the pointer
[fw A1B2] pytest e=1 45K 882L | /context-open A1B2

# Get just the errors
/context-open A1B2 --grep "FAILED\|Error"

# Compare with last passing run
/context-diff pytest

─── Tracking Important Outputs ───

# Pin output to prevent cleanup
/context-pin A1B2

# Add tags for organization
/context-tag A1B2 prod-bug hotfix

# Add notes for context
/context-note A1B2 "Root cause: race condition in auth"

# Find tagged outputs later
/context-recent --tag prod-bug

─── Searching History ───

# Search across all outputs
/context-search "connection refused"

# Search specific command outputs
/context-search "AssertionError" --cmd pytest

# Find outputs from last 24h
/context-search "error" --since 24h

─── Session Analysis ───

# See token savings
/fewword-stats

# Visual timeline
/context-timeline

# Check system health
/fewword-doctor

─── Quick Access Shortcuts ───

/context-open --last              # Most recent output
/context-open --last pytest       # Most recent pytest
/context-open --last-fail         # Most recent failure
/context-open --nth 2 pytest      # 2nd most recent pytest
EXAMPLES
  exit 0
fi

# Full tutorial
cat << 'TUTORIAL'
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   ███████╗███████╗██╗    ██╗██╗    ██╗ ██████╗ ██████╗ ██████╗   │
│   ██╔════╝██╔════╝██║    ██║██║    ██║██╔═══██╗██╔══██╗██╔══██╗  │
│   █████╗  █████╗  ██║ █╗ ██║██║ █╗ ██║██║   ██║██████╔╝██║  ██║  │
│   ██╔══╝  ██╔══╝  ██║███╗██║██║███╗██║██║   ██║██╔══██╗██║  ██║  │
│   ██║     ███████╗╚███╔███╔╝╚███╔███╔╝╚██████╔╝██║  ██║██████╔╝  │
│   ╚═╝     ╚══════╝ ╚══╝╚══╝  ╚══╝╚══╝  ╚═════╝ ╚═╝  ╚═╝╚═════╝   │
│                                                                  │
│              Context Engineering for Claude Code                  │
└──────────────────────────────────────────────────────────────────┘

Welcome to FewWord! This tutorial will show you how FewWord
helps you work more efficiently with Claude Code.

══════════════════════════════════════════════════════════════════
  THE PROBLEM
══════════════════════════════════════════════════════════════════

When you run commands like `pytest` or `npm install`, they often
produce hundreds or thousands of lines of output. This output:

  • Uses up your context window (tokens are precious!)
  • Makes it hard to find important information
  • Gets lost as the conversation continues

══════════════════════════════════════════════════════════════════
  THE SOLUTION
══════════════════════════════════════════════════════════════════

FewWord automatically intercepts command output and:

  1. Small outputs (<512B) → Shows inline (no change)
  2. Medium outputs (512B-4KB) → Shows compact pointer
  3. Large outputs (>4KB) → Shows pointer + preview (on failure)

Instead of 500+ tokens of pytest output, you see ~35 tokens:

  [fw A1B2] pytest e=1 45K 882L | /context-open A1B2

══════════════════════════════════════════════════════════════════
  BASIC USAGE
══════════════════════════════════════════════════════════════════

1. RUN A COMMAND
   Just run commands normally. FewWord works in the background.

   $ pytest tests/
   $ npm install
   $ cargo build

2. SEE WHAT'S SAVED
   /context-recent

   Shows numbered list of recent outputs:
    # │ ID       │ Cmd    │ Exit │ Size │ Age
   ───┼──────────┼────────┼──────┼──────┼────
    1 │ A1B2C3D4 │ pytest │ 1    │ 45K  │ 2m
    2 │ C3D4E5F6 │ npm    │ 0    │ 12K  │ 5m

3. RETRIEVE WHEN NEEDED
   /context-open 1          # By number from list
   /context-open A1B2       # By hex ID
   /context-open pytest     # By command name (latest)
   /context-open --last     # Most recent (any command)

══════════════════════════════════════════════════════════════════
  KEY COMMANDS
══════════════════════════════════════════════════════════════════

  RETRIEVAL
  ─────────
  /context-open <selector>     Open output by ID/number/cmd
  /context-open --last-fail    Last failed output
  /context-open ID --grep X    Search within output

  DISCOVERY
  ─────────
  /context-recent              List recent outputs
  /context-search "pattern"    Search across all outputs
  /context-timeline            Visual session history

  ORGANIZATION
  ────────────
  /context-pin <ID>            Pin to prevent cleanup
  /context-tag <ID> <tag>      Add tags for organization
  /context-note <ID> "note"    Add notes for context

  ANALYSIS
  ────────
  /context-diff pytest         Diff last 2 runs
  /context-correlate <ID>      Find related failures
  /fewword-stats               Token savings stats

  SYSTEM
  ──────
  /fewword-help                Full command reference
  /fewword-config              Show current config
  /fewword-doctor              System health check

══════════════════════════════════════════════════════════════════
  PRO TIPS
══════════════════════════════════════════════════════════════════

  • Outputs auto-cleanup: 24h for success, 48h for failures
  • Use /context-pin for important outputs you want to keep
  • Secrets are automatically redacted before saving
  • Configure per-project with .fewwordrc.toml

══════════════════════════════════════════════════════════════════
  NEXT STEPS
══════════════════════════════════════════════════════════════════

  1. Run a command and see FewWord in action
  2. Try /context-recent to see saved outputs
  3. Use /context-open to retrieve when needed

  Quick reference: /fewword-help
  See examples: /fewword-onboarding --examples
  Check health: /fewword-doctor

Happy coding!
TUTORIAL
```

## Notes

- First-time users are auto-prompted to run `/fewword-onboarding --quick`
- `--examples` shows practical workflow recipes
- Full tutorial is comprehensive but readable (~80 lines)
- ASCII art banner makes screenshots shareable
