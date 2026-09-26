"""Heater service."""

from __future__ import annotations

from typing import Any

from ..errors import NotFoundError
from ..service_base import LineService
from .ramp import plan_ramp
from .wall import wall_reading

RAMP_KIND = "heat.ramp"
WALL_KIND = "heat.wall"


class HeatService(LineService):
    """Ramps the wall temperature once the mixer is turning."""

    origin = "heat"
    line = "feed"

    def ramp(self, target_c: float) -> dict[str, Any]:
        """Start a ramp towards ``target_c``."""

        self.require("heat.ramp")
        plan = plan_ramp(target_c, self.context.config.limits)
        self.publish(RAMP_KIND, {"active": True, **plan.describe()})
        reading = wall_reading(self.context.thresholds, plan.wall_c, self.context.clock.now())
        self.publish(WALL_KIND, reading.describe())
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

    def status(self) -> dict[str, Any]:
        state = self.state()
        heat = state.get("heat", {})
        ramp = heat.get("ramp") if isinstance(heat, dict) else None
        wall = heat.get("wall") if isinstance(heat, dict) else None
        ramping = bool(ramp.get("active", False)) if isinstance(ramp, dict) else False
        return {
            "ramping": ramping,
            "target_c": ramp.get("target_c") if isinstance(ramp, dict) else None,
            "band_c": ramp.get("band_c") if isinstance(ramp, dict) else None,
            "wall_c": wall.get("temperature_c") if isinstance(wall, dict) else None,
            "wall_ok": bool(wall.get("ok", False)) if isinstance(wall, dict) else False,
            "wall": wall if isinstance(wall, dict) else None,
            "limit_c": self.context.config.limits.wall_temp_max_c,
        }

    def _ramp_record(self) -> dict[str, Any]:
        heat = self.state().get("heat", {})
        entry = heat.get("ramp") if isinstance(heat, dict) else None
        if not isinstance(entry, dict):
            raise NotFoundError("heater was never ramped", kind=RAMP_KIND)
        return entry
