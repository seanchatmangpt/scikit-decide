#!/usr/bin/env bash
set -euo pipefail

readonly GGEN_VERSION="v26.8.8"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_root="${repo_root}/ggen/fortune5"

case "$(uname -s)/$(uname -m)" in
  Linux/x86_64)
    asset="ggen-x86_64-unknown-linux-gnu.tar.gz"
    sha256="c651d873c2aeb6bd71c3d5356634f0b3f4adafd2454ee354c817a7079c2ea802"
    ;;
  Linux/aarch64|Linux/arm64)
    asset="ggen-aarch64-unknown-linux-gnu.tar.gz"
    sha256="c39d883b43aa6c635f5a490b7c203a1aaa6499e0df14b5d82d9dc4a26b8d22f6"
    ;;
  Darwin/arm64|Darwin/aarch64)
    asset="ggen-aarch64-apple-darwin.tar.gz"
    sha256="673c1b5e1aecc13fd848141e62ef6b2bb5b54f0eb653866826caa01e80aea3df"
    ;;
  Darwin/x86_64)
    asset="ggen-x86_64-apple-darwin.tar.gz"
    sha256="a4304371ce787e7bfe479fdba050960cdb8761fc9ca3d272da6bd7e64af08570"
    ;;
  *)
    echo "REFUSED:UNSUPPORTED_GGEN_VERIFIER_PLATFORM:$(uname -s)/$(uname -m)" >&2
    exit 2
    ;;
esac

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
archive="${workdir}/${asset}"
project="${workdir}/project"
mkdir -p "${project}"
cp "${source_root}/ggen.toml" "${project}/ggen.toml"
cp -R "${source_root}/ontology" "${project}/ontology"
cp -R "${source_root}/templates" "${project}/templates"

python - "${source_root}/ontology/fortune5-k8s.ttl" <<'PYONTOLOGY'
from collections import Counter
from pathlib import Path
import sys

from rdflib import Graph, Namespace
from rdflib.namespace import DCTERMS, PROV, RDF, RDFS, SKOS

path = Path(sys.argv[1])
graph = Graph().parse(path)
f5 = Namespace("urn:autofde-lab:fortune5:")

def one(subject, predicate, label):
    values = list(graph.objects(subject, predicate))
    if len(values) != 1:
        raise SystemExit(f"REFUSED:FORTUNE5_ONTOLOGY_CARDINALITY:{label}:{len(values)}")
    return values[0]

required_public_grounding = (
    (f5.Axis, RDFS.subClassOf, SKOS.ConceptScheme),
    (f5.Option, RDFS.subClassOf, SKOS.Concept),
    (f5.hasOption, RDFS.subPropertyOf, SKOS.hasTopConcept),
    (f5.axisName, RDFS.subPropertyOf, DCTERMS.identifier),
    (f5.optionName, RDFS.subPropertyOf, SKOS.prefLabel),
    (f5.ontology, RDF.type, PROV.Entity),
    (f5.ontology, PROV.wasAttributedTo, f5["autofde-lab"]),
)
for triple in required_public_grounding:
    if triple not in graph:
        raise SystemExit(f"REFUSED:PUBLIC_ONTOLOGY_GROUNDING_MISSING:{triple}")

axes = sorted(set(graph.subjects(RDF.type, f5.Axis)), key=str)
options = sorted(set(graph.subjects(RDF.type, f5.Option)), key=str)
if len(axes) != 14:
    raise SystemExit(f"REFUSED:FORTUNE5_AXIS_COUNT:{len(axes)}")
if len(options) != 74:
    raise SystemExit(f"REFUSED:FORTUNE5_OPTION_COUNT:{len(options)}")

axis_names = []
axis_orders = []
owned_options = []
enterprise_options = []
for axis in axes:
    axis_name = str(one(axis, f5.axisName, f"axisName:{axis}"))
    axis_order = int(one(axis, f5.axisOrder, f"axisOrder:{axis}"))
    axis_names.append(axis_name)
    axis_orders.append(axis_order)
    members = list(graph.objects(axis, f5.hasOption))
    if not members:
        raise SystemExit(f"REFUSED:FORTUNE5_AXIS_EMPTY:{axis_name}")
    owned_options.extend(members)
    if axis_name == "enterprise":
        enterprise_options = [str(one(o, f5.optionName, f"optionName:{o}")) for o in members]

if len(axis_names) != len(set(axis_names)):
    raise SystemExit("REFUSED:DUPLICATE_FORTUNE5_AXIS_NAME")
if len(axis_orders) != len(set(axis_orders)):
    raise SystemExit("REFUSED:DUPLICATE_FORTUNE5_AXIS_ORDER")
ownership = Counter(owned_options)
if set(ownership) != set(options) or any(count != 1 for count in ownership.values()):
    raise SystemExit("REFUSED:FORTUNE5_OPTION_OWNERSHIP_NOT_EXACT")

for option in options:
    one(option, f5.optionName, f"optionName:{option}")
    one(option, f5.optionOrder, f"optionOrder:{option}")

if sorted(enterprise_options) != [f"enterprise-{index:02d}" for index in range(1, 6)]:
    raise SystemExit("REFUSED:CLIENT_NEUTRAL_ENTERPRISE_SET_DRIFT")

print(
    f"fortune5_ontology_triples={len(graph)} axes={len(axes)} options={len(options)} "
    "public_grounding=SKOS+PROV-O+DCTERMS"
)
PYONTOLOGY

python - "${repo_root}/src/autofde_lab/fortune5" <<'PYAUTHORITY'
import ast
from pathlib import Path
import sys

root = Path(sys.argv[1])
banned_imports = (
    "boto3",
    "google.cloud",
    "httpx",
    "kubernetes",
    "requests",
    "socket",
    "subprocess",
    "urllib",
)
banned_callables = {"actuate", "execute", "deploy", "mutate"}
for path in sorted(root.glob("*.py")):
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        else:
            names = []
        for name in names:
            if any(name == banned or name.startswith(f"{banned}.") for banned in banned_imports):
                raise SystemExit(f"REFUSED:FORTUNE5_AMBIENT_AUTHORITY_IMPORT:{path}:{name}")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in banned_callables:
            raise SystemExit(f"REFUSED:FORTUNE5_ACTUATION_SURFACE:{path}:{node.name}")
print("fortune5_authority_fence=SELECT_CONSTRUCT_ONLY")
PYAUTHORITY

curl --fail --location --retry 3 --silent --show-error \
  "https://github.com/seanchatmangpt/ggen/releases/download/${GGEN_VERSION}/${asset}" \
  --output "${archive}"
actual_sha256="$(python - "${archive}" <<'PY'
import hashlib
from pathlib import Path
import sys

print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)"
if [[ "${actual_sha256}" != "${sha256}" ]]; then
  echo "REFUSED:GGEN_ASSET_DIGEST_DRIFT:${actual_sha256}!=${sha256}" >&2
  exit 3
fi

tar -xzf "${archive}" -C "${workdir}"
ggen_bin="$(find "${workdir}" -type f -name ggen -print -quit)"
if [[ -z "${ggen_bin}" ]]; then
  echo "REFUSED:GGEN_BINARY_NOT_FOUND" >&2
  exit 4
fi
chmod +x "${ggen_bin}"

run_ggen() {
  python - "${ggen_bin}" "${project}" <<'PY'
from pathlib import Path
import subprocess
import sys

binary, project = sys.argv[1:]
try:
    completed = subprocess.run(
        [binary, "sync", "run"],
        cwd=Path(project),
        check=False,
        timeout=5,
    )
except subprocess.TimeoutExpired as exc:
    raise SystemExit("REFUSED:GGEN_FIVE_SECOND_BUDGET_EXCEEDED") from exc
if completed.returncode != 0:
    raise SystemExit(completed.returncode)
PY
}

manifest() {
  python - "${project}" <<'PY'
import hashlib
from pathlib import Path
import sys

root = Path(sys.argv[1])
for name in ("catalog.py", "test_fortune5_laws.py"):
    path = root / name
    if not path.is_file():
        raise SystemExit(f"REFUSED:GGEN_OUTPUT_MISSING:{name}")
    print(f"{name}:{hashlib.sha256(path.read_bytes()).hexdigest()}")
PY
}

run_ggen
first_manifest="$(manifest)"
run_ggen
second_manifest="$(manifest)"
if [[ "${first_manifest}" != "${second_manifest}" ]]; then
  echo "REFUSED:GGEN_NONDETERMINISTIC_FORTUNE5_MANUFACTURE" >&2
  printf 'first:\n%s\nsecond:\n%s\n' "${first_manifest}" "${second_manifest}" >&2
  exit 5
fi

python - \
  "${repo_root}/src/autofde_lab/fortune5/catalog.py" \
  "${project}/catalog.py" <<'PY'
import ast
from pathlib import Path
import sys


def rows(path: str):
    tree = ast.parse(Path(path).read_text(), filename=path)
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "CATALOG_ROWS":
                return ast.literal_eval(node.value)
    raise SystemExit(f"REFUSED:CATALOG_ROWS_MISSING:{path}")

committed, manufactured = map(rows, sys.argv[1:])
if committed != manufactured:
    raise SystemExit("REFUSED:GGEN_FORTUNE5_PROJECTION_DRIFT")
print(f"fortune5_catalog_rows={len(committed)}")
PY

python -m compileall -q "${repo_root}/src/autofde_lab/fortune5" "${project}"
PYTHONPATH="${repo_root}/src" python -m pytest -q \
  "${project}/test_fortune5_laws.py" \
  "${repo_root}/tests/fortune5/test_space.py"

PYTHONPATH="${repo_root}/src" python -m autofde_lab.fortune5 summary > "${workdir}/summary.json"
python - "${workdir}/summary.json" <<'PYRECEIPT'
import json
from pathlib import Path
import sys

payload = json.loads(Path(sys.argv[1]).read_text())
expected = {
    "standing": "CANDIDATE",
    "authority": "NONE",
    "axes": 14,
    "raw_upper_bound": 1_327_104_000,
    "pairwise_candidates": 1_605,
    "pairwise_tokens": 2_415,
}
for key, value in expected.items():
    if payload.get(key) != value:
        raise SystemExit(f"REFUSED:FORTUNE5_CLI_RECEIPT_DRIFT:{key}:{payload.get(key)}!={value}")
print("fortune5_cli_receipt=PASS")
PYRECEIPT

printf 'FORTUNE5_GGEN_ALIVE version=%s\n%s\n' "${GGEN_VERSION}" "${second_manifest}"
