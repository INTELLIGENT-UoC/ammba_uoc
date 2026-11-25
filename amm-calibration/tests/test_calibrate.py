"""Tests for the calibration CLI and its configuration snippet."""

import json

import yaml
from src.calibrate import main, to_config_snippet

COMMUNITY = "11111111-1111-4111-8111-111111111111"


def _meas(slot, area, energy):
    return {
        "facilityId": area,
        "communityUuid": COMMUNITY,
        "timeSlot": slot,
        "creationTime": 0,
        "energyKwh": energy,
    }


def test_config_snippet_has_only_the_community_parameters():
    snippet = to_config_snippet(COMMUNITY, 28.5, 8.0, {"theta": 1.0, "steepness": 2.5})
    assert snippet == {
        "communities": {
            COMMUNITY: {
                "k_upper_ct_per_kwh": 28.5,
                "k_lower_ct_per_kwh": 8.0,
                "theta": 1.0,
                "steepness": 2.5,
            }
        }
    }


def test_main_writes_the_snippet(tmp_path):
    # Scarce, balanced and abundant slots (positive = consumption).
    measurements = [
        _meas("t1", "a", 10.0),
        _meas("t1", "b", -2.0),
        _meas("t2", "a", 10.0),
        _meas("t2", "b", -10.0),
        _meas("t3", "a", 10.0),
        _meas("t3", "b", -20.0),
    ]
    history = tmp_path / "history.json"
    history.write_text(json.dumps(measurements))
    out = tmp_path / "params.yaml"

    argv = ["--measurements", str(history), "--community", COMMUNITY]
    argv += ["--k-upper", "28.5", "--k-lower", "8.0", "--out", str(out)]
    assert main(argv) == 0

    entry = yaml.safe_load(out.read_text())["communities"][COMMUNITY]
    assert set(entry) == {"k_upper_ct_per_kwh", "k_lower_ct_per_kwh", "theta", "steepness"}
