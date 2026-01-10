---
description: "Show installed FewWord version"
---

# FewWord Version

Display the currently installed FewWord plugin version.

## Steps

1. Read and display version from plugin.json:
   ```bash
   plugin_json="${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json"

   if [ -f "$plugin_json" ]; then
     version=$(grep -o '"version"[[:space:]]*:[[:space:]]*"[^"]*"' "$plugin_json" | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
     echo "FewWord version: $version"
   else
     echo "Error: Could not find plugin.json"
     exit 1
   fi
   ```

2. Show update command:
   ```bash
   echo ""
   echo "To check for updates:"
   echo "  claude plugin update fewword@sheeki03-Few-Word"
   echo ""
   echo "GitHub: https://github.com/sheeki03/Few-Word"
   ```

## Notes

- Version follows semantic versioning (major.minor.patch)
- Update checks run on SessionStart (rate-limited to once every 24 hours)
- Set `FEWWORD_DISABLE_UPDATE_CHECK=1` to disable auto-check
- Set `FEWWORD_DISABLE_UPDATE_NOTIFY=1` to disable notifications
