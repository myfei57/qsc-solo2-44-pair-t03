"""Wall temperature readings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..decision.thresholds import ThresholdSet

WALL_THRESHOLD = "wall_temp"
BELOW_TARGET = "below_target"


@dataclass(frozen=True, slots=True)
class WallReading:
    """One wall temperature with its bound verdict."""

    temperature_c: float
    tick: int
    ok: bool
    code: str
    target_c: float | None = None

    def describe(self) -> dict[str, Any]:
        payload = {
            "temperature_c": self.temperature_c,
            "tick": self.tick,
            "ok": self.ok,
            "code": self.code,
        }
        if self.target_c is not None:
            payload["target_c"] = self.target_c
        return payload


def wall_reading(
    thresholds: ThresholdSet,
    temperature_c: float,
    tick: int,
    *,
    target_c: float | None = None,
) -> WallReading:
    """Compare a wall temperature with the hard bound and, when a ramp is
    active, with the setpoint it is supposed to settle on."""

    verdict = thresholds.evaluate(WALL_THRESHOLD, temperature_c)
    if not verdict.ok:
        return WallReading(
            temperature_c=temperature_c,
            tick=tick,
            ok=False,
            code=verdict.code,
            target_c=target_c,
        )
    if target_c is not None and temperature_c < target_c:
        return WallReading(
            temperature_c=temperature_c,
            tick=tick,
            ok=False,
            code=BELOW_TARGET,
            target_c=target_c,
        )
    return WallReading(
        temperature_c=temperature_c,
        tick=tick,
        ok=True,
        code="ok",
        target_c=target_c,
    )
