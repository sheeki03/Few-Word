---
description: "Open/retrieve an offloaded output by ID or shortcut"
arguments:
  - name: selector
    description: "ID (hex), number from /context-recent, command name, or use --last flags"
    required: false
---

# Context Open

Retrieve offloaded output with a "peek" preview by default. Only dumps full content when explicitly requested.

## Usage

```
/context-open A1B2              # By hex ID
/context-open 1                 # By number from /context-recent
/context-open pytest            # Latest output from 'pytest' command

# NEW: Shortcut flags (v1.3.3)
/context-open --last            # Most recent output (any command)
/context-open --last pytest     # Most recent pytest output
/context-open --last-fail       # Most recent failed output (exit != 0)
/context-open --last-fail pytest  # Most recent failed pytest
/context-open --nth 2 pytest    # 2nd most recent pytest output

Output flags:
  --full                        # Print entire file
  --head 50                     # Print first 50 lines
  --tail 50                     # Print last 50 lines
  --grep "pattern"              # Search for pattern (max 50 lines)
  --grep-i "pattern"            # Case-insensitive search
```

## Default Output (Peek)

```
───────────────────────────────────────
[fw A1B2] pytest e=1 45K 882L (2h ago)
───────────────────────────────────────
HEAD:
  ============================= test session starts =============================
  platform darwin -- Python 3.11.0, pytest-7.4.0
  collected 42 items
TAIL:
  FAILED tests/test_api.py::test_create_user - AssertionError
  ========= 1 failed, 41 passed in 2.34s =========
───────────────────────────────────────
Hint: --full | --head 50 | --tail 50 | --grep "pattern"
```

## Steps

1. Parse flags and selector:
   ```bash
   # Paths
   manifest=".fewword/index/tool_outputs.jsonl"
   index_path=".fewword/index/.recent_index"
   helper="$CLAUDE_PLUGIN_ROOT/hooks/scripts/context_helpers.py"

   # Defaults
   full=false
   head_n=0
   tail_n=0
   grep_pat=""
   grep_i=false
   selector=""

   # NEW: Shortcut flags (v1.3.3)
   use_last=false
   use_last_fail=false
   nth=1
   cmd_filter=""

   # Parse arguments with while loop (for/shift doesn't work correctly)
   while [ $# -gt 0 ]; do
     case "$1" in
       --last)
         use_last=true
         # Check if next arg is a command filter (not a flag)
         if [ -n "$2" ] && [ "${2#-}" = "$2" ]; then
           cmd_filter="$2"
           shift
         fi
         shift
         ;;
       --last-fail)
         use_last_fail=true
         # Check if next arg is a command filter (not a flag)
         if [ -n "$2" ] && [ "${2#-}" = "$2" ]; then
           cmd_filter="$2"
           shift
         fi
         shift
         ;;
       --nth)
         if [ -z "$2" ] || [ "${2#-}" != "$2" ]; then
           echo "Error: --nth requires a number (e.g., --nth 2)"
           exit 1
         fi
         # Validate numeric (P1 fix: --nth accepts non-numeric causing confusing errors)
         case "$2" in
           ''|*[!0-9]*) echo "Error: --nth requires a positive integer, got '$2'"; exit 1 ;;
         esac
         nth="$2"
         # Check if next arg is a command filter (not a flag)
         if [ -n "$3" ] && [ "${3#-}" = "$3" ]; then
           cmd_filter="$3"
           shift
         fi
         shift 2
         ;;
       --full)
         full=true
         shift
         ;;
       --head)
         if [ -z "$2" ] || [ "${2#-}" != "$2" ]; then
           echo "Error: --head requires a number (e.g., --head 50)"
           exit 1
         fi
         head_n="$2"
         shift 2
         ;;
       --tail)
         if [ -z "$2" ] || [ "${2#-}" != "$2" ]; then
           echo "Error: --tail requires a number (e.g., --tail 50)"
           exit 1
         fi
         tail_n="$2"
         shift 2
         ;;
       --grep)
         if [ -z "$2" ]; then
           echo "Error: --grep requires a pattern (e.g., --grep \"error\")"
           exit 1
         fi
         grep_pat="$2"
         shift 2
         ;;
       --grep-i)
         if [ -z "$2" ]; then
           echo "Error: --grep-i requires a pattern (e.g., --grep-i \"error\")"
           exit 1
         fi
         grep_pat="$2"
         grep_i=true
         shift 2
         ;;
       *)
         # First non-flag argument is the selector
         if [ -z "$selector" ]; then
           selector="$1"
         fi
         shift
         ;;
     esac
   done

   # Validate: need either selector OR shortcut flag
   if [ -z "$selector" ] && [ "$use_last" = false ] && [ "$use_last_fail" = false ] && [ "$nth" -eq 1 ]; then
     echo "Error: No selector provided."
     echo ""
     echo "Usage:"
     echo "  /context-open <id|number|cmd>          # By ID, number, or command name"
     echo "  /context-open --last [cmd]             # Most recent (optionally filtered)"
     echo "  /context-open --last-fail [cmd]        # Most recent failure"
     echo "  /context-open --nth N [cmd]            # Nth most recent"
     echo ""
     echo "Output flags: --full | --head N | --tail N | --grep pattern"
     exit 1
   fi
   ```

2. Resolve selector to hex ID (with shortcut support):
   ```bash
   # Handle shortcut flags first
   if [ "$use_last" = true ] || [ "$use_last_fail" = true ] || [ "$nth" -gt 1 ]; then
     # Build Python command to find Nth matching entry
     id=$(python3 -c "
import json
import sys

manifest_path = '$manifest'
cmd_filter = '$cmd_filter'
fail_only = $( [ "$use_last_fail" = true ] && echo 'True' || echo 'False' )
nth = $nth

# Read manifest in reverse to find Nth match
entries = []
try:
    with open(manifest_path, 'r') as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get('type') == 'offload':
                    entries.append(entry)
            except (ValueError, KeyError, TypeError):
                pass
except (FileNotFoundError, IOError):
    pass

# Search in reverse (newest first)
matches = 0
for entry in reversed(entries):
    # Apply command filter
    if cmd_filter and entry.get('cmd') != cmd_filter:
        continue
    # Apply failure filter
    if fail_only and entry.get('exit_code', 0) == 0:
        continue
    matches += 1
    if matches == nth:
        print(entry.get('id', ''))
        break
" 2>/dev/null)

     if [ -z "$id" ]; then
       filter_desc=""
       [ -n "$cmd_filter" ] && filter_desc=" for '$cmd_filter'"
       [ "$use_last_fail" = true ] && filter_desc="$filter_desc with failures"
       [ "$nth" -gt 1 ] && filter_desc="$filter_desc (nth=$nth)"
       echo "Error: No matching output found$filter_desc"
       echo ""
       echo "Try /context-recent to see available outputs"
       exit 1
     fi
   else
     # Standard selector resolution
     id=$(python3 "$helper" resolve "$selector" "$manifest" "$index_path" 2>/dev/null)

     if [ -z "$id" ]; then
       echo "Error: Could not resolve '$selector'"
       echo ""
       echo "Try:"
       echo "  - Run /context-recent to see available outputs"
       echo "  - Use a number (1, 2, 3) from the list"
       echo "  - Use an 8-char hex ID (e.g., A1B2C3D4)"
       echo "  - Use a command name (e.g., pytest)"
       echo "  - Use --last, --last-fail, or --nth flags"
       exit 1
     fi
   fi
   ```

3. Lookup entry and file path:
   ```bash
   # Get full entry details
   entry=$(python3 "$helper" lookup "$id" "$manifest" 2>/dev/null)

   if [ -z "$entry" ] || [ "$entry" = "{}" ]; then
     echo "Error: Entry not found for ID '$id'"
     exit 1
   fi

   # Extract fields
   cmd=$(echo "$entry" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cmd',''))")
   exit_code=$(echo "$entry" | python3 -c "import sys,json; print(json.load(sys.stdin).get('exit_code',0))")
   bytes=$(echo "$entry" | python3 -c "import sys,json; print(json.load(sys.stdin).get('bytes',0))")
   lines=$(echo "$entry" | python3 -c "import sys,json; print(json.load(sys.stdin).get('lines',0))")
   path=$(echo "$entry" | python3 -c "import sys,json; print(json.load(sys.stdin).get('path',''))")
   created_at=$(echo "$entry" | python3 -c "import sys,json; print(json.load(sys.stdin).get('created_at',''))")

   # Calculate age
   age=$(python3 "$helper" age "$created_at" 2>/dev/null || echo "?")

   # Format size
   if [ "$bytes" -ge 1048576 ]; then
     size="$((bytes / 1048576))M"
   elif [ "$bytes" -ge 1024 ]; then
     size="$((bytes / 1024))K"
   else
     size="${bytes}B"
   fi
   ```

4. Check file exists:
   ```bash
   if [ ! -f "$path" ]; then
     echo "───────────────────────────────────────"
     echo "[fw $id] $cmd e=$exit_code $size ${lines}L ($age ago) - CLEANED"
     echo "───────────────────────────────────────"
     echo ""
     echo "File has been cleaned up."
     echo "Was at: $path"
     echo ""
     echo "Possible reasons:"
     echo "  - TTL expiration (24h for success, 48h for failures)"
     echo "  - LRU eviction (scratch > 250MB)"
     echo ""
     echo "Use /context-pin <id> next time to preserve important outputs."
     exit 0
   fi
   ```

5. Output based on flags:
   ```bash
   # Print header
   echo "───────────────────────────────────────"
   echo "[fw $id] $cmd e=$exit_code $size ${lines}L ($age ago)"
   echo "───────────────────────────────────────"

   # Handle --full flag
   if [ "$full" = true ]; then
     cat "$path"
     exit 0
   fi

   # Handle --head flag
   if [ "$head_n" -gt 0 ]; then
     head -"$head_n" "$path"
     exit 0
   fi

   # Handle --tail flag
   if [ "$tail_n" -gt 0 ]; then
     tail -"$tail_n" "$path"
     exit 0
   fi

   # Handle --grep / --grep-i flags
   if [ -n "$grep_pat" ]; then
     echo "Matches for: $grep_pat"
     echo ""

     # Cap output at 50 lines / 4KB to prevent context explosion
     max_lines=50
     max_bytes=4096

     if [ "$grep_i" = true ]; then
       result=$(grep -i -n "$grep_pat" "$path" 2>/dev/null | head -"$max_lines")
     else
       result=$(grep -n "$grep_pat" "$path" 2>/dev/null | head -"$max_lines")
     fi

     result_bytes=$(echo "$result" | wc -c | tr -d ' ')
     result_lines=$(echo "$result" | wc -l | tr -d ' ')

     if [ "$result_bytes" -gt "$max_bytes" ]; then
       echo "$result" | head -c "$max_bytes"
       echo ""
       echo "..."
       echo "(truncated at ${max_bytes}B - use --full or refine pattern)"
     elif [ "$result_lines" -ge "$max_lines" ]; then
       echo "$result"
       echo ""
       echo "(truncated at $max_lines lines - use --full or refine pattern)"
     else
       echo "$result"
     fi
     exit 0
   fi

   # Default: Peek (head 3 + tail 5)
   echo "HEAD:"
   head -3 "$path" | sed 's/^/  /'
   echo "TAIL:"
   tail -5 "$path" | sed 's/^/  /'
   echo "───────────────────────────────────────"
   echo "Hint: --full | --head 50 | --tail 50 | --grep \"pattern\""
   ```

## Notes

- Default "peek" costs ~60 tokens vs ~500+ for full dump
- IDs are case-insensitive (a1b2c3d4 = A1B2C3D4)
- Numbers (1, 2, 3) reference the list from /context-recent
- Command names find the latest exact match (not substring)
- --grep output is capped at 50 lines / 4KB to prevent context explosion
