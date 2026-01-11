---
description: "Interactive tutorial for new FewWord users"
---

# FewWord Onboarding

Welcome tutorial that introduces FewWord concepts and common workflows.

## Usage

```bash
/onboarding              # Full tutorial
/onboarding --quick      # Quick start (essentials only)
/onboarding --examples   # Show example workflows
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
   /recent

3. Retrieve when needed:
   /open 1              # By number
   /open A1B2           # By ID
   /open pytest         # By command name
   /open --last-fail    # Last failure

That's it! FewWord works automatically in the background.

More: /help | /stats | /onboarding
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
[fw A1B2] pytest e=1 45K 882L | /open A1B2

# Get just the errors
/open A1B2 --grep "FAILED\|Error"

# Compare with last passing run
/diff pytest

─── Tracking Important Outputs ───

# Pin output to prevent cleanup
/pin A1B2

# Add tags for organization
/tag A1B2 prod-bug hotfix

# Add notes for context
/note A1B2 "Root cause: race condition in auth"

# Find tagged outputs later
/recent --tag prod-bug

─── Searching History ───

# Search across all outputs
/search "connection refused"

# Search specific command outputs
/search "AssertionError" --cmd pytest

# Find outputs from last 24h
/search "error" --since 24h

─── Session Analysis ───

# See token savings
/stats

# Visual timeline
/timeline

# Check system health
/doctor

─── Quick Access Shortcuts ───

/open --last              # Most recent output
/open --last pytest       # Most recent pytest
/open --last-fail         # Most recent failure
/open --nth 2 pytest      # 2nd most recent pytest
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

  [fw A1B2] pytest e=1 45K 882L | /open A1B2

══════════════════════════════════════════════════════════════════
  BASIC USAGE
══════════════════════════════════════════════════════════════════

1. RUN A COMMAND
   Just run commands normally. FewWord works in the background.

   $ pytest tests/
   $ npm install
   $ cargo build

2. SEE WHAT'S SAVED
   /recent

   Shows numbered list of recent outputs:
    # │ ID       │ Cmd    │ Exit │ Size │ Age
   ───┼──────────┼────────┼──────┼──────┼────
    1 │ A1B2C3D4 │ pytest │ 1    │ 45K  │ 2m
    2 │ C3D4E5F6 │ npm    │ 0    │ 12K  │ 5m

3. RETRIEVE WHEN NEEDED
   /open 1          # By number from list
   /open A1B2       # By hex ID
   /open pytest     # By command name (latest)
   /open --last     # Most recent (any command)

══════════════════════════════════════════════════════════════════
  KEY COMMANDS
══════════════════════════════════════════════════════════════════

  RETRIEVAL
  ─────────
  /open <selector>     Open output by ID/number/cmd
  /open --last-fail    Last failed output
  /open ID --grep X    Search within output

  DISCOVERY
  ─────────
  /recent              List recent outputs
  /search "pattern"    Search across all outputs
  /timeline            Visual session history

  ORGANIZATION
  ────────────
  /pin <ID>            Pin to prevent cleanup
  /tag <ID> <tag>      Add tags for organization
  /note <ID> "note"    Add notes for context

  ANALYSIS
  ────────
  /diff pytest         Diff last 2 runs
  /correlate <ID>      Find related failures
  /stats               Token savings stats

  SYSTEM
  ──────
  /help                Full command reference
  /config              Show current config
  /doctor              System health check

══════════════════════════════════════════════════════════════════
  PRO TIPS
══════════════════════════════════════════════════════════════════

  • Outputs auto-cleanup: 24h for success, 48h for failures
  • Use /pin for important outputs you want to keep
  • Secrets are automatically redacted before saving
  • Configure per-project with .fewwordrc.toml

══════════════════════════════════════════════════════════════════
  NEXT STEPS
══════════════════════════════════════════════════════════════════

  1. Run a command and see FewWord in action
  2. Try /recent to see saved outputs
  3. Use /open to retrieve when needed

  Quick reference: /help
  See examples: /onboarding --examples
  Check health: /doctor

Happy coding!
TUTORIAL
```

## Notes

- First-time users are auto-prompted to run `/onboarding --quick`
- `--examples` shows practical workflow recipes
- Full tutorial is comprehensive but readable (~80 lines)
- ASCII art banner makes screenshots shareable
