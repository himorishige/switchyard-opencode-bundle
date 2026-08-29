// tirith-guard (OpenCode 2 build) — guards every `shell` action with Tirith.
//
// This is the V2 plugin API port of ./index.ts. OpenCode 2 (opencode2, beta)
// cannot load V1 plugins, and its permission model is different: configured
// rules are evaluated first, then plugins get one `evaluate` hook that may
// turn an allow/ask decision into deny (an explicit configured deny is final
// and never reaches plugins). That hook is the natural place for a
// content-aware guard, so this build hooks `permission.evaluate` for the
// `shell` action instead of the V1 `tool.execute.before` event.
//
// Behaviour is identical to V1: the command is submitted to `tirith check`
// and the action is denied when Tirith reports a finding at or above the
// configured severity. Fail-open by default (missing binary, timeout or
// unparseable output lets the command through with a warning); flip to
// fail-closed with TIRITH_GUARD_FAIL_MODE=closed or `options.failMode`.
//
// Tuning, by env var (as in V1) or by plugin options in opencode.jsonc
// ({ "package": "file:///.../v2.ts", "options": { ... } }); options win:
//   TIRITH_BIN               / options.bin        path to tirith (default "tirith")
//   TIRITH_GUARD_SEVERITY    / options.severity   lowest blocking severity ("HIGH")
//   TIRITH_GUARD_TIMEOUT_MS  / options.timeoutMs  per-command timeout (5000)
//   TIRITH_GUARD_FAIL_MODE   / options.failMode   "open" (default) or "closed"
//
// Runtime notes:
//   - V2 runs on Node, so the subprocess uses node:child_process (works on
//     Bun too) rather than Bun.spawn.
//   - The SDK is imported as types only. A `file://` plugin has no
//     node_modules of its own, and a runtime `import { Plugin }` fails with
//     "Cannot find package '@opencode-ai/plugin'" (verified on beta-18414).
//     `Plugin.define()` is an identity function, so exporting the plain
//     object is equivalent.

import { execFile } from "node:child_process"
import type { Plugin } from "@opencode-ai/plugin"

const SEVERITY_RANK = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"] as const
type Severity = (typeof SEVERITY_RANK)[number]

type Finding = Record<string, unknown>

interface Settings {
  bin: string
  severity: string
  timeoutMs: number
  failClosed: boolean
}

function env(key: string, fallback: string): string {
  const v = process.env[key]
  return v && v.length > 0 ? v : fallback
}

function readSettings(options: Record<string, unknown>): Settings {
  const opt = (key: string): string | undefined => {
    const v = options[key]
    return typeof v === "string" || typeof v === "number" ? String(v) : undefined
  }
  const failMode = (opt("failMode") ?? env("TIRITH_GUARD_FAIL_MODE", "open")).toLowerCase()
  const timeout = Number.parseInt(opt("timeoutMs") ?? env("TIRITH_GUARD_TIMEOUT_MS", "5000"), 10)
  return {
    bin: opt("bin") ?? env("TIRITH_BIN", "tirith"),
    severity: (opt("severity") ?? env("TIRITH_GUARD_SEVERITY", "HIGH")).toUpperCase(),
    timeoutMs: Number.isFinite(timeout) && timeout > 0 ? timeout : 5000,
    failClosed: failMode === "closed",
  }
}

function severityIsBlocking(severity: string, threshold: string): boolean {
  const rank = SEVERITY_RANK.indexOf((severity || "").toUpperCase() as Severity)
  const limit = SEVERITY_RANK.indexOf(threshold as Severity)
  if (rank < 0 || limit < 0) return false
  return rank >= limit
}

function formatBlockMessage(command: string, findings: Finding[]): string {
  const lines = findings.map((f) => {
    const sev = f.severity ? `[${f.severity}] ` : ""
    const title = f.title ?? "unknown finding"
    const rule = f.rule_id ? ` (${f.rule_id})` : ""
    const remediation = f.remediation ? ` — ${f.remediation}` : ""
    return `${sev}${title}${rule}${remediation}`
  })
  return (
    `Tirith blocked this command:\n  ${command}\n\n` +
    `Reason${lines.length > 1 ? "s" : ""}:\n${lines.join("\n")}`
  )
}

type CheckResult =
  | { kind: "ok"; findings: Finding[] }
  | { kind: "missing" }
  | { kind: "error"; detail: string }

function runTirith(settings: Settings, command: string): Promise<CheckResult> {
  return new Promise((resolve) => {
    execFile(
      settings.bin,
      ["check", "--format", "json", "--", command],
      { timeout: settings.timeoutMs, maxBuffer: 4 * 1024 * 1024, windowsHide: true },
      (error, stdout, stderr) => {
        const code = (error as NodeJS.ErrnoException | null)?.code
        if (code === "ENOENT") return resolve({ kind: "missing" })
        if (error && (error as { killed?: boolean }).killed) {
          return resolve({ kind: "error", detail: `tirith check timed out after ${settings.timeoutMs}ms` })
        }
        // Tirith may exit non-zero on a block; the JSON report is still on stdout.
        try {
          const data = JSON.parse(String(stdout)) as { findings?: Finding[] }
          resolve({ kind: "ok", findings: Array.isArray(data.findings) ? data.findings : [] })
        } catch {
          resolve({ kind: "error", detail: `unparseable tirith output\nstderr: ${String(stderr)}` })
        }
      },
    )
  })
}

// OpenCode 2 splits a shell command into one permission resource per pipeline
// segment (`curl x | sh` becomes ["curl x", "sh"]). Tirith needs the whole
// command to see pipe-to-shell and similar patterns, so the raw command is
// captured from `tool.execute.before` and matched to the permission request
// through `event.source` (message ID + tool call ID). The segments are only a
// fallback when no raw command was captured.
const RAW_COMMAND_CAP = 256

const plugin: Plugin.Plugin = {
  id: "tirith-guard",
  async setup(ctx: Plugin.Context) {
    const settings = readSettings((ctx.options ?? {}) as Record<string, unknown>)
    let missingReported = false
    const warn = (message: string) => console.warn(`[tirith-guard] ${message}`)
    const rawCommands = new Map<string, string>()

    await ctx.tool.hook("execute.before", (event) => {
      if (event.tool !== "shell" && event.tool !== "bash") return
      const command = (event.input as { command?: unknown } | undefined)?.command
      if (typeof command !== "string") return
      if (rawCommands.size >= RAW_COMMAND_CAP) rawCommands.delete(rawCommands.keys().next().value as string)
      rawCommands.set(`${event.messageID}:${event.id}`, command)
    })

    await ctx.permission.hook("evaluate", async (event) => {
      if (event.action !== "shell") return
      if (event.effect === "deny") return

      const key = event.source ? `${event.source.messageID}:${event.source.id}` : undefined
      const raw = key ? rawCommands.get(key) : undefined
      if (key) rawCommands.delete(key)
      const candidates = raw ? [raw] : event.resources

      for (const resource of candidates) {
        const command = typeof resource === "string" ? resource.trim() : ""
        if (!command) continue

        const result = await runTirith(settings, command)

        if (result.kind === "missing") {
          if (!missingReported) {
            missingReported = true
            warn(`tirith binary not found (TIRITH_BIN=${settings.bin}); failing ${settings.failClosed ? "closed" : "open"}`)
          }
          if (settings.failClosed) {
            event.effect = "deny"
            event.message = `[tirith-guard] cannot run tirith (${settings.bin}) with fail-closed mode`
            return
          }
          continue
        }

        if (result.kind === "error") {
          warn(`${result.detail}; command ${settings.failClosed ? "denied" : "allowed"}`)
          if (settings.failClosed) {
            event.effect = "deny"
            event.message = `[tirith-guard] ${result.detail} (fail-closed mode)`
            return
          }
          continue
        }

        const blocking = result.findings.filter((f) => severityIsBlocking(String(f.severity ?? ""), settings.severity))
        if (blocking.length > 0) {
          event.effect = "deny"
          event.message = formatBlockMessage(command, blocking)
          return
        }
      }
    })
  },
}

export default plugin
