---
description: Initialize FewWord directory structure for a project
---

# Initialize FewWord Structure

Set up the FewWord directories for this project.

## Steps

1. Create the directory structure using Python (cross-platform):
   ```bash
   python3 -c "
from pathlib import Path
dirs = [
    '.fewword/scratch/tool_outputs',
    '.fewword/scratch/subagents',
    '.fewword/memory/plans',
    '.fewword/memory/history',
    '.fewword/memory/patterns',
    '.fewword/index'
]
for d in dirs:
    Path(d).mkdir(parents=True, exist_ok=True)
print('[fewword] Directories created')
" 2>/dev/null || python -c "
from pathlib import Path
dirs = [
    '.fewword/scratch/tool_outputs',
    '.fewword/scratch/subagents',
    '.fewword/memory/plans',
    '.fewword/memory/history',
    '.fewword/memory/patterns',
    '.fewword/index'
]
for d in dirs:
    Path(d).mkdir(parents=True, exist_ok=True)
print('[fewword] Directories created')
"
   ```

2. Add to .gitignore (if git repo):
   ```bash
   python3 -c "
from pathlib import Path
gitignore = Path('.gitignore')
if Path('.git').is_dir():
    content = gitignore.read_text() if gitignore.exists() else ''
    if '.fewword/scratch' not in content:
        with open(gitignore, 'a') as f:
            f.write('\n# FewWord plugin\n.fewword/scratch/\n.fewword/index/\n')
        print('Added .fewword/scratch/ and .fewword/index/ to .gitignore')
    else:
        print('.gitignore already configured')
" 2>/dev/null || python -c "
from pathlib import Path
gitignore = Path('.gitignore')
if Path('.git').is_dir():
    content = gitignore.read_text() if gitignore.exists() else ''
    if '.fewword/scratch' not in content:
        with open(gitignore, 'a') as f:
            f.write('\n# FewWord plugin\n.fewword/scratch/\n.fewword/index/\n')
        print('Added .fewword/scratch/ and .fewword/index/ to .gitignore')
    else:
        print('.gitignore already configured')
"
   ```

3. Create initial preferences file if user wants:
   ```yaml
   # .fewword/memory/preferences.yaml
   # Add your preferences here - Claude will learn from these
   formatting:
     # code_style: "include type hints"
     # response_length: "concise"
   domain:
     # tech_stack: "Python, FastAPI"
   ```

4. Confirm setup complete and explain usage:
   - `.fewword/scratch/` - Temporary files, auto-cleaned hourly
   - `.fewword/memory/` - Persistent learned context
   - `.fewword/index/` - Tool execution metadata and active plan
   - Bash outputs automatically offloaded when commands run
   - Plans persist across context summarization
   - Create `.fewword/DISABLE_OFFLOAD` to disable auto-offloading
