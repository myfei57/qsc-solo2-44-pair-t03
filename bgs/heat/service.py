"""Heater service."""

from __future__ import annotations

from typing import Any

from ..errors import NotFoundError
from ..service_base import LineService
from .ramp import plan_ramp
from .wall import wall_reading

RAMP_KIND = "heat.ramp"
WALL_KIND = "heat.wall"
WALL_ALARM = "heat.wall.below_target"


class HeatService(LineService):
    """Ramps the wall temperature once the mixer is turning."""

    origin = "heat"
    line = "feed"

    def ramp(self, target_c: float) -> dict[str, Any]:
        """Start a ramp towards ``target_c``."""

        self.require("heat.ramp")
        plan = plan_ramp(target_c, self.context.config.limits)
        self.publish(RAMP_KIND, {"active": True, **plan.describe()})
        self.emit("heat.ramped", plan.describe())
        return self.status()

    def cool(self) -> dict[str, Any]:
        """End the ramp."""

        self.require("heat.cool")
        ramp = self._ramp_record()
        self.publish(
            RAMP_KIND,
            {"active": False, "target_c": ramp.get("target_c", 0.0)},
        )
        self.emit("heat.cooled")
        return self.status()

    def read_wall(self, temperature_c: float) -> dict[str, Any]:
        """Record a measured wall temperature while a ramp is active."""

        ramp = self._ramp_record()
        if not ramp.get("active", False):
            raise NotFoundError("no active ramp to read the wall against", kind=RAMP_KIND)
        reading = wall_reading(
            self.context.thresholds,
            temperature_c,
            self.context.clock.now(),
            target_c=float(ramp.get("target_c", 0.0)),
        )
        self.publish(WALL_KIND, {"active": True, **reading.describe()})
        if not reading.ok:
            self.raise_alarm(WALL_ALARM, reading.describe())
        else:
            self.emit("heat.wall_read", reading.describe())
        return self.status()

    def status(self) -> dict[str, Any]:
        state = self.state()
        heat = state.get("heat", {})
        ramp = heat.get("ramp") if isinstance(heat, dict) else None
        wall = heat.get("wall") if isinstance(heat, dict) else None
        return {
            "ramping": bool(ramp.get("active", False)) if isinstance(ramp, dict) else False,
            "target_c": ramp.get("target_c") if isinstance(ramp, dict) else None,
            "band_c": ramp.get("band_c") if isinstance(ramp, dict) else None,
            "limit_c": self.context.config.limits.wall_temp_max_c,
            "wall": wall if isinstance(wall, dict) else None,
        }

    def _ramp_record(self) -> dict[str, Any]:
        heat = self.state().get("heat", {})
        entry = heat.get("ramp") if isinstance(heat, dict) else None
        if not isinstance(entry, dict):
            raise NotFoundError("heater was never ramped", kind=RAMP_KIND)
        return entry
