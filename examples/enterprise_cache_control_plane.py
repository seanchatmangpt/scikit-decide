# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Run a governed cache request with quotas, rollout, and provenance."""

from __future__ import annotations

import tempfile
from pathlib import Path

from autofde_lab.caching import (
    AttestationSigner,
    CacheConfig,
    CacheFabric,
    DataClassification,
    EnterpriseCacheGateway,
    EnterpriseContext,
    GovernancePolicy,
    PolicyEngine,
    ProvenanceLedger,
    QuarantineJournal,
    SLOTargets,
    SLOTracker,
)


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="autofde_lab-enterprise-cache-"))
    fabric = CacheFabric(CacheConfig(persistent_path=root / "cache.sqlite"))
    signer = AttestationSigner(b"example-key-material-32-bytes!!!", key_id="demo")
    ledger = ProvenanceLedger(root / "attestations.jsonl", signer=signer)
    gateway = EnterpriseCacheGateway(
        fabric,
        policy_engine=PolicyEngine(GovernancePolicy.company_default()),
        ledger=ledger,
        quarantine=QuarantineJournal(root / "quarantine.jsonl"),
        slo_tracker=SLOTracker(SLOTargets(minimum_hit_rate=0.0)),
    )
    context = EnterpriseContext(
        tenant="flight-controls",
        application="optimizer",
        environment="prod",
        release_id="optimizer-26.8.5",
        model_fingerprint="model-a1",
        data_fingerprint="data-b2",
        classification=DataClassification.INTERNAL,
        actor="solver-worker",
        change_ticket="CHG-1234",
    )
    namespace = "flight-controls/optimizer/prod/transition-model"
    calls = 0

    def compute() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"cost": 17}

    first = gateway.execute(
        context=context,
        namespace=namespace,
        method="evaluate",
        args=("scenario-1",),
        compute=compute,
    )
    second = gateway.execute(
        context=context,
        namespace=namespace,
        method="evaluate",
        args=("scenario-1",),
        compute=compute,
    )
    print({"first": first, "second": second, "computations": calls})
    print(gateway.health())


if __name__ == "__main__":
    main()
