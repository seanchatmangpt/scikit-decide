# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Repetition cardinality for POWL 2.0 composite nodes."""

from __future__ import annotations

from dataclasses import dataclass

from autofde_lab.powl.refusals import PowlError, PowlRefusal

__all__ = ["Frequency", "ONCE", "OPTIONAL", "ONE_OR_MORE", "ZERO_OR_MORE"]


@dataclass(frozen=True, slots=True)
class Frequency:
    """How many times a composite node may repeat.

    ``max is None`` means unbounded. The default ``(1, 1)`` means exactly once.
    """

    min: int = 1
    max: int | None = 1

    def __post_init__(self) -> None:
        if not isinstance(self.min, int) or isinstance(self.min, bool):
            raise PowlError(PowlRefusal.INVALID_FREQUENCY, f"min must be int, got {self.min!r}")
        if self.min < 0:
            raise PowlError(PowlRefusal.INVALID_FREQUENCY, f"min={self.min} < 0")
        if self.max is not None:
            if not isinstance(self.max, int) or isinstance(self.max, bool):
                raise PowlError(
                    PowlRefusal.INVALID_FREQUENCY, f"max must be int or None, got {self.max!r}"
                )
            if self.max < self.min:
                raise PowlError(
                    PowlRefusal.INVALID_FREQUENCY, f"max={self.max} < min={self.min}"
                )

    def allows(self, n: int) -> bool:
        """Whether ``n`` repetitions satisfy this cardinality."""
        if n < self.min:
            return False
        return self.max is None or n <= self.max

    @property
    def is_skippable(self) -> bool:
        """``True`` when zero repetitions are allowed."""
        return self.min == 0

    @property
    def is_unbounded(self) -> bool:
        """``True`` when there is no upper bound."""
        return self.max is None

    @property
    def is_repeatable(self) -> bool:
        """``True`` when more than one repetition is allowed."""
        return self.max is None or self.max > 1


ONCE = Frequency(1, 1)
OPTIONAL = Frequency(0, 1)
ONE_OR_MORE = Frequency(1, None)
ZERO_OR_MORE = Frequency(0, None)
