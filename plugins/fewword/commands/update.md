---
description: "Update FewWord plugin to latest version"
---

# FewWord Update

Update the FewWord plugin to the latest version from GitHub.

## Steps

1. Clear ALL caches and do a fresh install:
   ```bash
   # Remove all FewWord cache and marketplace data
   rm -rf ~/.claude/plugins/cache/sheeki03-Few-Word 2>/dev/null
   rm -rf ~/.claude/plugins/marketplaces/sheeki03-Few-Word 2>/dev/null
   rm -rf ~/.claude/plugins/fewword@sheeki03-Few-Word 2>/dev/null

   # Uninstall (ignore errors if not installed)
   claude plugin uninstall fewword@sheeki03-Few-Word 2>/dev/null

   # Fresh install from GitHub
   claude plugin install fewword@sheeki03-Few-Word
   ```

2. Verify the installed version:
   ```bash
   # Find and display installed version
   version=$(find ~/.claude/plugins -path "*fewword*" -name "plugin.json" -exec grep -l "fewword" {} \; 2>/dev/null | head -1 | xargs grep '"version"' 2>/dev/null | grep -o '[0-9]\+\.[0-9]\+\.[0-9]\+')
   if [ -n "$version" ]; then
     echo "✓ FewWord v${version} installed successfully"
   else
     echo "✓ FewWord installed (restart session to verify version)"
   fi
   ```

3. Inform the user:
   ```
   Update complete! Please restart your Claude Code session for the new version to take effect.
   ```

## Notes

- This command removes ALL cached data and does a fresh install from GitHub
- Always restart your session after updating for hooks to reload
- Check current version anytime with `/fewword:version`
- The standard `claude plugin update` command has caching issues - always use `/fewword:update` instead
