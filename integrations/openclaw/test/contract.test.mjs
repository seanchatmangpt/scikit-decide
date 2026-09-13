import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import plugin from "../dist/index.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const repoRoot = path.resolve(root, "../..");
const manifest = JSON.parse(fs.readFileSync(path.join(root, "openclaw.plugin.json"), "utf8"));
const pkg = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
const tools = ["skdecide_catalog", "skdecide_describe", "skdecide_match", "skdecide_run"];

test("OpenClaw-generated manifest owns the exact tool surface", () => {
  assert.equal(manifest.id, "scikit-decide");
  assert.deepEqual(manifest.contracts.tools, tools);
  assert.deepEqual(pkg.openclaw.extensions, ["./dist/index.js"]);
  assert.equal(pkg.devDependencies.openclaw, "2026.7.1-2");
  assert.equal(pkg.peerDependencies.openclaw, ">=2026.7.1-2");
});

test("plugin bundles an eligible skill and keeps MCP as an explicit transport", () => {
  assert.deepEqual(manifest.skills, ["./skills"]);
  assert.equal(Object.hasOwn(manifest, "mcpServers"), false);
  const skillPath = path.join(root, "skills", "scikit-decide", "SKILL.md");
  assert.ok(fs.existsSync(skillPath));
  const skill = fs.readFileSync(skillPath, "utf8");
  assert.match(skill, /^---\nname: scikit-decide\ndescription:/);
});

test("compute-bearing tools are optional, bounded, and not replay-safe", () => {
  assert.equal(manifest.toolMetadata.skdecide_match.optional, true);
  assert.equal(manifest.toolMetadata.skdecide_run.optional, true);
  assert.equal(manifest.toolMetadata.skdecide_match.replaySafe, false);
  assert.equal(manifest.toolMetadata.skdecide_run.replaySafe, false);
  assert.equal(manifest.configSchema.properties.timeoutMs.maximum, 600000);
  assert.equal(manifest.configSchema.properties.maxOutputBytes.maximum, 16777216);
});

test("exact OpenClaw SDK entry executes the receipted Python bridge", async () => {
  const registered = new Map();
  plugin.register({
    pluginConfig: {
      python: process.env.PYTHON || "python",
      cwd: repoRoot,
      timeoutMs: 30_000,
      maxOutputBytes: 1_048_576,
    },
    registerTool(definition, options) {
      registered.set(options?.name ?? definition.name, definition);
    },
  });
  assert.deepEqual([...registered.keys()], tools);
  const result = await registered.get("skdecide_catalog").execute(
    "openclaw-contract-call",
    { kind: "invalid-for-typed-refusal" },
    AbortSignal.timeout(30_000),
  );
  const payload = result.details;
  assert.equal(payload.ok, false);
  assert.equal(payload.status, "REFUSED:INVALID_ARGUMENT");
  assert.equal(payload.error.code, "INVALID_KIND");
  assert.equal(payload.receipt.status, payload.status);
  assert.match(payload.receipt.input_sha256, /^[0-9a-f]{64}$/);
  assert.match(payload.receipt.output_sha256, /^[0-9a-f]{64}$/);
  const receiptPath = process.env.OPENCLAW_NATIVE_TOOL_RECEIPT;
  if (receiptPath) fs.writeFileSync(receiptPath, `${JSON.stringify(payload, null, 2)}\n`);
});
