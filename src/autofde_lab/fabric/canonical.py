# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Canonical serialization and hashing for fabric identities and receipts."""

from __future__ import annotations

import hashlib
import importlib.metadata
import inspect
import json
import platform
import re
import sys
from dataclasses import asdict, is_dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from autofde_lab.fabric.models import DecisionRefusal, RefusalCode

_ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]+")


def canonical_json(value: Any) -> str:
    """Serialize a value into stable, compact JSON."""
    return json.dumps(
        to_jsonable(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256(value: Any) -> str:
    """Hash the canonical JSON representation of a value."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def runtime_identity() -> dict[str, Any]:
    """Return the runtime identity that bounds portable cache reuse."""
    try:
        package_version = importlib.metadata.version("scikit-decide")
    except importlib.metadata.PackageNotFoundError:
        package_version = "SOURCE_TREE"
    return {
        "package": "scikit-decide",
        "package_version": package_version,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_cache_tag": sys.implementation.cache_tag,
        "platform_system": platform.system(),
        "platform_machine": platform.machine(),
    }


@lru_cache(maxsize=256)
def implementation_identity(value: type[Any]) -> dict[str, Any]:
    """Bind a domain or solver type to its loaded implementation bytes."""
    module_name = str(getattr(value, "__module__", "UNKNOWN_MODULE"))
    qualified_name = str(getattr(value, "__qualname__", repr(value)))
    module = inspect.getmodule(value)
    try:
        source_path = inspect.getsourcefile(value)
    except TypeError:
        source_path = None
    if source_path is None and module is not None:
        source_path = getattr(module, "__file__", None)

    implementation_sha256 = None
    carrier = "UNOBSERVED"
    if source_path is not None:
        path = Path(source_path)
        if path.is_file():
            try:
                implementation_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
                carrier = "MODULE_FILE"
            except OSError:
                implementation_sha256 = None
    if implementation_sha256 is None:
        try:
            source = inspect.getsource(value).encode("utf-8")
        except (OSError, TypeError):
            source = None
        if source is not None:
            implementation_sha256 = hashlib.sha256(source).hexdigest()
            carrier = "TYPE_SOURCE"

    return {
        "module": module_name,
        "qualified_name": qualified_name,
        "carrier": carrier,
        "implementation_sha256": implementation_sha256,
        "runtime": runtime_identity(),
    }


def to_jsonable(value: Any) -> Any:
    """Convert common solver values into stable JSON-compatible data."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return to_jsonable(value.value)
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump(mode="json", exclude_none=True))
    if isinstance(value, Mapping):
        return {
            str(key): to_jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        converted = [to_jsonable(item) for item in value]
        return sorted(converted, key=canonical_json)
    if hasattr(value, "_asdict"):
        return to_jsonable(value._asdict())
    if hasattr(value, "to_json"):
        rendered = value.to_json()
        try:
            return to_jsonable(json.loads(rendered))
        except (TypeError, json.JSONDecodeError):
            return str(rendered)
    if hasattr(value, "__dict__"):
        public = {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_") and not callable(item)
        }
        if public:
            return to_jsonable(public)
    rendered = _ADDRESS_RE.sub("<address>", str(value))
    if rendered:
        return rendered
    raise DecisionRefusal(
        RefusalCode.SERIALIZATION_FAILED,
        f"cannot serialize value of type {type(value).__name__}",
    )
