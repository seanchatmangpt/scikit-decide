"""Metadata and verified loading for packaged Chatman Wasm archives."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
from importlib.resources import files
from io import BytesIO
from types import MappingProxyType
from typing import Mapping
from zipfile import BadZipFile, ZipFile

_BASE_ARCHIVE = "chatman-ecosystem-wasm.zip"
_INTEROP_ARCHIVE = "chatman-interop-wasm.zip"
_INTEROP_ENTRIES = frozenset({"mfw.wasm", "wasm4pm.wasm"})


@lru_cache(maxsize=2)
def _archive_bytes(name: str) -> bytes:
    return files("autofde_lab.wasm.artifacts").joinpath(name).read_bytes()


def _read_archive(name: str) -> dict[str, bytes]:
    try:
        with ZipFile(BytesIO(_archive_bytes(name))) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError(f"packaged Wasm archive has duplicates: {name}")
            return {entry: archive.read(entry) for entry in names}
    except BadZipFile as exc:
        raise ValueError(f"packaged Chatman Wasm archive is invalid: {name}") from exc


@lru_cache(maxsize=1)
def _archive_entries() -> Mapping[str, bytes]:
    entries = _read_archive(_BASE_ARCHIVE)
    interop = _read_archive(_INTEROP_ARCHIVE)
    if frozenset(interop) != _INTEROP_ENTRIES:
        raise ValueError("interop Wasm archive must contain exactly MFW and wasm4pm")
    entries.update(interop)
    return MappingProxyType(entries)


@dataclass(frozen=True, slots=True)
class PackagedArtifact:
    component: str
    filename: str
    sha256: str
    size: int

    def bytes(self) -> bytes:
        try:
            value = _archive_entries()[self.filename]
        except KeyError as exc:
            raise ValueError(f"packaged artifact is missing: {self.filename}") from exc
        if len(value) != self.size:
            raise ValueError(f"packaged artifact size drift for {self.filename}")
        if hashlib.sha256(value).hexdigest() != self.sha256:
            raise ValueError(f"packaged artifact digest drift for {self.filename}")
        if not value.startswith(b"\x00asm\x01\x00\x00\x00"):
            raise ValueError(f"packaged artifact is not Wasm v1: {self.filename}")
        return value


_ARTIFACTS = {
    'cargo-cicd': PackagedArtifact(component='cargo-cicd', filename='cargo-cicd.wasm', sha256='910efc260e0fda84e94b4f870326f2bbabcd8ce113c5aa16e3757ed2e88e2f13', size=5925),
    'ferroplan': PackagedArtifact(component='ferroplan', filename='ferroplan.wasm', sha256='24bd821fdef3b79cb64fe80be8c412c0a9ed8a1b02eae50eaf9d758779730177', size=6131),
    'fgn': PackagedArtifact(component='fgn', filename='fgn.wasm', sha256='82ab0cc5861137fdeb0823ca22662847cb65a4f86f473b42147e0462105ccb78', size=5651),
    'ggen': PackagedArtifact(component='ggen', filename='ggen.wasm', sha256='f2ffaec316af46991f29f09b5116843614cd7ff154ca078e49b3d43100416124', size=5524),
    'ggen-create': PackagedArtifact(component='ggen-create', filename='ggen-create.wasm', sha256='12db6ddf18c81229817d281cfe2eac5fb892175fba82a8eb9a62b903bedbf602', size=5844),
    'ggen-legacy': PackagedArtifact(component='ggen-legacy', filename='ggen-legacy.wasm', sha256='8de5404fe048939b078628a1db03ad7ad36b623a82931082e5a9691564f4f390', size=6017),
    'lsp-max': PackagedArtifact(component='lsp-max', filename='lsp-max.wasm', sha256='49b775e6e2d20c4985532e322224a8b49e1df86517ad7aff3aaf806f33e368e3', size=5659),
    'mfact': PackagedArtifact(component='mfact', filename='mfact.wasm', sha256='1fee7f453c94acbc179f8867f5c064c0cd5710717218f91d7932bce3c40d5f85', size=5947),
    'mfw': PackagedArtifact(component='mfw', filename='mfw.wasm', sha256='15cd91ca2e45ebd9408793162e96fa9a0bf975c237ea6acbf6ed8a8de16ab70a', size=5516),
    'mmdio': PackagedArtifact(component='mmdio', filename='mmdio.wasm', sha256='da2194ea8189ca5da8f3701d44077c20376c18cc4244a65ed36a6118f0b12ffb', size=5673),
    'mu-mcpp': PackagedArtifact(component='mu-mcpp', filename='mu-mcpp.wasm', sha256='916eff9e4e31d29e45b009a8b3ffcd20bc6bb19c5577d74e4b40c702cec6b9a7', size=5697),
    'mu-truex': PackagedArtifact(component='mu-truex', filename='mu-truex.wasm', sha256='517cbd247e1055965ec029729abbf88c14822df31bbbde68332c76299dc9ae20', size=5743),
    'powl': PackagedArtifact(component='powl', filename='powl.wasm', sha256='22439bdfecf98554c3a5b3951e581895e7c6cbfad85e0d0e77e2b24dca7e61a8', size=5902),
    'star-toml': PackagedArtifact(component='star-toml', filename='star-toml.wasm', sha256='13d8b03835009efc433c0d833c4cd1d3e950a33775b9d8f358c09b6e1ef16109', size=5747),
    'wasm4pm': PackagedArtifact(component='wasm4pm', filename='wasm4pm.wasm', sha256='bbdf1da87b28e4fb8953a5defe87e7cfa466d64e601b4bae2b37b3c72e8e7a09', size=6037),
    'wasm4pm-compat': PackagedArtifact(component='wasm4pm-compat', filename='wasm4pm-compat.wasm', sha256='c494687886e1bd5b761d8096848b986315165851ecd6e67078f354247bf485f5', size=6154),
}
ARTIFACTS: Mapping[str, PackagedArtifact] = MappingProxyType(_ARTIFACTS)


def artifact_for(name: str) -> PackagedArtifact:
    try:
        return ARTIFACTS[name]
    except KeyError as exc:
        raise KeyError(f"unknown packaged Chatman artifact: {name}") from exc
