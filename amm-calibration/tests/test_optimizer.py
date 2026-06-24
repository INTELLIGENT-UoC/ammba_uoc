"""Tests for the calibration objective and grid-search optimizer."""

from src.optimizer import DEFAULT_BOUNDS, Slot, objective, optimize_params


def _slots():
    # A spread of supply/demand ratios with fixed price bounds.
    return [
        Slot(total_supply=2.0, total_demand=10.0, k_upper=28.5, k_lower=8.0),  # scarce
        Slot(total_supply=10.0, total_demand=10.0, k_upper=28.5, k_lower=8.0),  # balanced
        Slot(total_supply=20.0, total_demand=10.0, k_upper=28.5, k_lower=8.0),  # abundant
    ]


def test_objective_is_finite():
    assert isinstance(objective(_slots(), 1.0, 2.5, 0.5), float)


def test_objective_skips_unusable_slots():
    # No supply or k_upper<=k_lower -> ignored, objective falls back to 0.
    bad = [
        Slot(total_supply=0.0, total_demand=5.0, k_upper=28.5, k_lower=8.0),
        Slot(total_supply=5.0, total_demand=5.0, k_upper=8.0, k_lower=8.0),
    ]
    assert objective(bad, 1.0, 2.5, 0.5) == 0.0


def test_optimizer_within_bounds_and_deterministic():
    r1 = optimize_params(_slots(), alpha=0.5)
    r2 = optimize_params(_slots(), alpha=0.5)
    assert r1 == r2  # deterministic
    (tlo, thi), (blo, bhi) = DEFAULT_BOUNDS
    assert tlo <= r1["theta"] <= thi
    assert blo <= r1["steepness"] <= bhi
    assert r1["n_slots"] == 3


def test_optimizer_beats_the_reference_start_point():
    """Optimised params should be at least as good as the paper's x0=[1,1]."""
    slots = _slots()
    result = optimize_params(slots, alpha=0.5)
    best = objective(slots, result["theta"], result["steepness"], 0.5)
    start = objective(slots, 1.0, 1.0, 0.5)
    assert best <= start + 1e-9
