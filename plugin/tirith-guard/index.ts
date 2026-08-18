// tirith-guard — opencode plugin that guards `bash` tool calls with Tirith.
//
// On every `bash` tool invocation the command is submitted to `tirith check`
// before it runs. If Tirith reports a finding at or above the configured
// severity the tool call is blocked and the reason is surfaced to the agent.
// Clean commands pass through with sub-millisecond Tirith overhead.
//
// The plugin is fail-open by default: if the tirith binary is missing, times
// out, or returns unparseable output the command is allowed to run (and a warn
// is logged). Flip to fail-closed with TIRITH_GUARD_FAIL_MODE=closed.
//
// Behaviour is tuned through environment variables so the distributed file can
// stay static and each user adjusts their own shell profile:
//   TIRITH_BIN            path to the tirith binary (default "tirith")
//   TIRITH_GUARD_SEVERITY lowest severity that blocks (default "HIGH")
//   TIRITH_GUARD_TIMEOUT_MS  per-command check timeout (default 5000)
//   TIRITH_GUARD_FAIL_MODE   "open" (default) allow, or "closed" block on error

import type { Plugin } from "@opencode-ai/plugin"

const SEVERITY_RANK = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"] as const
type Severity = (typeof SEVERITY_RANK)[number]

function env(key: string, fallback: string): string {
  const v = process.env[key]
  return v && v.length > 0 ? v : fallback
}

const bin = env("TIRITH_BIN", "tirith")
const blockSeverity = env("TIRITH_GUARD_SEVERITY", "HIGH").toUpperCase()
const timeoutMs = Number.parseInt(env("TIRITH_GUARD_TIMEOUT_MS", "5000"), 10)
const failMode = env("TIRITH_GUARD_FAIL_MODE", "open").toLowerCase()
const failClosed = failMode === "closed"

function severityIsBlocking(severity: string): boolean {
  const rank = SEVERITY_RANK.indexOf(
    (severity || "").toUpperCase() as Severity,
  )
  const threshold = SEVERITY_RANK.indexOf(blockSeverity as Severity)
  if (rank < 0 || threshold < 0) return false
  return rank >= threshold
}

function formatBlockMessage(command: string, findings: Array<Record<string, unknown>>): string {
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

export const TirithGuard: Plugin = async ({ client }) => {
  let missingReported = false

  return {
    "tool.execute.before": async (input, output) => {
      if (input.tool !== "bash") return
      const command = output.args?.command
      if (!command || typeof command !== "string") return

      let proc: ReturnType<typeof Bun.spawn>
      try {
        proc = Bun.spawn(
          [bin, "check", "--format", "json", "--", command],
          { stdout: "pipe", stderr: "pipe" },
        )
      } catch (e) {
        if (!missingReported) {
          missingReported = true
          await client.app.log({
            body: {
              service: "tirith-guard",
              level: "warn",
              message: `tirith binary not found (TIRITH_BIN=${bin}); failing open`,
            },
          })
        }
        if (failClosed) throw new Error(`[tirith-guard] cannot run tirith (${bin}) with fail-closed mode`)
        return
      }

      const timer = setTimeout(() => {
        try {
          proc.kill()
        } catch {
          /* already exited */
        }
      }, timeoutMs)

      let outText = ""
      let errText = ""
      try {
        ;[outText, errText] = await Promise.all([
          new Response(proc.stdout).text(),
          new Response(proc.stderr).text(),
        ])
      } catch {
        /* reading failed; handled below */
      } finally {
        clearTimeout(timer)
      }

      let findings: Array<Record<string, unknown>> = []
      try {
        const data = JSON.parse(outText) as { action?: string; findings?: Array<Record<string, unknown>> }
        findings = Array.isArray(data.findings) ? data.findings : []
      } catch (e) {
        await client.app.log({
          body: {
            service: "tirith-guard",
            level: "warn",
            message: `tirith check produced unparseable output; command allowed\nstderr: ${errText}`,
          },
        })
        if (failClosed) throw new Error("[tirith-guard] unparseable tirith output with fail-closed mode")
        return
      }

      const blocking = findings.filter((f) =>
        severityIsBlocking(String(f.severity ?? "")),
      )
      if (blocking.length > 0) {
        throw new Error(formatBlockMessage(command, blocking))
      }
    },
  }
}
