---
description: Pin an output to prevent auto-cleanup
---

# Context Pin

Pin an offloaded output to permanent storage. Pinned files are never auto-deleted.

## Usage

`/context-pin <id>` where `<id>` is the 8-character hex ID from `/context-recent` or the offload message.

## Steps

1. Parse the ID argument (user provides it after invoking this command)

2. Find the file in manifest:
   ```bash
   id="$1"  # The ID provided by user
   manifest=".fewword/index/tool_outputs.jsonl"

   if [ ! -f "$manifest" ]; then
     echo "Error: No manifest found. Nothing to pin."
     exit 1
   fi

   # Find the offload entry for this ID
   entry=$(grep "\"id\":\"$id\"" "$manifest" | grep '"type":"offload"' | tail -1)

   if [ -z "$entry" ]; then
     echo "Error: ID '$id' not found in manifest"
     echo "Use /context-recent to see available IDs"
     exit 1
   fi

   # Extract path from entry
   path=$(echo "$entry" | sed 's/.*"path":"\([^"]*\)".*/\1/')
   ```

3. Check if file exists:
   ```bash
   if [ ! -f "$path" ]; then
     echo "Error: File no longer exists (already cleaned up)"
     echo "Path was: $path"
     exit 1
   fi
   ```

4. Move to pinned storage:
   ```bash
   mkdir -p .fewword/memory/pinned
   filename=$(basename "$path")
   dest=".fewword/memory/pinned/$filename"

   mv "$path" "$dest"
   echo "Pinned: $path -> $dest"
   ```

5. Append pin event to manifest (append-only, not in-place update):
   ```bash
   now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
   printf '{"type":"pin","id":"%s","pinned_at":"%s","path":"%s"}\n' \
     "$id" "$now" "$dest" >> "$manifest"
   ```

6. Update LATEST alias if it pointed to this file:
   ```bash
   # Check if any LATEST symlink points to the moved file
   for latest in .fewword/scratch/tool_outputs/LATEST*.txt; do
     if [ -L "$latest" ]; then
       target=$(readlink "$latest")
       if [ "$(basename "$target")" = "$filename" ]; then
         # Update symlink to new location
         ln -sf "$(cd .fewword/memory/pinned && pwd)/$filename" "$latest"
         echo "Updated LATEST alias: $(basename "$latest")"
       fi
     fi
   done 2>/dev/null
   ```

7. Confirm:
   ```bash
   echo ""
   echo "File pinned successfully!"
   echo "Location: $dest"
   echo "This file will NOT be auto-deleted by cleanup."
   ```

## Notes

- Pinned files are stored in `.fewword/memory/pinned/`
- They survive TTL expiration and LRU eviction
- Use for important error logs, test outputs, or reference data
- To unpin: manually move file back to scratch or delete it
