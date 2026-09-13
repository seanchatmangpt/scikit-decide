# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The dual-read / single-write contract for persisted identifiers.

`docs/migration/AUTOFDE_LAB_RENAME.md` classes schema identifiers and the
data directory as VERSIONED_MIGRATION: they name artifacts that outlive the
process, so they cannot be renamed by substitution. The failure mode is
silent in both directions -- a substituted schema id orphans every receipt
already written, and a substituted data-home path strands a directory of
downloaded data while re-downloading it under the new name. Neither raises.

These tests pin both halves: writers emit exactly one (new) identifier, and
readers still recognise the superseded ones.
"""

from __future__ import annotations

import os

import pytest

from autofde_lab import schema_ids


class TestWritersEmitOnlyTheCurrentIdentifier:
    def test_agent_schemas_are_the_new_versions(self):
        from autofde_lab.agent.models import (
            AGENT_OUTCOME_SCHEMA,
            EPOCH_RECEIPT_SCHEMA,
        )

        assert EPOCH_RECEIPT_SCHEMA == "autofde_lab.agent.epoch_receipt/2"
        assert AGENT_OUTCOME_SCHEMA == "autofde_lab.agent.outcome/2"

    def test_fabric_and_cache_schemas_are_version_bumped_not_edited(self):
        # The version number moves; the previous string is not rewritten.
        assert schema_ids.FABRIC_SCHEMA == "autofde_lab.decision-fabric/3"
        assert schema_ids.CACHE_SCHEMA == "autofde_lab.fabric.errc-cache/2"
        assert schema_ids.DECISION_RESULT_SCHEMA == (
            "autofde_lab.fabric.decision_result/2"
        )


class TestReadersAcceptSupersededIdentifiers:
    @pytest.mark.parametrize(
        "legacy, accepted",
        [
            (
                "skdecide.agent.epoch_receipt/1",
                schema_ids.ACCEPTED_EPOCH_RECEIPT_SCHEMAS,
            ),
            ("skdecide.agent.outcome/1", schema_ids.ACCEPTED_AGENT_OUTCOME_SCHEMAS),
            (
                "skdecide.fabric.decision_result/1",
                schema_ids.ACCEPTED_DECISION_RESULT_SCHEMAS,
            ),
            ("skdecide.decision-fabric/2", schema_ids.ACCEPTED_FABRIC_SCHEMAS),
            ("skdecide.fabric.errc-cache/1", schema_ids.ACCEPTED_CACHE_SCHEMAS),
            # Written by the Phase 3 substitution pass -- a real spelling that
            # exists on disk and must not be orphaned by correcting it.
            ("autofde_lab.decision-fabric/2", schema_ids.ACCEPTED_FABRIC_SCHEMAS),
            ("autofde_lab.fabric.errc-cache/1", schema_ids.ACCEPTED_CACHE_SCHEMAS),
        ],
    )
    def test_legacy_identifier_is_still_recognised(self, legacy, accepted):
        assert schema_ids.accepts(legacy, accepted)

    def test_an_unrelated_identifier_is_not_accepted(self):
        """Anti-vacuity: `accepts` must reject something."""
        assert not schema_ids.accepts(
            "some.other.schema/9", schema_ids.ACCEPTED_FABRIC_SCHEMAS
        )
        assert not schema_ids.accepts(None, schema_ids.ACCEPTED_CACHE_SCHEMAS)

    def test_every_current_identifier_is_in_its_own_accepted_set(self):
        for current, accepted in [
            (schema_ids.EPOCH_RECEIPT_SCHEMA, schema_ids.ACCEPTED_EPOCH_RECEIPT_SCHEMAS),
            (schema_ids.AGENT_OUTCOME_SCHEMA, schema_ids.ACCEPTED_AGENT_OUTCOME_SCHEMAS),
            (schema_ids.FABRIC_SCHEMA, schema_ids.ACCEPTED_FABRIC_SCHEMAS),
            (schema_ids.CACHE_SCHEMA, schema_ids.ACCEPTED_CACHE_SCHEMAS),
            (
                schema_ids.DECISION_RESULT_SCHEMA,
                schema_ids.ACCEPTED_DECISION_RESULT_SCHEMAS,
            ),
        ]:
            assert schema_ids.accepts(current, accepted)


class TestEnterpriseReservedNamespaceGuardsBothPrefixes:
    """The collision guard is the read side of a persisted prefix.

    Checking only the current prefix would let a caller supply
    `skdecide.enterprise.subject_id` and pass a guard whose whole purpose is
    to keep that namespace reserved.
    """

    def _config(self):
        from autofde_lab._cache.enterprise import EnterpriseGatewayConfig

        return EnterpriseGatewayConfig()

    def test_current_prefix_is_what_gets_written(self):
        assert self._config().reserved_metadata_prefix == "autofde_lab.enterprise."

    def test_legacy_prefix_is_declared_read_side_only(self):
        from autofde_lab._cache.enterprise import (
            LEGACY_RESERVED_METADATA_PREFIXES,
        )

        assert "skdecide.enterprise." in LEGACY_RESERVED_METADATA_PREFIXES
        assert (
            self._config().reserved_metadata_prefix
            not in LEGACY_RESERVED_METADATA_PREFIXES
        )


class TestDataHomeResolutionPrefersExplicitThenLegacyThenNew:
    def _resolve(self):
        from autofde_lab.utils import _resolve_default_data_home

        return _resolve_default_data_home()

    def test_new_envvar_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AUTOFDE_LAB_DATA", str(tmp_path / "chosen"))
        monkeypatch.setenv("SKDECIDE_DATA", str(tmp_path / "legacy"))
        assert self._resolve() == str(tmp_path / "chosen")

    def test_legacy_envvar_is_still_honoured(self, monkeypatch, tmp_path):
        monkeypatch.delenv("AUTOFDE_LAB_DATA", raising=False)
        monkeypatch.setenv("SKDECIDE_DATA", str(tmp_path / "legacy"))
        assert self._resolve() == str(tmp_path / "legacy")

    def test_existing_legacy_directory_is_used_not_abandoned(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.delenv("AUTOFDE_LAB_DATA", raising=False)
        monkeypatch.delenv("SKDECIDE_DATA", raising=False)
        home = tmp_path / "home"
        (home / "skdecide_data").mkdir(parents=True)
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))
        assert self._resolve() == str(home / "skdecide_data")

    def test_fresh_install_gets_the_new_directory(self, monkeypatch, tmp_path):
        monkeypatch.delenv("AUTOFDE_LAB_DATA", raising=False)
        monkeypatch.delenv("SKDECIDE_DATA", raising=False)
        home = tmp_path / "empty-home"
        home.mkdir()
        monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))
        assert self._resolve() == "~/autofde_lab_data"

    def test_resolution_never_creates_or_moves_the_legacy_directory(
        self, monkeypatch, tmp_path
    ):
        """Explicitly: no auto-migration. The user's data is not touched."""
        monkeypatch.delenv("AUTOFDE_LAB_DATA", raising=False)
        monkeypatch.delenv("SKDECIDE_DATA", raising=False)
        home = tmp_path / "h2"
        legacy = home / "skdecide_data"
        legacy.mkdir(parents=True)
        (legacy / "marker.txt").write_text("real user data")
        monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))

        self._resolve()

        assert (legacy / "marker.txt").read_text() == "real user data"
        assert not (home / "autofde_lab_data").exists()
