"""Regression guard: the OCEL evidence file must hash to the digest cited."""
import hashlib, json, tempfile
from pathlib import Path
import pytest
from autofde_lab.hub.domain.gym_procedure.level4_gymact_bridge import skip_reason
from autofde_lab.hub.domain.gym_procedure.level4_crown import (
    ValidatedPlan, commit, commit_and_execute)

_SKIP = skip_reason()

@pytest.mark.skipif(_SKIP is not None, reason=_SKIP or "")
def test_ocel_file_hashes_to_the_digest_its_evidence_ref_cites():
    """Measured defect: the file was written with indent=2 while ocel_digest
    was computed over canonical bytes, so the cited digest never verified
    against the artifact it named."""
    ev = Path(tempfile.mkdtemp(prefix="ocel_digest_"))
    vp = ValidatedPlan(plan=("increment",) * 3, model_digest="x")
    res = commit_and_execute(commit(vp, "digest-guard"), "cube_counter",
                             {"target": 3}, {"counter": 3, "solved": True}, ev)
    written = (ev / "episode.ocel.json").read_bytes()
    assert hashlib.sha256(written).hexdigest() == res["ocel_digest"], (
        "episode.ocel.json does not hash to its own cited ocel_digest"
    )
    # and it is still valid JSON round-tripping to the same log
    assert json.loads(written) == res["ocel"]
