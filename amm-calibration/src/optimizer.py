"""Parameter optimization — port of `optimize_parameters_ammba` from the paper.

Given a history of market slots (each with aggregate supply, demand, and the
community's price bounds), find the sigmoid ``(theta, steepness)`` that:

1. **maximizes the worst-off average return** across slots — i.e. maximizes
   ``mean over slots of min(buyer_utility, seller_profit)`` where
   ``buyer_utility = k_upper - price`` and ``seller_profit = price - k_lower``;
2. subject to a **range-usage penalty** (weight ``alpha``) that pushes the price
   toward ``k_lower`` at the highest observed supply/demand ratio and toward
   ``k_upper`` at the lowest, so the sigmoid actually uses the full price band.

The objective value (to MINIMISE) is
``-mean(min_returns) + alpha * (range-usage penalty)``.

The reference code used ``scipy.optimize.minimize``. We use a dependency-free
coarse-to-fine grid search instead — the parameter space is 2-D, bounded, and
the objective is cheap, so this is robust, deterministic, and adds no heavy
dependency (matching this repo's dependency-hygiene stance). Swap in scipy only
if you need sub-grid precision.
"""

from dataclasses import dataclass

from src.pricing import sigmoid_price_unclamped

DEFAULT_BOUNDS = ((0.0, 50.0), (0.0, 50.0))  # (theta, steepness), as in the paper
DEFAULT_ALPHA = 0.5


@dataclass(frozen=True)
class Slot:
    """Aggregate state of one historical market slot."""

    total_supply: float  # kWh available (production surplus)
    total_demand: float  # kWh demanded (consumption)
    k_upper: float  # retail buy price bound
    k_lower: float  # feed-in tariff bound


def _valid(slots: list[Slot]) -> list[tuple[float, Slot]]:
    """Keep slots that can trade, paired with their supply/demand ratio."""
    out = []
    for s in slots:
        if s.k_upper <= s.k_lower or s.total_supply <= 0 or s.total_demand <= 0:
            continue
        out.append((s.total_supply / s.total_demand, s))
    return out


def objective(slots: list[Slot], theta: float, steepness: float, alpha: float) -> float:
    """Objective to minimise (see module docstring)."""
    valid = _valid(slots)
    if not valid:
        return 0.0

    min_returns = []
    for ratio, s in valid:
        price = sigmoid_price_unclamped(ratio, s.k_upper, s.k_lower, theta, steepness)
        buyer_utility = s.k_upper - price
        seller_profit = price - s.k_lower
        min_returns.append(min(buyer_utility, seller_profit))

    # Range-usage penalty, evaluated at the ratio extremes (paper convention:
    # both use the price bounds of the minimum-ratio slot).
    r_min, s_rmin = min(valid, key=lambda x: x[0])
    r_max = max(r for r, _ in valid)
    price_at_rmax = sigmoid_price_unclamped(r_max, s_rmin.k_upper, s_rmin.k_lower, theta, steepness)
    price_at_rmin = sigmoid_price_unclamped(r_min, s_rmin.k_upper, s_rmin.k_lower, theta, steepness)
    penalty = alpha * max(0.0, price_at_rmax - s_rmin.k_lower) + alpha * max(
        0.0, s_rmin.k_upper - price_at_rmin
    )

    return -(sum(min_returns) / len(min_returns)) + penalty


def _grid_min(slots, alpha, theta_lo, theta_hi, b_lo, b_hi, steps):
    best = None
    for i in range(steps + 1):
        theta = theta_lo + (theta_hi - theta_lo) * i / steps
        for j in range(steps + 1):
            steepness = b_lo + (b_hi - b_lo) * j / steps
            value = objective(slots, theta, steepness, alpha)
            if best is None or value < best[2]:
                best = (theta, steepness, value)
    return best


def optimize_params(
    slots: list[Slot],
    alpha: float = DEFAULT_ALPHA,
    bounds: tuple[tuple[float, float], tuple[float, float]] = DEFAULT_BOUNDS,
) -> dict:
    """Return the calibrated ``{theta, steepness, objective, alpha, n_slots}``."""
    (theta_lo, theta_hi), (b_lo, b_hi) = bounds

    # Coarse pass over the full box, then refine in a window around the best.
    coarse = _grid_min(slots, alpha, theta_lo, theta_hi, b_lo, b_hi, steps=50)
    theta_c, b_c, _ = coarse
    theta_w = (theta_hi - theta_lo) / 50
    b_w = (b_hi - b_lo) / 50
    fine = _grid_min(
        slots,
        alpha,
        max(theta_lo, theta_c - theta_w),
        min(theta_hi, theta_c + theta_w),
        max(b_lo, b_c - b_w),
        min(b_hi, b_c + b_w),
        steps=40,
    )

    theta, steepness, value = fine
    return {
        "theta": round(theta, 4),
        "steepness": round(steepness, 4),
        "objective": value,
        "alpha": alpha,
        "n_slots": len(_valid(slots)),
    }
