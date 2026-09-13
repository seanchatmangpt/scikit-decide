#!/usr/bin/env bash
set -euo pipefail
slug="${1:?usage: probe-gyms.sh <vendor-slug>}"
case "$slug" in
  agentbench)
    test -d "vendor/gyms/agentbench"
    actual="$(git -C "vendor/gyms/agentbench" rev-parse HEAD)"
    expected="d1e4a10db08c87075c78972e48ecc182be03e2d5"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  agentdojo)
    test -d "vendor/gyms/agentdojo"
    actual="$(git -C "vendor/gyms/agentdojo" rev-parse HEAD)"
    expected="089ed468cf3ed0322acc66b0211f26d9d90dbf60"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  agentgym)
    test -d "vendor/gyms/agentgym"
    actual="$(git -C "vendor/gyms/agentgym" rev-parse HEAD)"
    expected="3ef9235d23e68e7c2920c5422ad957dc8ced5c6c"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  agentlab)
    test -d "vendor/gyms/agentlab"
    actual="$(git -C "vendor/gyms/agentlab" rev-parse HEAD)"
    expected="cbc35a9bc0facaf731bc858c5825edbe757c719f"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  aiopslab)
    test -d "vendor/gyms/aiopslab"
    actual="$(git -C "vendor/gyms/aiopslab" rev-parse HEAD)"
    expected="80901cc77de13a8fb35dc0e3feff78ca09fd6ae4"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  androidworld)
    test -d "vendor/gyms/androidworld"
    actual="$(git -C "vendor/gyms/androidworld" rev-parse HEAD)"
    expected="3e50888527ef9f29b9157ecd537e408008bb1c85"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  asb)
    test -d "vendor/gyms/asb"
    actual="$(git -C "vendor/gyms/asb" rev-parse HEAD)"
    expected="1f561dccf92d55302368fa67679b4ba9d9c8fdc4"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  assetopsbench)
    test -d "vendor/gyms/assetopsbench"
    actual="$(git -C "vendor/gyms/assetopsbench" rev-parse HEAD)"
    expected="e11d1c1b2022db0396364a6d66e24168955a3bb7"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  azuregoat)
    test -d "vendor/gyms/azuregoat"
    actual="$(git -C "vendor/gyms/azuregoat" rev-parse HEAD)"
    expected="b97045952e6df00de735a7f27fd7c4994dcfe8c0"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  bountytasks)
    test -d "vendor/gyms/bountytasks"
    actual="$(git -C "vendor/gyms/bountytasks" rev-parse HEAD)"
    expected="1956e5fd4eff12034a5fbe0544482d2cf52bb5b0"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  browsergym)
    test -d "vendor/gyms/browsergym"
    actual="$(git -C "vendor/gyms/browsergym" rev-parse HEAD)"
    expected="9e779f087de9a65668b6974d11f9ce9816026e96"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  cloudfoxable)
    test -d "vendor/gyms/cloudfoxable"
    actual="$(git -C "vendor/gyms/cloudfoxable" rev-parse HEAD)"
    expected="fc49b7f637268031515ced9fee4b643d3e68db67"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  cloudgoat)
    test -d "vendor/gyms/cloudgoat"
    actual="$(git -C "vendor/gyms/cloudgoat" rev-parse HEAD)"
    expected="abf1ba8f5e47d7ced750fdfa025d51c99f1a43ed"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  crmarena)
    test -d "vendor/gyms/crmarena"
    actual="$(git -C "vendor/gyms/crmarena" rev-parse HEAD)"
    expected="a37d882c3a947f0330a907f513b90a7f08b9c532"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  cube-harness)
    test -d "vendor/gyms/cube-harness"
    actual="$(git -C "vendor/gyms/cube-harness" rev-parse HEAD)"
    expected="126989d75eb156949af37cd182fe9b0d69d94434"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  cube-standard)
    test -d "vendor/gyms/cube-standard"
    actual="$(git -C "vendor/gyms/cube-standard" rev-parse HEAD)"
    expected="9ca7c062d211450df05eb8318a1e847b5373b689"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  cybench)
    test -d "vendor/gyms/cybench"
    actual="$(git -C "vendor/gyms/cybench" rev-parse HEAD)"
    expected="1097a7226eb034d3821208114da38f10b8627ab1"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  cybergym-e2e)
    test -d "vendor/gyms/cybergym-e2e"
    actual="$(git -C "vendor/gyms/cybergym-e2e" rev-parse HEAD)"
    expected="b861317f11641b14ab6ba08b5179d0b044601057"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  devops-gym)
    test -d "vendor/gyms/devops-gym"
    actual="$(git -C "vendor/gyms/devops-gym" rev-parse HEAD)"
    expected="9bbe3f0de632299faa9102b282ebc9ea4a516d67"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  doomarena)
    test -d "vendor/gyms/doomarena"
    actual="$(git -C "vendor/gyms/doomarena" rev-parse HEAD)"
    expected="b80902f107b4d28194580352a59b3029f4a018b4"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  enterprisebench)
    test -d "vendor/gyms/enterprisebench"
    actual="$(git -C "vendor/gyms/enterprisebench" rev-parse HEAD)"
    expected="6b3c501763645cbe1d7f314c6481643f6cd0c52e"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  gcpgoat)
    test -d "vendor/gyms/gcpgoat"
    actual="$(git -C "vendor/gyms/gcpgoat" rev-parse HEAD)"
    expected="44605c4bff4b2da7611dfce78696bb53db6d8c54"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  general-agentbench)
    test -d "vendor/gyms/general-agentbench"
    actual="$(git -C "vendor/gyms/general-agentbench" rev-parse HEAD)"
    expected="35f5c027c31ddcb3366b28674c6cb2957460c0e2"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  harbor)
    test -d "vendor/gyms/harbor"
    actual="$(git -C "vendor/gyms/harbor" rev-parse HEAD)"
    expected="e485e8a6c538a3ba42fe890e61fbd14572c590aa"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  inspect-evals)
    test -d "vendor/gyms/inspect-evals"
    actual="$(git -C "vendor/gyms/inspect-evals" rev-parse HEAD)"
    expected="b935c0e5cfa04710f016f925db75d8e81413e2cf"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  itbench)
    test -d "vendor/gyms/itbench"
    actual="$(git -C "vendor/gyms/itbench" rev-parse HEAD)"
    expected="c8ad897d3ab455b3727c76b2467f0ad41b49c44b"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  kubernetes-goat)
    test -d "vendor/gyms/kubernetes-goat"
    actual="$(git -C "vendor/gyms/kubernetes-goat" rev-parse HEAD)"
    expected="723a0db478f050d173d23b4ce5044b65bce0bdd0"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  mcp-bench)
    test -d "vendor/gyms/mcp-bench"
    actual="$(git -C "vendor/gyms/mcp-bench" rev-parse HEAD)"
    expected="7a8eaeae83a842a2949080acc5473f65e1569daf"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  mcp-universe)
    test -d "vendor/gyms/mcp-universe"
    actual="$(git -C "vendor/gyms/mcp-universe" rev-parse HEAD)"
    expected="48b453021694d9823d308627fb7f6b7edd29541a"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  mcpmark)
    test -d "vendor/gyms/mcpmark"
    actual="$(git -C "vendor/gyms/mcpmark" rev-parse HEAD)"
    expected="cd45b7f57923b9b3985467f5139927575f83141c"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  o11y-bench)
    test -d "vendor/gyms/o11y-bench"
    actual="$(git -C "vendor/gyms/o11y-bench" rev-parse HEAD)"
    expected="867100cb314cf12dee039c3ef5b2534ccfe56919"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  osworld)
    test -d "vendor/gyms/osworld"
    actual="$(git -C "vendor/gyms/osworld" rev-parse HEAD)"
    expected="091f5ef1d5544bc74953c77875d5feb5bed30108"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  qqr)
    test -d "vendor/gyms/qqr"
    actual="$(git -C "vendor/gyms/qqr" rev-parse HEAD)"
    expected="d5c5bafb86bdc2cf471d0e2bef4cb2e645daf3f8"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  r2e-gym)
    test -d "vendor/gyms/r2e-gym"
    actual="$(git -C "vendor/gyms/r2e-gym" rev-parse HEAD)"
    expected="0d94c4eb9431cd195c55a7ea3abd54006c9a1735"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  rcaeval)
    test -d "vendor/gyms/rcaeval"
    actual="$(git -C "vendor/gyms/rcaeval" rev-parse HEAD)"
    expected="4695aa69f4f1f57b9094ca04ff235908b73a8e24"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  sadservers)
    test -d "vendor/gyms/sadservers"
    actual="$(git -C "vendor/gyms/sadservers" rev-parse HEAD)"
    expected="64a06f8531528e9c08911c96ff809f8dc41f86c2"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  scuba)
    test -d "vendor/gyms/scuba"
    actual="$(git -C "vendor/gyms/scuba" rev-parse HEAD)"
    expected="b988d167004d7ea207332eff8d55b0691d8cadf9"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  sec-bench)
    test -d "vendor/gyms/sec-bench"
    actual="$(git -C "vendor/gyms/sec-bench" rev-parse HEAD)"
    expected="31eb43485a3de47da260be0f978528b1f2314415"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  sre-bench)
    test -d "vendor/gyms/sre-bench"
    actual="$(git -C "vendor/gyms/sre-bench" rev-parse HEAD)"
    expected="a85eecdbd09e7ab04ff9bd5b00ecd3e9bc4464c1"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  sregym)
    test -d "vendor/gyms/sregym"
    actual="$(git -C "vendor/gyms/sregym" rev-parse HEAD)"
    expected="ba07faf1a322f9b6d4a279643bb796aa2f36f64b"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  st-webagentbench)
    test -d "vendor/gyms/st-webagentbench"
    actual="$(git -C "vendor/gyms/st-webagentbench" rev-parse HEAD)"
    expected="67f56dd7df9eca1646c9e49407b087e950aa1e77"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  swe-bench)
    test -d "vendor/gyms/swe-bench"
    actual="$(git -C "vendor/gyms/swe-bench" rev-parse HEAD)"
    expected="f7bbbb2ccdf479001d6467c9e34af59e44a840f9"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  tau2-bench)
    test -d "vendor/gyms/tau2-bench"
    actual="$(git -C "vendor/gyms/tau2-bench" rev-parse HEAD)"
    expected="668d3bcd135c02aa3438f987ef45735b7c163ee3"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  terminal-bench)
    test -d "vendor/gyms/terminal-bench"
    actual="$(git -C "vendor/gyms/terminal-bench" rev-parse HEAD)"
    expected="2fd12b88aafdd04a52c298e3940bcb189f9766d6"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  terminal-bench-pro)
    test -d "vendor/gyms/terminal-bench-pro"
    actual="$(git -C "vendor/gyms/terminal-bench-pro" rev-parse HEAD)"
    expected="874af409da6aafebccbf3bc5bb41a2fa4d78784d"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  terragoat)
    test -d "vendor/gyms/terragoat"
    actual="$(git -C "vendor/gyms/terragoat" rev-parse HEAD)"
    expected="729f8da62c6a85ce4af5ad3d123de97776d954c4"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  the-agent-company)
    test -d "vendor/gyms/the-agent-company"
    actual="$(git -C "vendor/gyms/the-agent-company" rev-parse HEAD)"
    expected="98b68ef82a47690c316f42fddb05baafaab56851"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  toolsandbox)
    test -d "vendor/gyms/toolsandbox"
    actual="$(git -C "vendor/gyms/toolsandbox" rev-parse HEAD)"
    expected="165848b9a78cead7ca7fe7c89c688b58e6501219"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  tua-bench)
    test -d "vendor/gyms/tua-bench"
    actual="$(git -C "vendor/gyms/tua-bench" rev-parse HEAD)"
    expected="3497fd320abcafaf4797424192c891a593fd7964"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  webarena)
    test -d "vendor/gyms/webarena"
    actual="$(git -C "vendor/gyms/webarena" rev-parse HEAD)"
    expected="dce04686a56253aefba7b18a4fa0937cf1dc987b"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  wonderbread)
    test -d "vendor/gyms/wonderbread"
    actual="$(git -C "vendor/gyms/wonderbread" rev-parse HEAD)"
    expected="ed052c67aeada04167cdfe92ff8de454aa94627a"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  workarena)
    test -d "vendor/gyms/workarena"
    actual="$(git -C "vendor/gyms/workarena" rev-parse HEAD)"
    expected="a772230a94cf1caf4166b8ead3983f3b3786455b"
    if [[ -n "$expected" && "$actual" != "$expected" ]]; then echo "REFUSED:GITLINK_DRIFT:$slug:$actual:$expected" >&2; exit 65; fi
    echo "PINNED:$slug:$actual"
    ;;
  *) echo "REFUSED:UNKNOWN_FORWARD_BENCH_VENDOR:$slug" >&2; exit 64 ;;
esac
