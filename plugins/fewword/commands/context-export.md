---
description: "Export session history as markdown report"
arguments:
  - name: --all-time
    description: "Export all sessions, not just current"
    required: false
  - name: --output
    description: "Output file path (default: auto-generated)"
    required: false
---

# Context Export

Export session history as a markdown report, saved to FewWord storage with a pointer for retrieval.

## Usage

```bash
/context-export                     # Export current session
/context-export --all-time          # Export all sessions
/context-export --output report.txt # Custom output path
```

## Output

Returns a compact pointer to the exported report:
```
[fw a1b2c3d4] Session export 2026-01-10 12.5KB 245L | /context-open a1b2c3d4
```

## Implementation

```python
#!/usr/bin/env python3
"""Wrapper to run context_export from hooks/scripts."""

import os
import sys
from pathlib import Path

# Add hooks/scripts to path
_cwd = os.environ.get('FEWWORD_CWD', os.getcwd())
for candidate in [
    Path(_cwd) / 'hooks' / 'scripts',
    Path(_cwd) / 'plugins' / 'fewword' / 'hooks' / 'scripts',
    Path(__file__).parent.parent / 'hooks' / 'scripts' if '__file__' in dir() else None,
]:
    if candidate and candidate.exists():
        sys.path.insert(0, str(candidate))
        break

from context_export import main

main()
```

## Notes

- Exports are stored as `.txt` for smart_cleanup compatibility
- Redaction is applied to previews, titles, tags, and notes
