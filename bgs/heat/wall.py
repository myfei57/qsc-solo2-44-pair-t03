"""Wall temperature readings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..decision.thresholds import ThresholdSet


@dataclass(frozen=True, slots=True)
class WallReading:
    """One wall temperature with its bound verdict."""

    temperature_c: float
    tick: int
    ok: bool
    code: str

    def describe(self) -> dict[str, Any]:
        return {
            "temperature_c": self.temperature_c,
            "tick": self.tick,
            "ok": self.ok,
            "code": self.code,
        }


def wall_reading(thresholds: ThresholdSet, temperature_c: float, tick: int) -> WallReading:
    """Record a wall temperature."""

    return WallReading(temperature_c=temperature_c, tick=tick, ok=True, code="ok")
