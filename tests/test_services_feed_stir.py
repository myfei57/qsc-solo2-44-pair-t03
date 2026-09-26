"""Feed and mixer behaviour, including the durability gate."""

from __future__ import annotations

import pytest

from bgs.errors import BelowLimitError, InterlockBlockedError, NotFoundError, NotDurableError, OrderViolationError, OverLimitError


def test_batch_declared_before_the_mix_is_durable_is_rejected_as_not_durable(runtime):
    runtime.dispatch("stir.start", {})
    runtime.dispatch("stir.homogenize", {"level": 0.9})

    with pytest.raises(NotDurableError) as caught:
        runtime.dispatch("feed.batch", {"batch_id": "B-1", "quantity": 5.0})

    assert "stir.persisted" in caught.value.context["missing"]
    assert caught.value.code == "not_durable"


def test_batch_declared_without_a_running_mixer_is_rejected_as_not_durable(runtime):
    with pytest.raises(NotDurableError):
        runtime.dispatch("feed.batch", {"batch_id": "B-1", "quantity": 5.0})


def test_feed_start_without_a_declared_batch_is_rejected_as_out_of_order(runtime):
    runtime.dispatch("stir.start", {})
    runtime.dispatch("stir.homogenize", {"level": 0.9})
    runtime.dispatch("stir.persist", {})

    with pytest.raises(OrderViolationError) as caught:
        runtime.dispatch("feed.start", {})

    assert caught.value.context["required_phase"] == "stir_confirmed"


def test_feed_close_before_the_gate_opens_is_rejected_as_out_of_order(runtime):
    runtime.dispatch("stir.start", {})
    runtime.dispatch("stir.homogenize", {"level": 0.9})
    runtime.dispatch("stir.persist", {})
    runtime.dispatch("feed.batch", {"batch_id": "B-1", "quantity": 5.0})

    with pytest.raises(OrderViolationError):
        runtime.dispatch("feed.close", {})


def test_full_feed_cycle_advances_every_declared_stage(runtime):
    runtime.dispatch("stir.start", {})
    runtime.dispatch("stir.homogenize", {"level": 0.9})
    runtime.dispatch("stir.persist", {})
    runtime.dispatch("feed.batch", {"batch_id": "B-1", "quantity": 5.0})
    runtime.dispatch("feed.start", {})
    runtime.dispatch("feed.close", {})

    state = runtime.state()
    assert state["lines"]["feed"]["phase"] == "fermenting"
    assert state["subsystems"]["feed"]["open"] is False
    assert runtime.view.current()["feed"]["ferment"]["active"] is True


def test_homogenisation_below_the_floor_is_rejected(runtime):
    runtime.dispatch("stir.start", {})

    with pytest.raises(BelowLimitError) as caught:
        runtime.dispatch("stir.homogenize", {"level": 0.5})

    assert caught.value.context["level"] == 0.5


def test_homogenisation_level_must_be_a_fraction(runtime):
    runtime.dispatch("stir.start", {})

    with pytest.raises(Exception) as caught:
        runtime.dispatch("stir.homogenize", {"level": 1.7})

    assert getattr(caught.value, "code", "") == "validation_error"


def test_heat_ramp_before_the_mixer_runs_is_rejected(runtime):
    with pytest.raises(InterlockBlockedError) as caught:
        runtime.dispatch("heat.ramp", {"target_c": 36.0})

    assert "stir.running" in caught.value.context["missing"]


def test_heat_ramp_above_the_wall_bound_is_rejected(runtime):
    runtime.dispatch("stir.start", {})

    with pytest.raises(OverLimitError) as caught:
        runtime.dispatch("heat.ramp", {"target_c": 60.0})

    assert caught.value.context["limit"] == 42.0


def test_heat_cool_before_a_ramp_is_blocked(runtime):
    runtime.dispatch("stir.start", {})

    with pytest.raises(InterlockBlockedError) as caught:
        runtime.dispatch("heat.cool", {})

    assert "heat.running" in caught.value.context["missing"]


def test_heat_cool_ends_an_active_ramp(runtime):
    runtime.dispatch("stir.start", {})
    runtime.dispatch("heat.ramp", {"target_c": 36.0})

    runtime.dispatch("heat.cool", {})

    assert runtime.state()["subsystems"]["heat"]["ramping"] is False


def test_heat_status_reports_the_target_band_and_bound(runtime):
    runtime.dispatch("stir.start", {})
    runtime.dispatch("heat.ramp", {"target_c": 36.0})

    heat = runtime.state()["subsystems"]["heat"]

    assert heat["ramping"] is True
    assert heat["target_c"] == 36.0
    assert heat["band_c"] == 1.5
    assert heat["limit_c"] == 42.0
    assert heat["wall"] is None


def test_heat_ramp_target_at_the_wall_bound_is_accepted(runtime):
    runtime.dispatch("stir.start", {})

    runtime.dispatch("heat.ramp", {"target_c": 42.0})

    assert runtime.state()["subsystems"]["heat"]["ramping"] is True


def test_wall_reading_below_the_target_raises_an_alarm(runtime):
    runtime.dispatch("stir.start", {})
    runtime.dispatch("heat.ramp", {"target_c": 36.0})

    result = runtime.dispatch("heat.wall", {"temperature_c": 30.0})

    wall = result["result"]["wall"]
    assert wall["ok"] is False
    assert wall["code"] == "below_target"
    assert wall["target_c"] == 36.0
    alarm = runtime.alarms.recent()[-1]
    assert alarm["name"] == "heat.wall.below_target"


def test_wall_reading_on_target_is_ok(runtime):
    runtime.dispatch("stir.start", {})
    runtime.dispatch("heat.ramp", {"target_c": 36.0})

    result = runtime.dispatch("heat.wall", {"temperature_c": 36.0})

    assert result["result"]["wall"]["ok"] is True
    assert result["result"]["wall"]["code"] == "ok"
    assert runtime.alarms.count() == 0


def test_wall_reading_is_visible_in_the_heat_status(runtime):
    runtime.dispatch("stir.start", {})
    runtime.dispatch("heat.ramp", {"target_c": 36.0})
    runtime.dispatch("heat.wall", {"temperature_c": 35.5})

    heat = runtime.state()["subsystems"]["heat"]

    assert heat["wall"]["temperature_c"] == 35.5
    assert heat["wall"]["target_c"] == 36.0


def test_wall_reading_without_an_active_ramp_is_rejected(runtime):
    runtime.dispatch("stir.start", {})

    with pytest.raises(NotFoundError):
        runtime.dispatch("heat.wall", {"temperature_c": 30.0})


def test_wall_reading_after_cooling_is_rejected(runtime):
    runtime.dispatch("stir.start", {})
    runtime.dispatch("heat.ramp", {"target_c": 36.0})
    runtime.dispatch("heat.cool", {})

    with pytest.raises(NotFoundError):
        runtime.dispatch("heat.wall", {"temperature_c": 30.0})


def test_stopping_the_mixer_while_the_gate_is_open_is_blocked(runtime):
    runtime.dispatch("stir.start", {})
    runtime.dispatch("stir.homogenize", {"level": 0.9})
    runtime.dispatch("stir.persist", {})
    runtime.dispatch("feed.batch", {"batch_id": "B-1", "quantity": 5.0})
    runtime.dispatch("feed.start", {})

    with pytest.raises(InterlockBlockedError) as caught:
        runtime.dispatch("stir.stop", {})

    assert "feed.open" in caught.value.context["missing"]


def test_stopping_a_mixer_that_never_ran_is_blocked(runtime):
    with pytest.raises(InterlockBlockedError):
        runtime.dispatch("stir.stop", {})


def test_persisting_the_mix_bumps_the_generation(runtime):
    runtime.dispatch("stir.start", {})
    runtime.dispatch("stir.homogenize", {"level": 0.9})

    runtime.dispatch("stir.persist", {})

    assert runtime.versions.current_generation("stir") == 1
    assert runtime.view.current()["stir"]["persisted"]["mix_level"] == 0.9


def test_persisting_without_a_recorded_mix_is_rejected(runtime):
    runtime.dispatch("stir.start", {})

    with pytest.raises(Exception) as caught:
        runtime.dispatch("stir.persist", {})

    assert getattr(caught.value, "code", "") == "not_found"


def test_declaring_a_batch_above_the_cycle_bound_is_rejected(runtime):
    runtime.dispatch("stir.start", {})
    runtime.dispatch("stir.homogenize", {"level": 0.9})
    runtime.dispatch("stir.persist", {})

    with pytest.raises(OverLimitError):
        runtime.dispatch("feed.batch", {"batch_id": "B-9", "quantity": 90.0})


def test_repeating_a_batch_identifier_is_rejected(runtime):
    runtime.dispatch("stir.start", {})
    runtime.dispatch("stir.homogenize", {"level": 0.9})
    runtime.dispatch("stir.persist", {})
    runtime.dispatch("feed.batch", {"batch_id": "B-1", "quantity": 5.0})

    with pytest.raises(Exception) as caught:
        runtime.dispatch("feed.batch", {"batch_id": "B-1", "quantity": 6.0})

    assert getattr(caught.value, "code", "") == "duplicate"
