# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Compiled DSPy reasoning pipelines for autofde-lab.

This package holds driver logic that used to live inside the vendored
``vendor/gyms/sregym`` submodule (``clients/autofde_lab_dspy/driver.py``,
abandoned). Nothing here is vendored; every module is a fresh,
autofde-lab-owned implementation composed from real DSPy primitives.
"""

from __future__ import annotations
