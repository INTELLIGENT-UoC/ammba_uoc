"""Sigmoid price function used by the calibration objective.

This is the **unclamped** sigmoid, matching the reference research implementation
(`optimize_parameters_ammba` in the AMMBA paper code). It deliberately differs
from the clearing node's `sigmoid.py`, which clamps the result to
``[k_lower, k_upper]`` for runtime safety:

- The clearing node clamps so that a numerical edge case can never produce an
  out-of-band price at runtime.
- The output of this function lies within ``(k_lower, k_upper)`` anyway (the
  sigmoid denominator is in ``(1, inf)``), so the clamp would not change the
  objective; calibration tunes the *shape* — how close the price gets to each
  bound at the ratio extremes.

NOTE: keep the core formula in sync with ``amm-clearing-node/src/sigmoid.py``
and ``amm-execution-node/src/sigmoid.py``.
"""

import math


def sigmoid_price_unclamped(
    ratio: float,
    k_upper: float,
    k_lower: float,
    theta: float,
    steepness: float,
) -> float:
    """price = K_upper - (K_upper - K_lower) / (1 + exp(-B * (ratio - theta)))."""
    if k_upper <= k_lower:
        return k_lower

    exponent = -steepness * (ratio - theta)
    if exponent > 700:  # denominator -> inf  =>  price -> k_upper (scarcity)
        return k_upper
    if exponent < -700:  # denominator -> 1    =>  price -> k_lower (abundance)
        return k_lower

    denominator = 1.0 + math.exp(exponent)
    return k_upper - (k_upper - k_lower) / denominator
