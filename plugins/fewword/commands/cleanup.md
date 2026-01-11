---
description: Clean up scratch files and show context storage stats
---

# Context Cleanup

Analyze and clean FewWord storage.

## Steps

1. Show current storage usage (cross-platform):
   ```bash
   # Cross-platform stats using Python (works on Windows, macOS, Linux)
   python3 -c "
from pathlib import Path

def dir_size(p):
    if not p.exists():
        return 0
    return sum(f.stat().st_size for f in p.rglob('*') if f.is_file())

def fmt_size(b):
    if b >= 1048576: return f'{b // 1048576}M'
    if b >= 1024: return f'{b // 1024}K'
    return f'{b}B'

def count_files(p):
    if not p.exists(): return 0
    return sum(1 for f in p.rglob('*') if f.is_file())

print('=== FewWord Storage Stats ===')
for name in ['scratch', 'memory', 'index']:
    p = Path('.fewword') / name
    if p.exists():
        print(f'{fmt_size(dir_size(p))}\t.fewword/{name}/')
    else:
        print(f'0B\t.fewword/{name}/ (not found)')

print()
print('=== Scratch Breakdown ===')
scratch = Path('.fewword/scratch')
if scratch.exists():
    subdirs = [d for d in scratch.iterdir() if d.is_dir()]
    if subdirs:
        for d in subdirs:
            print(f'{fmt_size(dir_size(d))}\t{d}/')
    else:
        print('Empty')
else:
    print('Empty')

print()
print('=== File Counts ===')
print(f'Scratch files: {count_files(Path(\".fewword/scratch\"))}')
print(f'Memory files: {count_files(Path(\".fewword/memory\"))}')
print(f'Index files: {count_files(Path(\".fewword/index\"))}')
" 2>/dev/null || echo "No .fewword/ directory found"
   ```

2. Ask user what to clean:
   - **All scratch**: Remove everything in `.fewword/scratch/`
   - **Old files only**: Remove files older than 1 hour
   - **Tool outputs only**: Clear `.fewword/scratch/tool_outputs/`
   - **Nothing**: Just show stats

3. Execute cleanup based on choice:
   - All scratch: `rm -rf .fewword/scratch/*` (or on Windows: `rmdir /s /q .fewword\scratch`)
   - Old files (cross-platform Python):
     ```bash
     python3 -c "
import time
from pathlib import Path
cutoff = time.time() - 3600  # 1 hour ago
for f in Path('.fewword/scratch').rglob('*'):
    if f.is_file() and f.stat().st_mtime < cutoff:
        f.unlink()
        print(f'Deleted: {f}')
"
     ```
   - Tool outputs: `rm -rf .fewword/scratch/tool_outputs/*`

4. Show results after cleanup

**Note**: `index/` is never auto-cleaned - it contains the active plan and tool metadata.
