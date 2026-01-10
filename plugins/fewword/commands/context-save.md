---
description: "Manually save large content to FewWord scratch with pointer"
arguments:
  - name: title
    description: "Short title for the saved content (required)"
    required: true
  - name: --file
    description: "Read content from file path instead of stdin"
    required: false
  - name: --source
    description: "Source hint: subagent, paste, tool (default: manual)"
    required: false
---

# Context Save

Manually offload large content (subagent outputs, pasted text, etc.) to FewWord scratch storage without requiring hooks.

## Usage

```bash
# Pipe content from stdin
echo "Large output here..." | /context-save "Explore results"

# From a file
/context-save "Build log" --file /tmp/build.log

# With source hint
/context-save "API response" --source subagent --file response.json
```

## Output

Returns a compact pointer:
```
[fw a1b2c3d4] Explore results 15.2KB 210L | /context-open a1b2c3d4
```

## Implementation

```python
#!/usr/bin/env python3
"""Wrapper to run context_save from hooks/scripts."""

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

from context_save import main

main()
```

## Notes

- Content is read from stdin (pipe) or `--file` path
- No clipboard support (OS-specific complexity)
- Redaction applied before saving using same patterns as Bash offload
- Files use `.txt` extension for smart_cleanup compatibility
- No `exit_code` field - displays as `-` in outputs
- Title stored raw in manifest (JSON handles escaping), sanitized only for filename
