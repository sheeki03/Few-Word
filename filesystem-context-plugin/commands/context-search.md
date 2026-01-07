---
description: Search through offloaded context files (tool outputs, plans, history)
arguments:
  - name: search_term
    description: The search term or pattern to find
    required: true
---

# Search Offloaded Context

Find and retrieve information from filesystem context storage.

## Arguments

This command requires a search term: `/context-search <search_term>`

Example: `/context-search authentication error`

## Steps

1. Validate the search term argument was provided:
   - If `$ARGUMENTS.search_term` is empty, ask user: "What would you like to search for?"
   - Otherwise proceed with the search

2. Search across context storage:
   ```bash
   SEARCH_TERM="$ARGUMENTS.search_term"
   echo "=== Searching for: $SEARCH_TERM ==="
   echo ""
   echo "=== Scratch files (ephemeral) ==="
   grep -rn --include="*.txt" --include="*.md" --include="*.yaml" "$SEARCH_TERM" .fsctx/scratch/ 2>/dev/null | head -20

   echo ""
   echo "=== Memory files (persistent) ==="
   grep -rn --include="*.txt" --include="*.md" --include="*.yaml" "$SEARCH_TERM" .fsctx/memory/ 2>/dev/null | head -20

   echo ""
   echo "=== Index files (metadata) ==="
   grep -n "$SEARCH_TERM" .fsctx/index/*.jsonl 2>/dev/null | head -10
   ```

3. If matches found, offer to:
   - Show more context around a match: `grep -B 3 -A 3 'term' <file>`
   - Read the full file
   - Show file metadata (size, age)

4. If no matches, suggest:
   - Try different search terms
   - List available files with `ls -la .fsctx/scratch/ .fsctx/memory/`
   - Check if context was already cleaned up
