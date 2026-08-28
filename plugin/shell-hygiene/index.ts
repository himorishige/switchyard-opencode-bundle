// shell-hygiene — OpenCode 2 plugin that cleans up every shell command before it runs.
//
// OpenCode 2 exposes `shell.create.before`, a hook that fires before a shell
// command is spawned — before the permission decision, so it also runs for
// commands that end up denied. It cannot block anything (that is what the
// permission rules and tirith-guard are for); it shapes the environment the
// command will run in:
//
//   1. Credential scrubbing. The shell inherits the OpenCode server's whole
//      environment, including API keys the agent has no business reading
//      (`env | grep KEY` is a classic exfiltration step). Names matching the
//      `scrub` globs are removed. The default list only covers keys the
//      agent's shell never needs; keys the shipped skills rely on
//      (GEMINI_API_KEY / OPENAI_API_KEY for web-search, BACKLOG_API_KEY for
//      bee) are left alone. Use `keep` to protect a name that a scrub glob
//      would otherwise match.
//   2. Timeout cap. The model can ask for long timeouts; `maxTimeoutMs`
//      bounds them.
//   3. External working directory warning. A command that runs outside the
//      project directory is logged (permission rules decide whether it may
//      run; this just makes it visible in the server log).
//
// Options (opencode.jsonc `plugins` object form). Every option is optional:
//   scrub           string[]  env-name globs to remove (replaces the default list)
//   keep            string[]  env names never removed, even if a scrub glob matches
//   maxTimeoutMs    number    upper bound for the per-command timeout (default 600000)
//   warnExternalCwd boolean   log commands whose cwd is outside the project (default true)
//   verbose         boolean   log the scrubbed names for every command (default false)
//
// The SDK is imported as types only: a `file://` plugin has no node_modules
// and a runtime `import { Plugin }` fails to resolve. `Plugin.define()` is an
// identity function, so exporting the plain object is equivalent.

import type { Plugin } from "@opencode-ai/plugin"

const DEFAULT_SCRUB = [
  // the router holds the real Fireworks key; the shell never needs it
  "FIREWORKS_*",
  // model-provider keys that no shipped skill reads from the shell
  "ANTHROPIC_API_KEY",
  "OPENROUTER_API_KEY",
  "DASHSCOPE_API_KEY",
  "HF_TOKEN",
  "HUGGINGFACE_HUB_TOKEN",
  // cloud session material
  "AWS_SECRET_ACCESS_KEY",
  "AWS_SESSION_TOKEN",
  // generic secret-shaped names
  "*_PASSWORD",
  "*_PASSWD",
  "*_PRIVATE_KEY",
  "*_SECRET_KEY",
  "*_CLIENT_SECRET",
]

const DEFAULT_MAX_TIMEOUT_MS = 600_000

interface Settings {
  scrub: RegExp[]
  keep: Set<string>
  maxTimeoutMs: number
  warnExternalCwd: boolean
  verbose: boolean
}

function globToRegExp(glob: string): RegExp {
  const escaped = glob.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".")
  return new RegExp(`^${escaped}$`, "i")
}

function stringList(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined
  return value.filter((v): v is string => typeof v === "string" && v.length > 0)
}

function readSettings(options: Record<string, unknown>): Settings {
  const timeout = typeof options.maxTimeoutMs === "number" ? options.maxTimeoutMs : DEFAULT_MAX_TIMEOUT_MS
  return {
    scrub: (stringList(options.scrub) ?? DEFAULT_SCRUB).map(globToRegExp),
    keep: new Set(stringList(options.keep) ?? []),
    maxTimeoutMs: Number.isFinite(timeout) && timeout > 0 ? timeout : DEFAULT_MAX_TIMEOUT_MS,
    warnExternalCwd: options.warnExternalCwd !== false,
    verbose: options.verbose === true,
  }
}

function isInside(dir: string, root: string): boolean {
  const normalizedRoot = root.endsWith("/") ? root : `${root}/`
  return dir === root || dir.startsWith(normalizedRoot)
}

const plugin: Plugin.Plugin = {
  id: "shell-hygiene",
  async setup(ctx: Plugin.Context) {
    const settings = readSettings((ctx.options ?? {}) as Record<string, unknown>)
    const project = ctx.location.project?.directory ?? ctx.location.directory
    const log = (message: string) => console.warn(`[shell-hygiene] ${message}`)

    await ctx.shell.hook("create.before", (event) => {
      const removed: string[] = []
      for (const name of Object.keys(event.env)) {
        if (settings.keep.has(name)) continue
        if (settings.scrub.some((re) => re.test(name))) {
          delete event.env[name]
          removed.push(name)
        }
      }

      if (event.timeout > settings.maxTimeoutMs) {
        if (settings.verbose) log(`timeout ${event.timeout}ms capped to ${settings.maxTimeoutMs}ms`)
        event.timeout = settings.maxTimeoutMs
      }

      if (settings.warnExternalCwd && project && !isInside(event.cwd, project)) {
        log(`command runs outside the project: cwd=${event.cwd} command=${event.command}`)
      }

      if (settings.verbose && removed.length > 0) {
        log(`removed ${removed.length} env var(s): ${removed.join(", ")}`)
      }
    })
  },
}

export default plugin
