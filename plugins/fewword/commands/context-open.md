---
description: "Open/retrieve an offloaded output by ID"
---

# Context Open

Retrieve the contents of an offloaded output by its ID.

## Usage

The user will provide an ID after invoking this command, e.g., `/context-open A1B2C3D4`

## Steps

1. Get the ID from the user's command (the argument after `/context-open`)

2. Look up the ID in the manifest:
   ```bash
   id="$1"  # The ID provided by user
   manifest=".fewword/index/tool_outputs.jsonl"

   if [ ! -f "$manifest" ]; then
     echo "Error: No manifest found. Run a command first to create offloaded outputs."
     exit 1
   fi

   # Find the offload entry for this ID (case insensitive)
   entry=$(grep -i "\"id\":\"$id\"" "$manifest" | grep '"type":"offload"' | tail -1)

   if [ -z "$entry" ]; then
     echo "Error: ID '$id' not found in manifest"
     echo "Use /context-recent to see available IDs"
     exit 1
   fi
   ```

3. Extract path and check if file exists:
   ```bash
   # Extract path from entry
   path=$(echo "$entry" | sed 's/.*"path":"\([^"]*\)".*/\1/')

   if [ -f "$path" ]; then
     # File exists - show contents
     echo "=== Contents of $id ==="
     cat "$path"
   else
     # File was cleaned up
     echo "File has been cleaned up."
     echo "Was at: $path"
     echo ""
     echo "The file may have been deleted by:"
     echo "  - TTL expiration (24h for success, 48h for failures)"
     echo "  - LRU eviction (scratch > 250MB)"
     echo ""
     echo "Use /context-pin <id> next time to preserve important outputs."
   fi
   ```

## Notes

- IDs are 8-character hex strings shown in the compact pointer: `[fw A1B2C3D4]`
- IDs are case-insensitive
- If the file was cleaned up, the command explains why and suggests `/context-pin`
- This is the primary retrieval method - simpler than remembering file paths
