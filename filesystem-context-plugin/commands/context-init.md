---
description: Initialize filesystem context structure for a project
---

# Initialize Context Structure

Set up the filesystem context directories for this project.

## Steps

1. Create the directory structure:
   ```bash
   mkdir -p .fsctx/{scratch/{tool_outputs,subagents},memory/{plans,history,patterns},index}
   echo "[fsctx] Directories created"
   ```

2. Add to .gitignore (if git repo):
   ```bash
   if [ -d .git ]; then
     if ! grep -q ".fsctx/scratch" .gitignore 2>/dev/null; then
       echo -e "\n# Filesystem context plugin\n.fsctx/scratch/\n.fsctx/index/" >> .gitignore
       echo "Added .fsctx/scratch/ and .fsctx/index/ to .gitignore"
     else
       echo ".gitignore already configured"
     fi
   fi
   ```

3. Create initial preferences file if user wants:
   ```yaml
   # .fsctx/memory/preferences.yaml
   # Add your preferences here - Claude will learn from these
   formatting:
     # code_style: "include type hints"
     # response_length: "concise"
   domain:
     # tech_stack: "Python, FastAPI"
   ```

4. Confirm setup complete and explain usage:
   - `.fsctx/scratch/` - Temporary files, auto-cleaned hourly
   - `.fsctx/memory/` - Persistent learned context
   - `.fsctx/index/` - Tool execution metadata and active plan
   - Bash outputs automatically offloaded when commands run
   - Plans persist across context summarization
   - Create `.fsctx/DISABLE_OFFLOAD` to disable auto-offloading
