# scikit-decide for OpenClaw

This package projects scikit-decide's registered Python domain and solver entry points into three interoperable OpenClaw surfaces:

- a generated and validated native tool plugin (`skdecide_catalog`, `skdecide_describe`, `skdecide_match`, `skdecide_run`);
- a bundled AgentSkills-compatible `SKILL.md`;
- a stdio MCP server backed by `python -m autofde_lab.openclaw_bridge mcp` and configured through OpenClaw's MCP CLI.

The bridge admits registered names only, applies explicit episode/step/time/output bounds, and emits a receipt for every success, refusal, or failure.

## Build and validate

OpenClaw owns the plugin metadata projection. Do not hand-maintain tool ownership independently of the `defineToolPlugin` entry.

```bash
cd integrations/openclaw
npm install --ignore-scripts --no-audit --no-fund
npm run build
openclaw plugins build --root . --entry ./dist/index.js
openclaw plugins validate --root . --entry ./dist/index.js
npm test
npm pack --dry-run --json
```

CI regenerates `openclaw.plugin.json` and fails when the manifest, package metadata, or compiled runtime drifts from source.

## Hermetic host proof

```bash
export OPENCLAW_STATE_DIR="$(mktemp -d)"
export OPENCLAW_CONFIG_PATH="$OPENCLAW_STATE_DIR/openclaw.json"
export OPENCLAW_TEST_FAST=1
export PYTHONPATH="$(pwd)/src"

openclaw plugins install --link "$(pwd)/integrations/openclaw"
openclaw plugins enable scikit-decide
openclaw plugins inspect scikit-decide --runtime --json
openclaw skills info scikit-decide --json

openclaw mcp add scikit-decide \
  --command python \
  --arg=-m \
  --arg=autofde_lab.openclaw_bridge \
  --arg=mcp \
  --cwd "$(pwd)" \
  --env "PYTHONPATH=$(pwd)/src"
openclaw mcp doctor scikit-decide --probe --json
```

MCP configuration is intentionally explicit. `openclaw.plugin.json` contains plugin discovery metadata, not an ambient MCP actuation path.

## Plugin configuration

The OpenClaw process must use a Python environment that can import scikit-decide. Configure a different executable or working directory under `plugins.entries.scikit-decide.config`:

```json5
{
  plugins: {
    entries: {
      "scikit-decide": {
        enabled: true,
        config: {
          python: "/absolute/path/to/.venv/bin/python",
          cwd: "/absolute/path/to/scikit-decide",
          timeoutMs: 120000,
          maxOutputBytes: 4194304
        }
      }
    }
  }
}
```

## Focused replay

```bash
python -m py_compile src/autofde_lab/openclaw_runtime.py src/autofde_lab/openclaw_bridge.py
python -m pytest tests/test_openclaw_bridge.py -q
cd integrations/openclaw
npm run check
npm pack --dry-run --json
```

`skdecide_match` and `skdecide_run` remain optional because they construct domains or perform computation. Catalog and description are read-only. Native plugin calls and MCP calls share the same Python bridge and receipt semantics.
