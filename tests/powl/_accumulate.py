# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Failure accumulators shared by the POWL test suite.

The suite is deliberately compressed: a property that used to be redrawn by N
parametrized items is now one item that walks the same N inputs. That is only
lossless if a failure still *names every offender*, so nothing here may
``break`` or ``assert`` inside the loop — each case appends a line and the
caller asserts the accumulated list is empty.
"""

from __future__ import annotations

from typing import Callable

from autofde_lab.powl.refusals import PowlError, PowlRefusal


class Failures(list):
    """A list of human-readable failure lines, rendered as the assert message."""

    def check(self, ok: bool, message: str) -> None:
        if not ok:
            self.append(message)

    def expect_refusal(
        self, name: str, build: Callable[[], object], expected: PowlRefusal, detail: str = ""
    ) -> None:
        """Record a failure unless ``build()`` refuses with exactly ``expected``."""
        try:
            build()
        except PowlError as exc:
            if exc.refusal is not expected:
                self.append(
                    f"{name}: expected {expected.name}, got {exc.refusal.name} ({exc})"
                )
            elif detail and detail not in (exc.detail or ""):
                self.append(f"{name}: expected detail {detail!r} in {exc.detail!r}")
        except Exception as exc:  # noqa: BLE001 - a wrong exception type is a failure
            self.append(f"{name}: expected {expected.name}, raised {exc!r}")
        else:
            self.append(f"{name}: expected {expected.name}, nothing was raised")

    def expect_ok(self, name: str, run: Callable[[], object]) -> None:
        try:
            run()
        except Exception as exc:  # noqa: BLE001
            self.append(f"{name}: expected acceptance, raised {exc!r}")

    def report(self) -> str:
        return "\n".join(["", *self])
