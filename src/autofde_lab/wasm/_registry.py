"""Exact-SHA registry for executable Chatman ecosystem Wasm adapters."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from types import MappingProxyType
from typing import Mapping

from ._abi import REGISTRY_SCHEMA
from ._artifacts import artifact_for
from ._model import ComponentDescriptor


def _component(
    *,
    name: str,
    python_name: str,
    repository: str,
    branch: str,
    revision: str,
    capability_class: str,
    visibility: str = "public",
    aliases: tuple[str, ...] = (),
) -> ComponentDescriptor:
    artifact = artifact_for(name)
    return ComponentDescriptor(
        name=name,
        python_name=python_name,
        repository=repository,
        branch=branch,
        revision=revision,
        artifact=artifact.filename,
        artifact_sha256=artifact.sha256,
        artifact_size=artifact.size,
        capability_class=capability_class,
        visibility=visibility,
        aliases=aliases,
    )


_COMPONENTS = (
    _component(
        name="ggen",
        python_name="ggen",
        repository="https://github.com/seanchatmangpt/ggen",
        branch="main",
        revision="c36d72161b847b13555c24132819281f17e40e40",
        capability_class="graph-manufacture",
    ),
    _component(
        name="ggen-legacy",
        python_name="ggen_legacy",
        repository="https://github.com/seanchatmangpt/ggen-legacy",
        branch="main",
        revision="9118fe4569df0e1f98bdae279d01a66b6c177781",
        capability_class="compatibility",
    ),
    _component(
        name="ggen-create",
        python_name="ggen_create",
        repository="https://github.com/seanchatmangpt/ggen-create",
        branch="main",
        revision="f5a0dc1ad7a3c981240231616efdff18eb3990a9",
        capability_class="graph-manufacture",
    ),
    _component(
        name="wasm4pm",
        python_name="wasm4pm",
        repository="https://github.com/seanchatmangpt/wasm4pm",
        branch="agent/mfw-interop-admission",
        revision="400f1795cd17845f0723e4e3edf67c3f1e591b36",
        capability_class="process-evidence",
    ),
    _component(
        name="wasm4pm-compat",
        python_name="wasm4pm_compat",
        repository="https://github.com/seanchatmangpt/wasm4pm-compat",
        branch="main",
        revision="fbc080dc39300dac9dbd1d46edf47caa9916c610",
        capability_class="compatibility",
    ),
    _component(
        name="lsp-max",
        python_name="lsp_max",
        repository="https://github.com/seanchatmangpt/lsp-max",
        branch="master",
        revision="2bc341561312b81c3b6d1b4585e82e0cd524b839",
        capability_class="language-protocol",
    ),
    _component(
        name="star-toml",
        python_name="star_toml",
        repository="https://github.com/seanchatmangpt/star-toml",
        branch="main",
        revision="8395515cf8e68bfdc9edff49fb358c4f1da7c795",
        capability_class="admitted-observation",
    ),
    _component(
        name="mfact",
        python_name="mfact",
        repository="https://github.com/seanchatmangpt/mfact",
        branch="main",
        revision="308384002a15b9946acbcd6f560c5819723d79dc",
        capability_class="formal-admission",
    ),
    _component(
        name="powl",
        python_name="powl",
        repository="https://github.com/seanchatmangpt/POWL",
        branch="main",
        revision="d2bae89b4f3a6375b56225ecfaf5eac3797900dc",
        capability_class="process-planning",
        aliases=("POWL",),
    ),
    _component(
        name="fgn",
        python_name="fgn",
        repository="https://github.com/seanchatmangpt/fgn",
        branch="main",
        revision="ae4156ddb0a1e4a6db0ef36f8675df903dedd718",
        capability_class="agent-runtime",
    ),
    _component(
        name="mfw",
        python_name="mfw",
        repository="https://github.com/seanchatmangpt/mfw",
        branch="agent/wasm4pm-scikit-interop",
        revision="e11e53c017fa76421f3ef58d7299cfcce90d7a60",
        capability_class="manufacture-framework",
        visibility="private",
    ),
    _component(
        name="mmdio",
        python_name="mmdio",
        repository="https://github.com/seanchatmangpt/mmdio",
        branch="main",
        revision="77c80ca2b1a944ecec8e28faa8c1762278f91e2b",
        capability_class="diagram-io",
    ),
    _component(
        name="mu-mcpp",
        python_name="mu_mcpp",
        repository="https://github.com/seanchatmangpt/mcpp",
        branch="master",
        revision="9995559a9042806ba18cd8177b1f5dd4c064008b",
        capability_class="lawful-manufacture",
        visibility="private",
        aliases=("mcpp",),
    ),
    _component(
        name="mu-truex",
        python_name="mu_truex",
        repository="https://github.com/seanchatmangpt/truex",
        branch="main",
        revision="7da0500926ddd0374e91f6ab8d58244f6611fe4a",
        capability_class="lawful-manufacture",
        aliases=("truex",),
    ),
    _component(
        name="cargo-cicd",
        python_name="cargo_cicd",
        repository="https://github.com/seanchatmangpt/cargo-cicd",
        branch="main",
        revision="e64f8224c23771e8c4e5d1d22fb939f812b04e1b",
        capability_class="release-law",
    ),
    _component(
        name="ferroplan",
        python_name="ferroplan",
        repository="https://github.com/seanchatmangpt/ferroplan",
        branch="main",
        revision="282fae46a7cf4f71ab473e33b5f3fdb4d73433c9",
        capability_class="planning-runtime",
    ),
)


class ComponentRegistry:
    def __init__(self, components: Iterable[ComponentDescriptor]) -> None:
        ordered = tuple(components)
        by_name: dict[str, ComponentDescriptor] = {}
        by_python_name: dict[str, ComponentDescriptor] = {}
        for component in ordered:
            if component.name in by_name:
                raise ValueError(f"duplicate component name: {component.name}")
            by_name[component.name] = component
            for key in (component.python_name, *component.aliases):
                if key in by_python_name:
                    raise ValueError(f"duplicate Python binding or alias: {key}")
                by_python_name[key] = component
        self._components = ordered
        self._by_name: Mapping[str, ComponentDescriptor] = MappingProxyType(by_name)
        self._by_python_name: Mapping[str, ComponentDescriptor] = MappingProxyType(
            by_python_name
        )

    @classmethod
    def default(cls) -> "ComponentRegistry":
        return cls(_COMPONENTS)

    def __iter__(self) -> Iterator[ComponentDescriptor]:
        return iter(self._components)

    def __len__(self) -> int:
        return len(self._components)

    def by_name(self, name: str) -> ComponentDescriptor:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise KeyError(f"unknown Chatman component: {name}") from exc

    def by_python_name(self, name: str) -> ComponentDescriptor:
        try:
            return self._by_python_name[name]
        except KeyError as exc:
            raise AttributeError(f"unknown Chatman Python binding: {name}") from exc

    def as_manifest(self) -> dict[str, object]:
        return {
            "schema": REGISTRY_SCHEMA,
            "component_count": len(self),
            "components": [component.as_dict() for component in self],
        }
