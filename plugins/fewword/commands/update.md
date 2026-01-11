---
description: "Update FewWord plugin to latest version"
---

# FewWord Update

Update the FewWord plugin to the latest version from GitHub.

## Steps

1. Clear the marketplace cache and reinstall to ensure latest version:
   ```bash
   rm -rf ~/.claude/plugins/marketplaces/sheeki03-Few-Word && claude plugin uninstall fewword@sheeki03-Few-Word 2>/dev/null; claude plugin install fewword@sheeki03-Few-Word
   ```

2. Inform the user:
   ```
   Update complete. Please restart your Claude Code session for changes to take effect.
   ```

## Notes

- This command clears the cached marketplace data and reinstalls fresh from GitHub
- The standard `claude plugin update` command may show "already at latest" due to stale cache
- After updating, start a new session for hooks to reload
- Check current version with `/fewword:version`
