---
description: Pin an output to prevent auto-cleanup
---

# Context Pin

Pin an offloaded output to permanent storage. Pinned files are never auto-deleted.

## Usage

`/pin <id>` where `<id>` is the 8-character hex ID from `/recent` or the offload message.

## Steps

1. Parse the ID argument (user provides it after invoking this command)

2. Validate and find the file in manifest:
   ```bash
   id="$1"  # The ID provided by user
   manifest=".fewword/index/tool_outputs.jsonl"

   # Validate ID is 8-character hex (prevents grep injection)
   if ! echo "$id" | grep -qE '^[0-9A-Fa-f]{8}$'; then
     echo "Error: Invalid ID format. Expected 8-character hex (e.g., A1B2C3D4)"
     exit 1
   fi

   if [ ! -f "$manifest" ]; then
     echo "Error: No manifest found. Nothing to pin."
     exit 1
   fi

   # Find the offload entry for this ID (fixed-string match)
   entry=$(grep -iF "\"id\":\"$id\"" "$manifest" | grep '"type":"offload"' | tail -1)

   if [ -z "$entry" ]; then
     echo "Error: ID '$id' not found in manifest"
     echo "Use /recent to see available IDs"
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

   if ! mv "$path" "$dest"; then
     echo "Error: Failed to move file to pinned storage"
     exit 1
   fi
   echo "Pinned: $path -> $dest"
   ```

5. Append pin event to manifest (append-only, not in-place update):
   ```bash
   now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
   printf '{"type":"pin","id":"%s","pinned_at":"%s","path":"%s"}\n' \
     "$id" "$now" "$dest" >> "$manifest"
   ```

6. Update LATEST alias if it pointed to this file (cross-platform):
   ```bash
   # Update any LATEST alias that points to the moved file
   # Works with both symlinks (Unix) and pointer files (Windows fallback)
   python3 -c "
from pathlib import Path
import os

filename = '$filename'
pinned_path = Path('.fewword/memory/pinned') / filename
pinned_abs = str(pinned_path.resolve())

for latest in Path('.fewword/scratch/tool_outputs').glob('LATEST*.txt'):
    try:
        # Check if it's a symlink
        if latest.is_symlink():
            target = os.readlink(latest)
            if Path(target).name == filename:
                latest.unlink()
                latest.symlink_to(pinned_abs)
                print(f'Updated LATEST alias: {latest.name}')
        # Check if it's a pointer file (Windows fallback)
        elif latest.is_file():
            content = latest.read_text().strip()
            if Path(content).name == filename:
                latest.write_text(pinned_abs)
                print(f'Updated LATEST alias: {latest.name}')
    except (OSError, IOError):
        pass
" 2>/dev/null
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
