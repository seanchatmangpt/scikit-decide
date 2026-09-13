# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The round-trip law, and every falsifier for it, constructed and shown to fail.

The law
-------
``reduce(reconstruct_work_graph(generated tfvars)) == reduce(admitted graph)``

Both sides are reduced explicitly via :func:`autofde_lab.powl.transitive_reduction`.

What this proves and what it does not
-------------------------------------
Reconstruction reads the **generated tfvars text**, not GitHub. No
``terraform apply`` is run against the GitHub provider anywhere in this suite —
``github_issue`` creates real issues in a real repository. This is a
*projection* round trip: the rendered artifact still carries the admitted work
order. It is not evidence about any deployed state.
"""

from __future__ import annotations

import ast
import dataclasses
import re
from pathlib import Path

import pytest

from autofde_lab.autofde.github_projection import (
    METADATA_BEGIN,
    METADATA_END,
    project,
    render_powl_json,
    render_project_plan_json,
    render_tfvars,
)
from autofde_lab.autofde.phase_graph import (
    AUTOFDE_PHASE_GRAPH,
    Phase,
    PhaseGraph,
    WorkItem,
    reduce_order,
    work_partial_order,
)
from autofde_lab.autofde.reconstruct import parse_tfvars, reconstruct_work_graph
from autofde_lab.autofde.refusals import AutoFdeError, AutoFdeRefusal

REPO_ROOT = Path(__file__).resolve().parents[2]
GRAPH = AUTOFDE_PHASE_GRAPH


def _labels(po, ids):
    return {(ids[e.src], ids[e.dst]) for e in reduce_order(po)}


def admitted_edges() -> set[tuple[str, str]]:
    ids = GRAPH.sorted_item_ids()
    return _labels(work_partial_order(GRAPH), ids)


def reconstructed_edges(text: str) -> set[tuple[str, str]]:
    recon = reconstruct_work_graph(text)
    po = recon.partial_order()
    ids = tuple(sorted(it.node_id for it in recon.items))
    return _labels(po, ids)


@pytest.fixture(scope="module")
def tfvars() -> str:
    return render_tfvars(GRAPH)


def edit_meta(text: str, node_id: str, key: str, value: str) -> str:
    """Rewrite one metadata field of one issue, leaving every other byte alone."""
    lines = text.split("\n")
    start = lines.index(f"autofde-node: {node_id}")
    for j in range(start, len(lines)):
        if lines[j] == METADATA_END:
            break
        if lines[j].startswith(f"autofde-{key}: "):
            lines[j] = f"autofde-{key}: {value}"
            out = "\n".join(lines)
            assert out != text, "falsifier did not change anything"
            return out
    raise AssertionError(f"no autofde-{key} in the block for {node_id}")


# ── anti-self-attestation ───────────────────────────────────────────────────


def test_reconstruct_does_not_import_the_projector():
    """Same discipline as ``tests/powl/test_membership.py``."""
    import autofde_lab.autofde.reconstruct as m

    src = Path(m.__file__).read_text()
    import_lines = [
        line
        for line in src.splitlines()
        if line.lstrip().startswith(("import ", "from "))
    ]
    assert import_lines  # guard against a vacuous pass
    assert not [line for line in import_lines if "github_projection" in line]
    assert not any(
        "github_projection" in name for name in vars(m) if not name.startswith("__")
    )


# ══════════════════════════════════════════════════════════════════════════
# THE LAW
# ══════════════════════════════════════════════════════════════════════════


def test_round_trip_law(tfvars):
    """reduce(reconstruct(generated tfvars)) == reduce(admitted graph)."""
    assert reconstructed_edges(tfvars) == admitted_edges()


def test_round_trip_preserves_the_node_set(tfvars):
    recon = reconstruct_work_graph(tfvars)
    assert {it.node_id for it in recon.items} == set(GRAPH.item_map)


def test_round_trip_partial_orders_are_equal_objects(tfvars):
    """``PartialOrder`` normalizes to the reduction, so equality is structural."""
    assert reconstruct_work_graph(tfvars).partial_order() == work_partial_order(GRAPH)


# ── the concurrency the law must preserve ───────────────────────────────────


def test_runtime_kernel_and_azure_pack_are_concurrent_phases():
    assert GRAPH.phases_are_concurrent("runtime-kernel", "azure-pack")


def test_no_edge_is_emitted_between_the_concurrent_branches(tfvars):
    edges = reconstructed_edges(tfvars)
    rk = {"rk-scheduler", "rk-bounds"}
    ap = {"ap-landing-zone", "ap-identity"}
    crossing = {
        (a, b) for (a, b) in edges if (a in rk and b in ap) or (a in ap and b in rk)
    }
    assert crossing == set(), f"concurrent branches were ordered: {crossing}"


# ══════════════════════════════════════════════════════════════════════════
# FALSIFIERS — each constructed, each shown to fail
# ══════════════════════════════════════════════════════════════════════════


def test_falsifier_two_independent_items_ordered_in_powl(tfvars):
    """Ordering rk-scheduler before ap-landing-zone must break the law."""
    injected = edit_meta(
        tfvars, "ap-landing-zone", "requires", "pi-terraform-module, rk-scheduler"
    )
    assert ("rk-scheduler", "ap-landing-zone") in reconstructed_edges(injected)
    assert reconstructed_edges(injected) != admitted_edges()


def test_falsifier_declared_predecessor_lost_from_metadata(tfvars):
    mutated = edit_meta(tfvars, "rk-bounds", "requires", "none")
    assert reconstructed_edges(mutated) != admitted_edges()


def test_falsifier_issue_bound_to_the_wrong_milestone(tfvars):
    mutated = tfvars.replace(
        '    milestone = "azure-pack"', '    milestone = "runtime-kernel"', 1
    )
    assert mutated != tfvars
    with pytest.raises(AutoFdeError) as exc:
        reconstruct_work_graph(mutated)
    assert exc.value.refusal is AutoFdeRefusal.MILESTONE_BINDING_MISMATCH


def test_falsifier_wrong_kind_label(tfvars):
    mutated = tfvars.replace(
        '    labels    = ["kind-cloud"]', '    labels    = ["kind-runtime"]', 1
    )
    assert mutated != tfvars
    with pytest.raises(AutoFdeError) as exc:
        reconstruct_work_graph(mutated)
    assert exc.value.refusal is AutoFdeRefusal.LABEL_MISMATCH


def test_falsifier_no_kind_label_at_all(tfvars):
    mutated = tfvars.replace('    labels    = ["kind-cloud"]', "    labels    = []", 1)
    with pytest.raises(AutoFdeError) as exc:
        reconstruct_work_graph(mutated)
    assert exc.value.refusal is AutoFdeRefusal.LABEL_MISMATCH


def test_falsifier_one_work_item_generating_two_issues(tfvars):
    """A duplicated issue block is a non-injective projection."""
    blocks = re.findall(r"  \{\n(?:.*\n)*?  \},\n", tfvars)
    assert blocks, "no issue blocks found"
    duplicated = tfvars.replace(blocks[-1], blocks[-1] + blocks[-1], 1)
    assert duplicated != tfvars
    with pytest.raises(AutoFdeError) as exc:
        reconstruct_work_graph(duplicated)
    assert exc.value.refusal is AutoFdeRefusal.NON_INJECTIVE_PROJECTION


def test_falsifier_work_item_vanishes_from_the_projection():
    """Dropping bc-attestation changes the node set, so the law fails."""
    kept = tuple(i for i in GRAPH.items if i.node_id != "bc-attestation")
    lossy = render_tfvars(PhaseGraph(phases=GRAPH.phases, items=kept))
    recon = reconstruct_work_graph(lossy)
    assert {it.node_id for it in recon.items} != set(GRAPH.item_map)
    assert reconstructed_edges(lossy) != admitted_edges()


def test_falsifier_issue_with_no_source_graph_node(tfvars):
    """An issue whose metadata names no node is refused, not silently dropped."""
    mutated = tfvars.replace("autofde-node: bc-clock", "autofde-node: ", 1)
    assert mutated != tfvars
    with pytest.raises(AutoFdeError) as exc:
        reconstruct_work_graph(mutated)
    assert exc.value.refusal is AutoFdeRefusal.ORPHAN_ISSUE


def test_falsifier_issue_with_no_metadata_block_at_all(tfvars):
    mutated = tfvars.replace(METADATA_BEGIN, "<!-- unrelated -->", 1)
    with pytest.raises(AutoFdeError) as exc:
        reconstruct_work_graph(mutated)
    assert exc.value.refusal is AutoFdeRefusal.MISSING_PRECEDENCE_METADATA


def test_falsifier_predecessor_naming_an_unprojected_node(tfvars):
    mutated = edit_meta(tfvars, "rk-bounds", "requires", "rk-ghost")
    with pytest.raises(AutoFdeError) as exc:
        reconstruct_work_graph(mutated)
    assert exc.value.refusal is AutoFdeRefusal.UNKNOWN_WORK_ITEM


def test_falsifier_milestone_with_no_admitted_phase(tfvars):
    extra = (
        '  "ghost-phase" = {\n'
        '    title       = "Ghost"\n'
        '    due_date    = ""\n'
        "    description = <<EOT\nnobody works here\nEOT\n"
        "  },\n"
    )
    mutated = tfvars.replace("milestones = {\n", "milestones = {\n" + extra, 1)
    assert mutated != tfvars
    with pytest.raises(AutoFdeError) as exc:
        reconstruct_work_graph(mutated)
    assert exc.value.refusal is AutoFdeRefusal.ORPHAN_MILESTONE


def test_falsifier_issue_bound_to_an_undeclared_milestone(tfvars):
    mutated = tfvars.replace(
        '    milestone = "azure-pack"', '    milestone = "nowhere"', 1
    )
    with pytest.raises(AutoFdeError) as exc:
        reconstruct_work_graph(mutated)
    assert exc.value.refusal is AutoFdeRefusal.ORPHAN_MILESTONE


def test_falsifier_a_cycle_is_refused_at_the_source():
    cyclic = tuple(
        dataclasses.replace(i, requires=("bc-attestation",))
        if i.node_id == "bc-clock"
        else i
        for i in GRAPH.items
    )
    with pytest.raises(AutoFdeError) as exc:
        PhaseGraph(phases=GRAPH.phases, items=cyclic)
    assert exc.value.refusal in {
        AutoFdeRefusal.CYCLIC_WORK_GRAPH,
        AutoFdeRefusal.PHASE_ORDER_VIOLATION,
    }


def test_falsifier_a_cycle_reconstructed_from_tfvars_is_refused(tfvars):
    """Terraform introducing a cycle: bc-attestation made a predecessor of bc-clock."""
    mutated = edit_meta(
        tfvars, "bc-clock", "requires", "ap-identity, bc-attestation, rk-bounds"
    )
    with pytest.raises(AutoFdeError) as exc:
        reconstruct_work_graph(mutated).partial_order()
    assert exc.value.refusal is AutoFdeRefusal.CYCLIC_WORK_GRAPH


def test_falsifier_a_work_edge_against_the_phase_order():
    bad = tuple(
        dataclasses.replace(i, requires=("bc-clock",))
        if i.node_id == "sf-ontology"
        else i
        for i in GRAPH.items
    )
    with pytest.raises(AutoFdeError) as exc:
        PhaseGraph(phases=GRAPH.phases, items=bad)
    assert exc.value.refusal is AutoFdeRefusal.PHASE_ORDER_VIOLATION


def test_falsifier_a_work_edge_across_concurrent_phases():
    """rk-* -> ap-* is not permitted: neither phase precedes the other."""
    bad = tuple(
        dataclasses.replace(i, requires=i.requires + ("rk-scheduler",))
        if i.node_id == "ap-landing-zone"
        else i
        for i in GRAPH.items
    )
    with pytest.raises(AutoFdeError) as exc:
        PhaseGraph(phases=GRAPH.phases, items=bad)
    assert exc.value.refusal is AutoFdeRefusal.PHASE_ORDER_VIOLATION


def test_falsifier_rendering_twice_must_be_byte_identical():
    a = render_tfvars(GRAPH)
    b = render_tfvars(GRAPH)
    assert a == b
    # and declaration order of the source items must not leak into the bytes
    shuffled = PhaseGraph(phases=GRAPH.phases, items=tuple(reversed(GRAPH.items)))
    assert render_tfvars(shuffled) == a
    assert render_powl_json(shuffled) == render_powl_json(GRAPH)
    assert render_project_plan_json(shuffled) == render_project_plan_json(GRAPH)


def test_falsifier_the_round_trip_law_can_actually_fail(tfvars):
    """Guard against a vacuous law: a mutated artifact must not satisfy it."""
    mutated = edit_meta(tfvars, "bc-attestation", "requires", "none")
    assert reconstructed_edges(mutated) != admitted_edges()


# ══════════════════════════════════════════════════════════════════════════
# THE PROVISIONING GRAPH — checked separately, never cited about work order
# ══════════════════════════════════════════════════════════════════════════

MAIN_TF = REPO_ROOT / "infra" / "github" / "project_management" / "main.tf"


def test_provisioning_graph_construction_order():
    """Terraform edges mean 'needs this object's id', and only that.

    This is the provisioning graph's OWN check. It is never evidence about work
    order — see :func:`test_provisioning_graph_is_invariant_under_work_order`.
    """
    hcl = MAIN_TF.read_text()
    assert 'resource "github_repository" "autofde"' in hcl
    # milestones and labels are constructed after the repository
    for res in (
        '"github_repository_milestone" "epics"',
        '"github_issue_label" "issues_labels"',
    ):
        block = hcl.split(f"resource {res}")[1].split("\n}")[0]
        assert "depends_on" in block
        assert "[github_repository.autofde]" in block
    # issues are constructed after the milestone, because they need its number
    issues = hcl.split('resource "github_issue" "tasks"')[1]
    assert "github_repository_milestone.epics[" in issues
    assert ".number" in issues
    assert "github_issue_label.issues_labels[" in issues


def test_provisioning_graph_is_invariant_under_work_order():
    """The decisive argument, executed.

    Two graphs identical except that in one, A blocks B, and in the other they
    are independent. Every field Terraform can see — title, labels, milestone —
    is identical; only the issue-body metadata differs. So the resource graph
    carries zero bits about work order and can never falsify a work-order
    projection.
    """
    phases = (Phase("p", "P", "single phase"),)
    common = dict(phase="p", kind="Runtime", body="work")
    blocking = PhaseGraph(
        phases=phases,
        items=(
            WorkItem(node_id="a", title="A", **common),
            WorkItem(node_id="b", title="B", requires=("a",), **common),
        ),
    )
    independent = PhaseGraph(
        phases=phases,
        items=(
            WorkItem(node_id="a", title="A", **common),
            WorkItem(node_id="b", title="B", **common),
        ),
    )

    def terraform_visible(g):
        return [(i.title, i.labels, i.milestone) for i in project(g)]

    assert terraform_visible(blocking) == terraform_visible(independent)
    # ... while the work graphs genuinely differ
    assert work_partial_order(blocking) != work_partial_order(independent)
    assert len(reduce_order(work_partial_order(blocking))) == 1
    assert len(reduce_order(work_partial_order(independent))) == 0
    # ... and the difference survives only because it is in the body
    assert render_tfvars(blocking) != render_tfvars(independent)
    diff_lines = set(render_tfvars(blocking).split("\n")) ^ set(
        render_tfvars(independent).split("\n")
    )
    assert all(line.strip().startswith("autofde-requires") for line in diff_lines), (
        diff_lines
    )


# ── generated artifacts on disk are current ────────────────────────────────

GEN_DIR = REPO_ROOT / "infra" / "github" / "project_management"


GENERATED_ARTIFACTS = (
    ("project_management.auto.tfvars", render_tfvars),
    ("phase-graph.powl.json", render_powl_json),
    ("github-project-plan.json", render_project_plan_json),
)


def test_checked_in_artifacts_match_a_fresh_render():
    """One property (staleness) over three artifacts; offenders accumulated."""
    offenders: list[str] = []
    for name, render in GENERATED_ARTIFACTS:
        path = GEN_DIR / name
        if not path.exists():
            offenders.append(f"{name}: missing; run `python -m autofde_lab.autofde`")
        elif path.read_text() != render(GRAPH):
            offenders.append(f"{name}: stale")
    assert not offenders, "generated artifacts out of date:\n" + "\n".join(offenders)


def test_tfvars_variable_names_match_main_tf():
    parsed = parse_tfvars((GEN_DIR / "project_management.auto.tfvars").read_text())
    hcl = MAIN_TF.read_text()
    for var in ("milestones", "labels", "issues"):
        assert f'variable "{var}"' in hcl
    assert set(parsed.milestones) == {p.phase_id for p in GRAPH.phases}
    assert len(parsed.issues) == len(GRAPH.items)


def test_ontology_abox_matches_the_admitted_graph():
    """The hand-authored T-Box/A-Box and the Python graph must not drift."""
    ttl = (REPO_ROOT / "ontology" / "autofde-phase-graph.ttl").read_text()
    declared = set(re.findall(r'afde:nodeId "([^"]+)"', ttl))
    assert declared == set(GRAPH.item_map) | set(GRAPH.phase_map)
    precedes = set(re.findall(r"afde:([\w-]+)\s+afde:precedes afde:([\w-]+)\s*\.", ttl))
    assert precedes == admitted_edges()
    # concurrency is asserted by absence, in the ontology too
    assert not [
        (a, b)
        for (a, b) in precedes
        if {a.split("-")[0], b.split("-")[0]} == {"rk", "ap"}
    ]


def test_ontology_ttl_parses_if_rdflib_is_available():
    rdflib = pytest.importorskip("rdflib")
    g = rdflib.Graph()
    g.parse(REPO_ROOT / "ontology" / "autofde-phase-graph.ttl", format="turtle")
    assert len(g) > 100


def test_the_package_contains_no_terraform_invocation_at_all():
    """Hard boundary, asserted rather than merely intended.

    ``github_issue`` creates real issues in a real repository, so nothing here
    may shell out to Terraform — not ``apply``, not ``plan``. The package
    renders text; running Terraform is a human decision outside this code.
    """
    pkg = REPO_ROOT / "src" / "autofde_lab" / "autofde"
    for path in sorted(pkg.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        docstrings = {
            id(n.body[0].value)
            for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef))
            and n.body
            and isinstance(n.body[0], ast.Expr)
            and isinstance(n.body[0].value, ast.Constant)
            and isinstance(n.body[0].value.value, str)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) in docstrings:
                    continue  # prose about the boundary, not a command
                # a command line, not a mention: "terraform apply/plan/..."
                assert not re.match(
                    r"\s*terraform\s+(apply|plan|init|destroy|import)",
                    node.value,
                    re.IGNORECASE,
                ), (path.name, node.value)
        roots: set[str] = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                roots |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                roots.add((n.module or "").split(".")[0])
        assert not roots & {"subprocess", "os"}, (path.name, sorted(roots))
