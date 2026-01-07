/**
 * Filesystem Context Plugin for OpenCode
 *
 * Equivalent functionality to Claude Code hooks:
 * - tool.execute.before: Bash output offloading (write-then-decide)
 * - tool.execute.after: Tool logging (sanitized)
 * - session.idle: Archive completed plans
 *
 * IMPORTANT: OpenCode MCP limitation - MCP tool calls may not trigger
 * tool.execute.before/after in some versions. MCP interception is best-effort.
 */

import { existsSync, mkdirSync, writeFileSync, appendFileSync, readFileSync, unlinkSync, renameSync, statSync } from 'fs';
import { join, dirname } from 'path';
import { randomUUID } from 'crypto';

// === Configuration ===
const SIZE_THRESHOLD = 8000;  // bytes, below this show full output
const PREVIEW_LINES = 10;

// Interactive commands to skip
const INTERACTIVE_COMMANDS = new Set([
  'ssh', 'vim', 'vi', 'nvim', 'nano', 'emacs', 'less', 'more', 'top',
  'htop', 'watch', 'tmux', 'screen', 'ftp', 'sftp', 'telnet', 'python',
  'python3', 'node', 'irb', 'rails', 'psql', 'mysql', 'sqlite3', 'mongosh',
  'redis-cli', 'man', 'info', 'edit', 'pico', 'joe', 'jed', 'ne'
]);

// Patterns indicating command handles its own output
const SKIP_PATTERNS = [
  />\s*\S+/,           // stdout redirect
  /2>\s*\S+/,          // stderr redirect
  /&>\s*\S+/,          // both redirect
  /\|\s*tee\s+/,       // piping to tee
  /\|\s*less/,         // piping to pager
  /\|\s*more/,         // piping to pager
  /<</,                // heredoc
];

function isDisabled(cwd: string): boolean {
  if (process.env.FEWWORD_DISABLE) return true;
  const disableFile = join(cwd, '.fsctx', 'DISABLE_OFFLOAD');
  return existsSync(disableFile);
}

function getFirstCommand(cmd: string): string {
  const prefixes = ['sudo', 'env', 'nohup', 'nice', 'time', 'strace', 'ltrace'];
  const words = cmd.trim().split(/\s+/);

  for (const word of words) {
    if (word.includes('=') && !word.startsWith('-')) continue;
    if (prefixes.includes(word)) continue;
    return word.split('/').pop() || word;
  }
  return words[0] || '';
}

function shouldSkip(command: string): boolean {
  if (!command?.trim()) return true;

  // Skip pipelines in v1 (exit code masking)
  if (command.includes('|')) return true;

  const firstCmd = getFirstCommand(command);
  if (INTERACTIVE_COMMANDS.has(firstCmd)) return true;

  for (const pattern of SKIP_PATTERNS) {
    if (pattern.test(command)) return true;
  }

  if (command.trim().length < 10) return true;

  return false;
}

function generateWrapper(originalCmd: string, outputFile: string): string {
  const escapedFile = outputFile.replace(/'/g, "'\"'\"'");

  return `
__fsctx_out='${escapedFile}'
__fsctx_dir="$(dirname "$__fsctx_out")"
mkdir -p "$__fsctx_dir" 2>/dev/null

# Capture stdout+stderr
{ ${originalCmd} ; } > "$__fsctx_out" 2>&1
__fsctx_exit=$?

# Measure size
__fsctx_bytes=$(wc -c < "$__fsctx_out" 2>/dev/null | tr -d ' ')
__fsctx_lines=$(wc -l < "$__fsctx_out" 2>/dev/null | tr -d ' ')

# Write-then-decide
if [ "\${__fsctx_bytes:-0}" -lt ${SIZE_THRESHOLD} ]; then
  cat "$__fsctx_out"
  rm -f "$__fsctx_out"
else
  echo ""
  echo "=== [FewWord: Output offloaded] ==="
  echo "File: $__fsctx_out"
  echo "Size: $__fsctx_bytes bytes, $__fsctx_lines lines"
  echo "Exit: $__fsctx_exit"
  echo ""
  if [ "$__fsctx_lines" -le ${PREVIEW_LINES * 2} ]; then
    echo "=== Full output ==="
    cat "$__fsctx_out"
  else
    echo "=== First ${PREVIEW_LINES} lines ==="
    head -${PREVIEW_LINES} "$__fsctx_out"
    __fsctx_omitted=$(( __fsctx_lines - ${PREVIEW_LINES * 2} ))
    echo ""
    echo "... ($__fsctx_omitted lines omitted) ..."
    echo ""
    echo "=== Last ${PREVIEW_LINES} lines ==="
    tail -${PREVIEW_LINES} "$__fsctx_out"
  fi
  echo ""
  echo "=== Retrieval commands ==="
  echo "  Full: cat $__fsctx_out"
  echo "  Grep: grep 'pattern' $__fsctx_out"
fi

exit $__fsctx_exit
`.trim();
}

function logToolExecution(cwd: string, sessionId: string, toolName: string): void {
  try {
    const indexDir = join(cwd, '.fsctx', 'index');
    if (!existsSync(indexDir)) mkdirSync(indexDir, { recursive: true });

    const logFile = join(indexDir, 'tool_log.jsonl');
    const eventId = randomUUID().slice(0, 8);

    const entry = {
      timestamp: new Date().toISOString(),
      event_id: eventId,
      session_id: sessionId,
      tool: toolName,
    };

    appendFileSync(logFile, JSON.stringify(entry) + '\n');
  } catch {
    // Ignore logging errors
  }
}

function archiveCompletedPlans(cwd: string): void {
  try {
    const planFile = join(cwd, '.fsctx', 'index', 'current_plan.yaml');
    if (!existsSync(planFile)) return;

    const content = readFileSync(planFile, 'utf-8');
    if (!content.includes('status: completed')) return;

    const archiveDir = join(cwd, '.fsctx', 'memory', 'plans');
    if (!existsSync(archiveDir)) mkdirSync(archiveDir, { recursive: true });

    const timestamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 15);
    const archivePath = join(archiveDir, `archived_${timestamp}.yaml`);

    renameSync(planFile, archivePath);
    console.log(`[fewword] Archived completed plan to ${archivePath}`);
  } catch {
    // Ignore archival errors
  }
}

// Main plugin export
export default async function fsctxPlugin({ cwd }: { cwd: string }) {
  // Ensure directories exist on load
  const dirs = [
    '.fsctx/scratch/tool_outputs',
    '.fsctx/scratch/subagents',
    '.fsctx/memory/plans',
    '.fsctx/memory/history',
    '.fsctx/memory/patterns',
    '.fsctx/index',
  ];

  for (const dir of dirs) {
    const fullPath = join(cwd, dir);
    if (!existsSync(fullPath)) {
      mkdirSync(fullPath, { recursive: true });
    }
  }

  return {
    name: 'fsctx',

    // Equivalent to Claude Code's PreToolUse
    'tool.execute.before': async (
      context: { tool: string; sessionId?: string },
      args: { command?: string; [key: string]: unknown }
    ) => {
      if (isDisabled(cwd)) return;

      const toolName = context.tool?.toLowerCase() || '';
      const sessionId = context.sessionId || 'unknown';

      // Handle Bash/Execute tools
      if (toolName === 'bash' || toolName === 'execute') {
        const command = args.command as string;
        if (!command || shouldSkip(command)) return;

        const eventId = randomUUID().slice(0, 8);
        const timestamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 15);
        const firstCmd = getFirstCommand(command);
        const safeCmd = firstCmd.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 20);
        const outputFile = join(cwd, `.fsctx/scratch/tool_outputs/${safeCmd}_${timestamp}_${eventId}.txt`);

        args.command = generateWrapper(command, outputFile);
      }

      // Note: MCP tool interception may not work in all OpenCode versions
      // This is documented as a known limitation
    },

    // Equivalent to Claude Code's PostToolUse
    'tool.execute.after': async (
      context: { tool: string; sessionId?: string }
    ) => {
      if (isDisabled(cwd)) return;

      const toolName = context.tool || '';
      const sessionId = context.sessionId || 'unknown';

      // Log tool execution (sanitized)
      logToolExecution(cwd, sessionId, toolName);

      // Check scratch size
      try {
        const scratchDir = join(cwd, '.fsctx', 'scratch');
        if (existsSync(scratchDir)) {
          let totalSize = 0;
          const countFiles = (dir: string) => {
            const items = require('fs').readdirSync(dir, { withFileTypes: true });
            for (const item of items) {
              const fullPath = join(dir, item.name);
              if (item.isDirectory()) {
                countFiles(fullPath);
              } else {
                totalSize += statSync(fullPath).size;
              }
            }
          };
          countFiles(scratchDir);

          const sizeMB = totalSize / (1024 * 1024);
          if (sizeMB > 100) {
            console.log(`[fewword] Warning: .fsctx/scratch/ is ${sizeMB.toFixed(1)}MB - consider cleanup`);
          }
        }
      } catch {
        // Ignore errors
      }
    },

    // Archive completed plans when session goes idle
    'session.idle': async () => {
      archiveCompletedPlans(cwd);
    },
  };
}
