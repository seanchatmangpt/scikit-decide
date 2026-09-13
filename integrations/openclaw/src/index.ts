import { spawn } from "node:child_process";
import { Type } from "typebox";
import { defineToolPlugin } from "openclaw/plugin-sdk/tool-plugin";

type PluginConfig = {
  python?: string;
  cwd?: string;
  timeoutMs?: number;
  maxOutputBytes?: number;
};

type BridgeReply = {
  ok: boolean;
  status: string;
  result?: unknown;
  error?: { code: string; message: string };
  receipt: Record<string, unknown>;
};

const PluginConfigSchema = Type.Object(
  {
    python: Type.Optional(
      Type.String({ minLength: 1, default: "python", description: "Python executable." }),
    ),
    cwd: Type.Optional(Type.String({ description: "scikit-decide checkout or install directory." })),
    timeoutMs: Type.Optional(
      Type.Integer({
        minimum: 1_000,
        maximum: 600_000,
        default: 120_000,
        description: "Maximum wall-clock time for one bridge process.",
      }),
    ),
    maxOutputBytes: Type.Optional(
      Type.Integer({
        minimum: 1_024,
        maximum: 16_777_216,
        default: 4_194_304,
        description: "Combined stdout/stderr capture bound.",
      }),
    ),
  },
  { additionalProperties: false },
);

const Subject = Type.Object(
  {
    name: Type.String({ minLength: 1 }),
    kwargs: Type.Optional(Type.Record(Type.String(), Type.Unknown())),
  },
  { additionalProperties: false },
);

function invokeBridge(
  config: PluginConfig,
  tool: string,
  params: unknown,
  signal?: AbortSignal,
): Promise<BridgeReply> {
  const python = config.python || "python";
  const timeoutMs = config.timeoutMs ?? 120_000;
  const maxOutputBytes = config.maxOutputBytes ?? 4 * 1024 * 1024;
  return new Promise((resolve, reject) => {
    const child = spawn(
      python,
      ["-m", "autofde_lab.openclaw_bridge", "call", tool, "--arguments", JSON.stringify(params)],
      {
        cwd: config.cwd || undefined,
        env: process.env,
        shell: false,
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    let size = 0;
    let settled = false;
    const finish = (error?: Error, reply?: BridgeReply) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      if (error) reject(error);
      else if (reply) resolve(reply);
    };
    const abort = () => {
      child.kill("SIGKILL");
      finish(new Error("scikit-decide bridge call was aborted"));
    };
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      finish(new Error(`scikit-decide bridge exceeded ${timeoutMs}ms`));
    }, timeoutMs);
    if (signal?.aborted) {
      abort();
      return;
    }
    signal?.addEventListener("abort", abort, { once: true });
    const capture = (target: Buffer[], chunk: Buffer) => {
      size += chunk.length;
      if (size > maxOutputBytes) {
        child.kill("SIGKILL");
        finish(new Error(`scikit-decide bridge output exceeded ${maxOutputBytes} bytes`));
        return;
      }
      target.push(chunk);
    };
    child.stdout.on("data", (chunk) => capture(stdout, chunk));
    child.stderr.on("data", (chunk) => capture(stderr, chunk));
    child.on("error", (error) => finish(error));
    child.on("close", (code) => {
      if (settled) return;
      const output = Buffer.concat(stdout).toString("utf8");
      try {
        const reply = JSON.parse(output) as BridgeReply;
        if (code !== 0 && reply.ok) {
          finish(new Error(`scikit-decide bridge exited ${code} after reporting success`));
          return;
        }
        finish(undefined, reply);
      } catch (error) {
        finish(
          new Error(
            `scikit-decide bridge returned invalid JSON (exit=${code}): ${Buffer.concat(stderr)
              .toString("utf8")
              .slice(-4000)}`,
            { cause: error },
          ),
        );
      }
    });
  });
}

export default defineToolPlugin({
  id: "scikit-decide",
  name: "scikit-decide",
  description:
    "Registered planning, scheduling, and reinforcement-learning capabilities from scikit-decide",
  activation: { onStartup: true },
  configSchema: PluginConfigSchema,
  tools: (tool) => [
    tool({
      name: "skdecide_catalog",
      label: "scikit-decide catalog",
      description: "List registered scikit-decide domains and solvers.",
      parameters: Type.Object(
        {
          kind: Type.Optional(
            Type.Union([Type.Literal("all"), Type.Literal("domains"), Type.Literal("solvers")]),
          ),
        },
        { additionalProperties: false },
      ),
      execute(params, config, context) {
        return invokeBridge(config, "skdecide_catalog", params, context.signal);
      },
    }),
    tool({
      name: "skdecide_describe",
      label: "Describe scikit-decide subject",
      description: "Describe one registered scikit-decide domain or solver.",
      parameters: Type.Object(
        {
          kind: Type.Union([Type.Literal("domain"), Type.Literal("solver")]),
          name: Type.String({ minLength: 1 }),
        },
        { additionalProperties: false },
      ),
      execute(params, config, context) {
        return invokeBridge(config, "skdecide_describe", params, context.signal);
      },
    }),
    tool({
      name: "skdecide_match",
      label: "Match scikit-decide solvers",
      description: "Construct a registered domain and list compatible registered solvers.",
      parameters: Type.Object({ domain: Subject }, { additionalProperties: false }),
      optional: true,
      execute(params, config, context) {
        return invokeBridge(config, "skdecide_match", params, context.signal);
      },
    }),
    tool({
      name: "skdecide_run",
      label: "Run scikit-decide rollout",
      description: "Run a bounded scikit-decide rollout using registered subjects only.",
      parameters: Type.Object(
        {
          domain: Subject,
          solver: Type.Optional(Subject),
          solve: Type.Optional(Type.Boolean()),
          rollout: Type.Optional(
            Type.Object(
              {
                num_episodes: Type.Optional(Type.Integer({ minimum: 1, maximum: 100 })),
                max_steps: Type.Optional(Type.Integer({ minimum: 1, maximum: 10_000 })),
              },
              { additionalProperties: false },
            ),
          ),
          timeout_seconds: Type.Optional(Type.Number({ exclusiveMinimum: 0, maximum: 600 })),
      },
      { additionalProperties: false },
    ),
      optional: true,
      execute(params, config, context) {
        return invokeBridge(config, "skdecide_run", params, context.signal);
      },
    }),
  ],
});
