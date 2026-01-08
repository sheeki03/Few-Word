# Changelog

All notable changes to FewWord will be documented in this file.

## [1.3.0] - 2025-01-09

### Added
- **Tiered offloading**: Smarter thresholds for different output sizes
  - < 512B: Shown inline (no offload)
  - 512B - 4KB: Compact pointer only (~35 tokens)
  - \> 4KB: Compact pointer + tail preview (failures only)
- **Ultra-compact pointers**: Reduced from ~200 tokens to ~35 tokens
  - Format: `[fw A1B2C3D4] pytest e=1 45K 882L | /context-open A1B2C3D4`
- **Session tracking**: Per-session stats via `/fewword-stats`
- **New commands**:
  - `/context-open <id>` - Retrieve offloaded output by ID
  - `/fewword-stats` - Show session statistics and token savings
  - `/fewword-version` - Show installed version
- **Update notifications**: Automatic check on SessionStart

### Changed
- Preview only shown for failures (exit != 0), not successes
- Improved ID validation (8-char hex check) in commands
- Better error handling for `mv` failures in `/context-pin`
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
- `/context-recent` command for recovery after context compaction
- `/context-pin` command to preserve important outputs
- `/context-search` command to search offloaded files
- LATEST symlinks for quick access to most recent outputs

## [1.0.0] - 2025-01-06

### Added
- Initial release
- Automatic offloading of large Bash outputs (>8KB)
- Preview with first/last 10 lines
- Manifest tracking in `.fewword/index/tool_outputs.jsonl`
- MCP tool interception with pagination clamping
- Privacy-safe logging (no command arguments or secrets logged)
