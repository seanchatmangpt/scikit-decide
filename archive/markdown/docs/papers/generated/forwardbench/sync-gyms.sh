#!/usr/bin/env bash
set -euo pipefail
slug="${1:?usage: sync-gyms.sh <vendor-slug>}"
case "$slug" in
  agentbench)
    git -c submodule.forwardbench-agentbench.update=checkout submodule update --init --depth 1 -- "vendor/gyms/agentbench"
    ;;
  agentdojo)
    git -c submodule.forwardbench-agentdojo.update=checkout submodule update --init --depth 1 -- "vendor/gyms/agentdojo"
    ;;
  agentgym)
    git -c submodule.forwardbench-agentgym.update=checkout submodule update --init --depth 1 -- "vendor/gyms/agentgym"
    ;;
  agentlab)
    git -c submodule.forwardbench-agentlab.update=checkout submodule update --init --depth 1 -- "vendor/gyms/agentlab"
    ;;
  aiopslab)
    git -c submodule.forwardbench-aiopslab.update=checkout submodule update --init --depth 1 -- "vendor/gyms/aiopslab"
    ;;
  androidworld)
    git -c submodule.forwardbench-androidworld.update=checkout submodule update --init --depth 1 -- "vendor/gyms/androidworld"
    ;;
  asb)
    git -c submodule.forwardbench-asb.update=checkout submodule update --init --depth 1 -- "vendor/gyms/asb"
    ;;
  assetopsbench)
    git -c submodule.forwardbench-assetopsbench.update=checkout submodule update --init --depth 1 -- "vendor/gyms/assetopsbench"
    ;;
  azuregoat)
    git -c submodule.forwardbench-azuregoat.update=checkout submodule update --init --depth 1 -- "vendor/gyms/azuregoat"
    ;;
  bountytasks)
    git -c submodule.forwardbench-bountytasks.update=checkout submodule update --init --depth 1 -- "vendor/gyms/bountytasks"
    ;;
  browsergym)
    git -c submodule.forwardbench-browsergym.update=checkout submodule update --init --depth 1 -- "vendor/gyms/browsergym"
    ;;
  cloudfoxable)
    git -c submodule.forwardbench-cloudfoxable.update=checkout submodule update --init --depth 1 -- "vendor/gyms/cloudfoxable"
    ;;
  cloudgoat)
    git -c submodule.forwardbench-cloudgoat.update=checkout submodule update --init --depth 1 -- "vendor/gyms/cloudgoat"
    ;;
  crmarena)
    git -c submodule.forwardbench-crmarena.update=checkout submodule update --init --depth 1 -- "vendor/gyms/crmarena"
    ;;
  cube-harness)
    git -c submodule.forwardbench-cube-harness.update=checkout submodule update --init --depth 1 -- "vendor/gyms/cube-harness"
    ;;
  cube-standard)
    git -c submodule.forwardbench-cube-standard.update=checkout submodule update --init --depth 1 -- "vendor/gyms/cube-standard"
    ;;
  cybench)
    git -c submodule.forwardbench-cybench.update=checkout submodule update --init --depth 1 -- "vendor/gyms/cybench"
    ;;
  cybergym-e2e)
    git -c submodule.forwardbench-cybergym-e2e.update=checkout submodule update --init --depth 1 -- "vendor/gyms/cybergym-e2e"
    ;;
  devops-gym)
    git -c submodule.forwardbench-devops-gym.update=checkout submodule update --init --depth 1 -- "vendor/gyms/devops-gym"
    ;;
  doomarena)
    git -c submodule.forwardbench-doomarena.update=checkout submodule update --init --depth 1 -- "vendor/gyms/doomarena"
    ;;
  enterprisebench)
    git -c submodule.forwardbench-enterprisebench.update=checkout submodule update --init --depth 1 -- "vendor/gyms/enterprisebench"
    ;;
  gcpgoat)
    git -c submodule.forwardbench-gcpgoat.update=checkout submodule update --init --depth 1 -- "vendor/gyms/gcpgoat"
    ;;
  general-agentbench)
    git -c submodule.forwardbench-general-agentbench.update=checkout submodule update --init --depth 1 -- "vendor/gyms/general-agentbench"
    ;;
  harbor)
    git -c submodule.forwardbench-harbor.update=checkout submodule update --init --depth 1 -- "vendor/gyms/harbor"
    ;;
  inspect-evals)
    git -c submodule.forwardbench-inspect-evals.update=checkout submodule update --init --depth 1 -- "vendor/gyms/inspect-evals"
    ;;
  itbench)
    git -c submodule.forwardbench-itbench.update=checkout submodule update --init --depth 1 -- "vendor/gyms/itbench"
    ;;
  kubernetes-goat)
    git -c submodule.forwardbench-kubernetes-goat.update=checkout submodule update --init --depth 1 -- "vendor/gyms/kubernetes-goat"
    ;;
  mcp-bench)
    git -c submodule.forwardbench-mcp-bench.update=checkout submodule update --init --depth 1 -- "vendor/gyms/mcp-bench"
    ;;
  mcp-universe)
    git -c submodule.forwardbench-mcp-universe.update=checkout submodule update --init --depth 1 -- "vendor/gyms/mcp-universe"
    ;;
  mcpmark)
    git -c submodule.forwardbench-mcpmark.update=checkout submodule update --init --depth 1 -- "vendor/gyms/mcpmark"
    ;;
  o11y-bench)
    git -c submodule.forwardbench-o11y-bench.update=checkout submodule update --init --depth 1 -- "vendor/gyms/o11y-bench"
    ;;
  osworld)
    git -c submodule.forwardbench-osworld.update=checkout submodule update --init --depth 1 -- "vendor/gyms/osworld"
    ;;
  qqr)
    git -c submodule.forwardbench-qqr.update=checkout submodule update --init --depth 1 -- "vendor/gyms/qqr"
    ;;
  r2e-gym)
    git -c submodule.forwardbench-r2e-gym.update=checkout submodule update --init --depth 1 -- "vendor/gyms/r2e-gym"
    ;;
  rcaeval)
    git -c submodule.forwardbench-rcaeval.update=checkout submodule update --init --depth 1 -- "vendor/gyms/rcaeval"
    ;;
  sadservers)
    git -c submodule.forwardbench-sadservers.update=checkout submodule update --init --depth 1 -- "vendor/gyms/sadservers"
    ;;
  scuba)
    git -c submodule.forwardbench-scuba.update=checkout submodule update --init --depth 1 -- "vendor/gyms/scuba"
    ;;
  sec-bench)
    git -c submodule.forwardbench-sec-bench.update=checkout submodule update --init --depth 1 -- "vendor/gyms/sec-bench"
    ;;
  sre-bench)
    git -c submodule.forwardbench-sre-bench.update=checkout submodule update --init --depth 1 -- "vendor/gyms/sre-bench"
    ;;
  sregym)
    git -c submodule.forwardbench-sregym.update=checkout submodule update --init --depth 1 -- "vendor/gyms/sregym"
    ;;
  st-webagentbench)
    git -c submodule.forwardbench-st-webagentbench.update=checkout submodule update --init --depth 1 -- "vendor/gyms/st-webagentbench"
    ;;
  swe-bench)
    git -c submodule.forwardbench-swe-bench.update=checkout submodule update --init --depth 1 -- "vendor/gyms/swe-bench"
    ;;
  tau2-bench)
    git -c submodule.forwardbench-tau2-bench.update=checkout submodule update --init --depth 1 -- "vendor/gyms/tau2-bench"
    ;;
  terminal-bench)
    git -c submodule.forwardbench-terminal-bench.update=checkout submodule update --init --depth 1 -- "vendor/gyms/terminal-bench"
    ;;
  terminal-bench-pro)
    git -c submodule.forwardbench-terminal-bench-pro.update=checkout submodule update --init --depth 1 -- "vendor/gyms/terminal-bench-pro"
    ;;
  terragoat)
    git -c submodule.forwardbench-terragoat.update=checkout submodule update --init --depth 1 -- "vendor/gyms/terragoat"
    ;;
  the-agent-company)
    git -c submodule.forwardbench-the-agent-company.update=checkout submodule update --init --depth 1 -- "vendor/gyms/the-agent-company"
    ;;
  toolsandbox)
    git -c submodule.forwardbench-toolsandbox.update=checkout submodule update --init --depth 1 -- "vendor/gyms/toolsandbox"
    ;;
  tua-bench)
    git -c submodule.forwardbench-tua-bench.update=checkout submodule update --init --depth 1 -- "vendor/gyms/tua-bench"
    ;;
  webarena)
    git -c submodule.forwardbench-webarena.update=checkout submodule update --init --depth 1 -- "vendor/gyms/webarena"
    ;;
  wonderbread)
    git -c submodule.forwardbench-wonderbread.update=checkout submodule update --init --depth 1 -- "vendor/gyms/wonderbread"
    ;;
  workarena)
    git -c submodule.forwardbench-workarena.update=checkout submodule update --init --depth 1 -- "vendor/gyms/workarena"
    ;;
  *) echo "REFUSED:UNKNOWN_FORWARD_BENCH_VENDOR:$slug" >&2; exit 64 ;;
esac
