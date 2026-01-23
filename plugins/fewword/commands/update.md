---
description: "Update FewWord plugin to latest version"
---

# FewWord Update

Update the FewWord plugin to the latest version from GitHub.

## Steps

1. Clear ALL caches and do a fresh install using Python (cross-platform):
   ```bash
   python3 -c "
import shutil
from pathlib import Path
home = Path.home()
cache_dirs = [
    home / '.claude/plugins/cache/sheeki03-Few-Word',
    home / '.claude/plugins/marketplaces/sheeki03-Few-Word',
    home / '.claude/plugins/fewword@sheeki03-Few-Word'
]
for d in cache_dirs:
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
        print(f'Removed: {d}')
print('Cache cleared')
" 2>/dev/null || python -c "
import shutil
from pathlib import Path
home = Path.home()
cache_dirs = [
    home / '.claude/plugins/cache/sheeki03-Few-Word',
    home / '.claude/plugins/marketplaces/sheeki03-Few-Word',
    home / '.claude/plugins/fewword@sheeki03-Few-Word'
]
for d in cache_dirs:
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
        print(f'Removed: {d}')
print('Cache cleared')
"
   ```

2. Uninstall and reinstall:
   ```bash
   claude plugin uninstall fewword@sheeki03-Few-Word 2>/dev/null
   claude plugin install fewword@sheeki03-Few-Word
   ```

3. Verify the installed version using Python (cross-platform):
   ```bash
   python3 -c "
import json
from pathlib import Path
home = Path.home()
patterns = [
    home / '.claude/plugins/marketplaces/sheeki03-Few-Word/plugins/fewword/.claude-plugin/plugin.json',
    home / '.claude/plugins/fewword@sheeki03-Few-Word/plugins/fewword/.claude-plugin/plugin.json'
]
for p in patterns:
    if p.exists():
        data = json.loads(p.read_text())
        print(f\"✓ FewWord v{data.get('version', 'unknown')} installed successfully\")
        break
else:
    print('✓ FewWord installed (restart session to verify version)')
" 2>/dev/null || python -c "
import json
from pathlib import Path
home = Path.home()
patterns = [
    home / '.claude/plugins/marketplaces/sheeki03-Few-Word/plugins/fewword/.claude-plugin/plugin.json',
    home / '.claude/plugins/fewword@sheeki03-Few-Word/plugins/fewword/.claude-plugin/plugin.json'
]
for p in patterns:
    if p.exists():
        data = json.loads(p.read_text())
        print(f\"✓ FewWord v{data.get('version', 'unknown')} installed successfully\")
        break
else:
    print('✓ FewWord installed (restart session to verify version)')
"
   ```

4. Inform the user:
   ```
   Update complete! Please restart your Claude Code session for the new version to take effect.
   ```

## Notes

- This command removes ALL cached data and does a fresh install from GitHub
- Always restart your session after updating for hooks to reload
- Check current version anytime with `/fewword:version`
- The standard `claude plugin update` command has caching issues - always use `/fewword:update` instead
