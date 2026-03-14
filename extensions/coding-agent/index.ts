/**
 * Coding Agent Extension for OpenClaw
 *
 * Integrates Claude Code via ACP (Agent Client Protocol) using acpx as the
 * backend. All Claude Code invocations go through ACP for lifecycle management.
 *
 * Tools:
 *   - claude_code: Spawn Claude Code via ACP to autonomously complete coding tasks
 *   - hf_space_status: Check Space health/stage
 *   - hf_restart_space: Restart a Space
 */

import { execSync } from "node:child_process";
import { existsSync } from "node:fs";

// ── Types ────────────────────────────────────────────────────────────────────

interface PluginApi {
  pluginConfig: Record<string, unknown>;
  logger: { info: (...a: unknown[]) => void; warn: (...a: unknown[]) => void; error: (...a: unknown[]) => void };
  registerTool?: (def: ToolDef) => void;
}

interface ToolDef {
  name: string;
  description: string;
  label?: string;
  parameters: Record<string, unknown>;
  execute: (toolCallId: string, params: Record<string, unknown>) => Promise<ToolResult>;
}

interface ToolResult {
  content: Array<{ type: "text"; text: string }>;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const WORK_DIR = "/tmp/claude-workspace";
const CLAUDE_TIMEOUT = 300_000; // 5 minutes

function text(t: string): ToolResult {
  return { content: [{ type: "text", text: t }] };
}

function asStr(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}

// ── Git helpers ──────────────────────────────────────────────────────────────

function ensureRepo(targetSpace: string, hfToken: string): void {
  const repoUrl = `https://user:${hfToken}@huggingface.co/spaces/${targetSpace}`;

  if (existsSync(`${WORK_DIR}/.git`)) {
    // Reset to latest remote state (clean slate for each task)
    try {
      execSync("git fetch origin && git reset --hard origin/main", {
        cwd: WORK_DIR,
        timeout: 30_000,
        stdio: "pipe",
      });
      return;
    } catch {
      // If fetch/reset fails, re-clone
      execSync(`rm -rf ${WORK_DIR}`, { stdio: "pipe" });
    }
  }

  // Fresh clone
  if (existsSync(WORK_DIR)) {
    execSync(`rm -rf ${WORK_DIR}`, { stdio: "pipe" });
  }
  execSync(`git clone --depth 20 ${repoUrl} ${WORK_DIR}`, {
    timeout: 60_000,
    stdio: "pipe",
  });
  execSync('git config user.name "Claude Code"', { cwd: WORK_DIR, stdio: "pipe" });
  execSync('git config user.email "claude-code@huggingclaw"', { cwd: WORK_DIR, stdio: "pipe" });
}

function pushChanges(summary: string): string {
  const status = execSync("git status --porcelain", {
    cwd: WORK_DIR,
    encoding: "utf-8",
  }).trim();

  if (!status) return "No files changed.";

  execSync("git add -A", { cwd: WORK_DIR, stdio: "pipe" });
  // Use a safe commit message
  const msg = summary.slice(0, 72).replace(/"/g, '\\"');
  execSync(`git commit -m "Claude Code: ${msg}"`, { cwd: WORK_DIR, stdio: "pipe" });
  execSync("git push", { cwd: WORK_DIR, timeout: 60_000, stdio: "pipe" });

  return `Pushed changes:\n${status}`;
}

// ── Plugin ───────────────────────────────────────────────────────────────────

const plugin = {
  id: "coding-agent",
  name: "Coding Agent",
  description: "Claude Code via ACP for autonomous coding on HF Spaces",

  register(api: PluginApi) {
    const cfg = (api.pluginConfig as Record<string, unknown>) || {};
    const targetSpace = asStr(cfg.targetSpace) || process.env.CODING_AGENT_TARGET_SPACE || "";
    const hfToken = asStr(cfg.hfToken) || process.env.HF_TOKEN || "";
    const zaiApiKey = asStr(cfg.zaiApiKey) || process.env.ZAI_API_KEY || process.env.ZHIPU_API_KEY || "";

    api.logger.info(`coding-agent: targetSpace=${targetSpace}, zaiKey=${zaiApiKey ? "set" : "missing"}`);

    if (!api.registerTool) {
      api.logger.warn("coding-agent: registerTool unavailable — no tools registered");
      return;
    }

    // ── Tool: claude_code ───────────────────────────────────────────────────
    api.registerTool({
      name: "claude_code",
      label: "Run Claude Code",
      description:
        "Run Claude Code via ACP (acpx) to autonomously complete a coding task on the target HF Space. " +
        "Claude Code clones the Space repo, analyzes code, makes changes, and pushes them back. " +
        "Use for: debugging, fixing errors, adding features, refactoring.",
      parameters: {
        type: "object",
        required: ["task"],
        properties: {
          task: {
            type: "string",
            description: "Detailed coding task description. Be specific about what to fix/change and why.",
          },
          auto_push: {
            type: "boolean",
            description: "Automatically push changes after Claude Code finishes (default: true)",
          },
        },
      },
      async execute(_id, params) {
        const task = asStr(params.task);
        const autoPush = params.auto_push !== false;

        if (!targetSpace) return text("Error: no targetSpace configured");
        if (!hfToken) return text("Error: no HF token configured");
        if (!zaiApiKey) return text("Error: no ZAI_API_KEY or ZHIPU_API_KEY configured for Claude Code backend");

        try {
          // 1. Clone / reset to latest
          api.logger.info(`coding-agent: Syncing repo ${targetSpace}...`);
          ensureRepo(targetSpace, hfToken);

          // 2. Run Claude Code via ACP (acpx)
          api.logger.info(`coding-agent: Running Claude Code via ACP: ${task.slice(0, 100)}...`);
          const claudeEnv: Record<string, string> = {
            ...(process.env as Record<string, string>),
            ANTHROPIC_BASE_URL: "https://api.z.ai/api/anthropic",
            ANTHROPIC_AUTH_TOKEN: zaiApiKey,
            ANTHROPIC_DEFAULT_OPUS_MODEL: "GLM-4.7",
            ANTHROPIC_DEFAULT_SONNET_MODEL: "GLM-4.7",
            ANTHROPIC_DEFAULT_HAIKU_MODEL: "GLM-4.5-Air",
            CI: "true",
          };

          const output = execSync(
            `acpx claude ${JSON.stringify(task)}`,
            {
              cwd: WORK_DIR,
              env: claudeEnv,
              timeout: CLAUDE_TIMEOUT,
              encoding: "utf-8",
              maxBuffer: 10 * 1024 * 1024, // 10MB
            },
          );

          // 3. Push changes if requested
          let pushResult = "Auto-push disabled.";
          if (autoPush) {
            try {
              pushResult = pushChanges(task);
            } catch (e: unknown) {
              pushResult = `Push failed: ${e instanceof Error ? e.message : e}`;
            }
          }

          return text(
            `=== Claude Code Output ===\n${output}\n\n=== Changes ===\n${pushResult}`,
          );
        } catch (e: unknown) {
          const msg = e instanceof Error ? e.message : String(e);
          return text(`Claude Code failed:\n${msg.slice(0, 3000)}`);
        }
      },
    });

    // ── Tool: hf_space_status ───────────────────────────────────────────────
    api.registerTool({
      name: "hf_space_status",
      label: "Check Space Health",
      description:
        "Check the current status of the target HuggingFace Space. " +
        "Returns: stage (BUILDING, APP_STARTING, RUNNING, RUNTIME_ERROR, BUILD_ERROR, NO_APP_FILE).",
      parameters: {
        type: "object",
        properties: {},
      },
      async execute() {
        if (!targetSpace) return text("Error: no target space configured");
        try {
          const resp = await fetch(`https://huggingface.co/api/spaces/${targetSpace}`, {
            headers: { Authorization: `Bearer ${hfToken}` },
          });
          if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
          const data = (await resp.json()) as Record<string, unknown>;
          const runtime = (data.runtime as Record<string, unknown>) || {};
          const stage = runtime.stage || "unknown";
          const hardware = runtime.hardware || "unknown";

          // Try hitting the Space URL
          let apiStatus = "not checked";
          try {
            const spaceUrl = `https://${targetSpace.replace("/", "-").toLowerCase()}.hf.space`;
            const probe = await fetch(spaceUrl, { signal: AbortSignal.timeout(8000) });
            apiStatus = probe.ok ? `reachable (${probe.status})` : `error (${probe.status})`;
          } catch {
            apiStatus = "unreachable";
          }

          return text(
            `Space: ${targetSpace}\nStage: ${stage}\nHardware: ${hardware}\nAPI: ${apiStatus}`,
          );
        } catch (e: unknown) {
          return text(`Error checking space: ${e instanceof Error ? e.message : e}`);
        }
      },
    });

    // ── Tool: hf_restart_space ──────────────────────────────────────────────
    api.registerTool({
      name: "hf_restart_space",
      label: "Restart Space",
      description: "Restart the target HuggingFace Space. Use when the Space is stuck or after deploying fixes.",
      parameters: {
        type: "object",
        properties: {},
      },
      async execute() {
        if (!targetSpace) return text("Error: no target space configured");
        try {
          const resp = await fetch(`https://huggingface.co/api/spaces/${targetSpace}/restart`, {
            method: "POST",
            headers: { Authorization: `Bearer ${hfToken}` },
          });
          if (!resp.ok) {
            const body = await resp.text().catch(() => "");
            throw new Error(`${resp.status}: ${body}`);
          }
          return text(`Space ${targetSpace} is restarting`);
        } catch (e: unknown) {
          return text(`Error restarting space: ${e instanceof Error ? e.message : e}`);
        }
      },
    });

    api.logger.info("coding-agent: Registered 3 tools (claude_code, hf_space_status, hf_restart_space)");
  },
};

export default plugin;
