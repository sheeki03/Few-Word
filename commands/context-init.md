---
description: Initialize FewWord directory structure for a project
---

# Initialize FewWord Structure

Set up the FewWord directories for this project.

## Steps

1. Create the directory structure:
   ```bash
   mkdir -p .fewword/{scratch/{tool_outputs,subagents},memory/{plans,history,patterns},index}
   echo "[fewword] Directories created"
   ```

2. Add to .gitignore (if git repo):
   ```bash
   if [ -d .git ]; then
     if ! grep -q ".fewword/scratch" .gitignore 2>/dev/null; then
       echo -e "\n# FewWord plugin\n.fewword/scratch/\n.fewword/index/" >> .gitignore
       echo "Added .fewword/scratch/ and .fewword/index/ to .gitignore"
     else
       echo ".gitignore already configured"
     fi
   fi
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
