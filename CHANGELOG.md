# Changelog

All notable changes to FewWord will be documented in this file.

## [1.3.4] - 2026-01-10

### New Features
- **Manual offloading** (`/save`): Save arbitrary content to FewWord storage with custom labels
- **Session export** (`/export`): Export session history as markdown report
- **Cross-session search** (`/search --all-sessions`): Search across all sessions, not just current
- **MCP allowlist/denylist**: Configure which MCP tools get logged/clamped via `mcp_allowlist` and `mcp_denylist` in config

### Extended Entry Types
- Manual entries (`type: "manual"`) for `/save`
- Export entries (`type: "export"`) for `/export`
- All commands updated to support new entry types in filtering and display

### Improved
- Config precedence: user config (~/.config/fewword/) > repo config (.fewword/config.toml) > env vars
- Filename patterns standardized for smart_cleanup compatibility

## [1.3.3] - 2025-01-09

### Security Hardening
- **Path traversal protection**: All file operations now validate paths are within working directory
  - `context-diff`: Validates manifest-supplied paths before reading
  - `context-unpin`: Validates paths before deletion
  - `context-tag`: Validates `FEWWORD_CWD` environment variable
- **Bounded file reads**: `context-correlate` now limits reads to 2MB to prevent memory exhaustion
- **Redaction test mode**: Secrets masked by default, requires `--show-matches` flag to reveal

### Redaction Fixes
- **Fixed PRIVATE_KEY_CONTENT regex**: Replaced variable-length lookbehind (Python `re` incompatible) with working pattern
- **Fixed HEX_SECRET pattern**: Changed non-capturing group to capturing for proper replacement
- **Fixed length calculation**: Uses `match.lastindex` instead of always `group(1)`

### Manifest Integrity
- **Robust JSON escaping**: Uses `jq -Rs` when available, proper fallback escaping for tabs, newlines, control chars
- **Config loading safety**: Wrapped in try/except with fallback to defaults on malformed configs
- **Directory creation**: Ensures `.fewword/index/` exists before manifest writes
- **Write error handling**: Clear error messages with manifest path on IO failures

### Deterministic Output
- **Signature extraction**: Uses `sorted(set(...))` instead of `list(set(...))` for reproducible results
- **Explanation output**: Uses `min()` instead of `list()[0]` for deterministic element selection

### Error Handling Improvements
- **Explicit encoding**: All `read_text()` calls use `encoding='utf-8', errors='replace'`
- **Tag validation**: Remove path validates tags same as add path
- **Config source reporting**: Reports actual loaded file path, not just existence check
- **Exit code parsing**: Handles negative exit codes correctly (was dropping them)
- **Exception types**: Fixed `auto_pin.py` catching wrong exception type

### Documentation
- **Fixed example numbering** in `config.md` (was 1,2,4 → now 1,2,3,4)
- **Fixed ID truncation** in `context-search.md` tip (4-char → 8-char to match output)
- **Fixed retention defaults** in `help.md` (prose now matches code: 24h/48h)

## [1.3.1] - 2025-01-09

### Added
- **Peek-first retrieval**: `/open` now shows head 3 + tail 5 by default (~60 tokens)
- **Flags for `/open`**:
  - `--full` - Print entire file
  - `--head N` - Print first N lines
  - `--tail N` - Print last N lines
  - `--grep "pattern"` - Search with output cap (50 lines / 4KB)
  - `--grep-i "pattern"` - Case-insensitive search
- **Numbered indexes**: `/recent` shows numbered list with age
- **Multi-mode ID resolution**: Use number (`1`), hex ID (`A1B2`), or command name (`pytest`)
- **Cross-platform age calculation**: Python stdlib (works on macOS, Linux, Windows)
- **Session-scoped index**: `.recent_index_<session_id>` with Windows-safe pointer fallback
- **Opt-in peek on pointer**: `FEWWORD_PEEK_ON_POINTER=1` adds tail preview to Tier 2 failures

### Changed
- `/open` defaults to peek instead of full cat (reduces token cost from ~500+ to ~60)
- Grep output capped at 50 lines / 4KB to prevent context explosion
- Flag parsing uses proper `while [ $# -gt 0 ]` loop with missing-value guards

### Added (new file)
- `hooks/scripts/context_helpers.py` - Cross-platform helpers for age + ID resolution

## [1.3.0] - 2025-01-09

### Added
- **Tiered offloading**: Smarter thresholds for different output sizes
  - < 512B: Shown inline (no offload)
  - 512B - 4KB: Compact pointer only (~35 tokens)
  - \> 4KB: Compact pointer + tail preview (failures only)
- **Ultra-compact pointers**: Reduced from ~200 tokens to ~35 tokens
  - Format: `[fw A1B2C3D4] pytest e=1 45K 882L | /open A1B2C3D4`
- **Session tracking**: Per-session stats via `/stats`
- **New commands**:
  - `/open <id>` - Retrieve offloaded output by ID
  - `/stats` - Show session statistics and token savings
  - `/version` - Show installed version
- **Update notifications**: Automatic check on SessionStart

### Changed
- Preview only shown for failures (exit != 0), not successes
- Improved ID validation (8-char hex check) in commands
- Better error handling for `mv` failures in `/pin`
- Fixed MB decimal calculation in stats display
- Fixed `.gitignore` pattern matching

### Fixed
- Subshell `()` now used instead of `{}` to properly capture exit codes from commands containing `exit N`
- Environment variable parsing now safely handles non-numeric values
- Session ID properly escaped in bash wrapper
- MCP interceptor now merges params instead of replacing entire input

## [1.2.0] - 2025-01-08

### Added
- **Smart retention**: Different TTLs based on exit code
  - Success (exit 0): 24 hours
  - Failure (exit != 0): 48 hours
- **LRU eviction**: Automatic cleanup when scratch exceeds 250MB
- Exit code included in output filenames

### Changed
- Improved cleanup logic with TTL + LRU hybrid approach

## [1.1.0] - 2025-01-07

### Added
- `/recent` command for recovery after context compaction
- `/pin` command to preserve important outputs
- `/search` command to search offloaded files
- LATEST symlinks for quick access to most recent outputs

## [1.0.0] - 2025-01-06

### Added
- Initial release
- Automatic offloading of large Bash outputs (>8KB)
- Preview with first/last 10 lines
- Manifest tracking in `.fewword/index/tool_outputs.jsonl`
- MCP tool interception with pagination clamping
- Privacy-safe logging (no command arguments or secrets logged)
