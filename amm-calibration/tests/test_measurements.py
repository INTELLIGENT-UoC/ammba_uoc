"""Tests for aggregating int:Measurement records into market slots."""

from src.calibrate import calibrate
from src.measurements import aggregate_slots


def _meas(slot, area, energy, community="c1"):
    return {
        "facilityId": area,
        "communityUuid": community,
        "timeSlot": slot,
        "creationTime": 0,
        "energyKwh": energy,
    }


def test_net_load_sign_convention():
    # Default: positive = consumption (demand), negative = injection (supply).
    measurements = [
        _meas("t1", "a", 5.0),  # demand 5
        _meas("t1", "b", -3.0),  # supply 3
        _meas("t1", "c", -2.0),  # supply 2
    ]
    slots = aggregate_slots(measurements, k_upper=28.5, k_lower=8.0)
    assert len(slots) == 1
    assert slots[0].total_demand == 5.0
    assert slots[0].total_supply == 5.0


def test_sign_flip():
    measurements = [_meas("t1", "a", 5.0), _meas("t1", "b", -3.0)]
    slots = aggregate_slots(measurements, k_upper=28.5, k_lower=8.0, positive_is_consumption=False)
    # Flipped: positive is injection now.
    assert slots[0].total_supply == 5.0
    assert slots[0].total_demand == 3.0


def test_community_filter():
    measurements = [
        _meas("t1", "a", 5.0, community="c1"),
        _meas("t1", "b", -4.0, community="c2"),
    ]
    slots = aggregate_slots(measurements, k_upper=28.5, k_lower=8.0, community_uuid="c1")
    assert slots[0].total_demand == 5.0
    assert slots[0].total_supply == 0.0


def test_calibrate_end_to_end():
    # Several slots across two time steps with both supply and demand.
    measurements = [
        _meas("t1", "a", 10.0),
        _meas("t1", "b", -2.0),
        _meas("t2", "a", 10.0),
        _meas("t2", "b", -20.0),
    ]
    params = calibrate(measurements, k_upper=28.5, k_lower=8.0, community_uuid="c1")
    assert 0.0 <= params["theta"] <= 50.0
    assert 0.0 <= params["steepness"] <= 50.0
    assert params["n_slots"] == 2
