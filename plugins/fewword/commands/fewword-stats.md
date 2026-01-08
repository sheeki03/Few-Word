---
description: "Show FewWord session statistics and token savings"
---

# FewWord Stats

Show statistics about offloaded outputs for the current session, including estimated token savings.

## Steps

1. Read session ID and manifest:
   ```bash
   session_file=".fewword/index/session.json"
   manifest=".fewword/index/tool_outputs.jsonl"

   if [ ! -f "$session_file" ]; then
     echo "No active session found."
     echo "Session tracking starts on next SessionStart."
     exit 0
   fi

   session_id=$(cat "$session_file" | grep -o '"session_id":"[^"]*"' | cut -d'"' -f4)
   started_at=$(cat "$session_file" | grep -o '"started_at":"[^"]*"' | cut -d'"' -f4)

   echo "=== FewWord Session Stats ==="
   echo "Session: $session_id"
   echo "Started: $started_at"
   echo ""
   ```

2. Calculate stats from manifest (filter by current session):
   ```bash
   if [ ! -f "$manifest" ]; then
     echo "No outputs recorded yet."
     exit 0
   fi

   # Filter manifest by session_id and count
   session_entries=$(grep "\"session_id\":\"$session_id\"" "$manifest" | grep '"type":"offload"')

   if [ -z "$session_entries" ]; then
     echo "No outputs offloaded this session."
     echo ""
     echo "Outputs < 512B are shown inline (no savings needed)."
     echo "Run commands with larger outputs to see savings."
     exit 0
   fi

   # Count outputs
   count=$(echo "$session_entries" | wc -l | tr -d ' ')

   # Sum bytes
   total_bytes=$(echo "$session_entries" | grep -o '"bytes":[0-9]*' | cut -d':' -f2 | awk '{sum+=$1} END {print sum}')

   # Estimate tokens saved (1 token ≈ 4 bytes, minus ~35 tokens per pointer)
   tokens_inline=$((total_bytes / 4))
   pointer_cost=$((count * 35))
   tokens_saved=$((tokens_inline - pointer_cost))

   # Format bytes
   if [ "$total_bytes" -ge 1048576 ]; then
     size_str="$((total_bytes / 1048576)).$((total_bytes % 1048576 / 104858))MB"
   elif [ "$total_bytes" -ge 1024 ]; then
     size_str="$((total_bytes / 1024))KB"
   else
     size_str="${total_bytes}B"
   fi

   echo "Outputs offloaded: $count"
   echo "Total bytes: $size_str"
   echo "Estimated tokens saved: ~${tokens_saved}"
   echo ""
   ```

3. Show tier breakdown:
   ```bash
   # Count by tier (based on bytes)
   # Tier 1: < 512B (inline, not in manifest)
   # Tier 2: 512B - 4KB (compact pointer)
   # Tier 3: > 4KB (preview)

   tier2=$(echo "$session_entries" | awk -F'"bytes":' '{print $2}' | cut -d',' -f1 | awk '$1 >= 512 && $1 < 4096' | wc -l | tr -d ' ')
   tier3=$(echo "$session_entries" | awk -F'"bytes":' '{print $2}' | cut -d',' -f1 | awk '$1 >= 4096' | wc -l | tr -d ' ')

   tier2_bytes=$(echo "$session_entries" | awk -F'"bytes":' '{print $2}' | cut -d',' -f1 | awk '$1 >= 512 && $1 < 4096 {sum+=$1} END {print sum+0}')
   tier3_bytes=$(echo "$session_entries" | awk -F'"bytes":' '{print $2}' | cut -d',' -f1 | awk '$1 >= 4096 {sum+=$1} END {print sum+0}')

   tier2_saved=$(( (tier2_bytes / 4) - (tier2 * 35) ))
   tier3_saved=$(( (tier3_bytes / 4) - (tier3 * 35) ))

   echo "By tier:"
   echo "  Inline (<512B):     (shown in context, not tracked)"
   echo "  Compact (512B-4KB): $tier2 outputs → saved ~${tier2_saved} tokens"
   echo "  Preview (>4KB):     $tier3 outputs → saved ~${tier3_saved} tokens"
   echo ""
   echo "Recent outputs: /context-recent"
   ```

## Notes

- Stats are per-session (reset on each SessionStart)
- Token estimates assume 1 token ≈ 4 bytes and ~35 tokens per compact pointer
- Inline outputs (<512B) are not tracked since they're shown in full
- Use `/context-recent` to see individual outputs
