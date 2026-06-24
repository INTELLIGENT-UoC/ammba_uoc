"""Sigmoid price function used by the calibration objective.

This is the **unclamped** sigmoid, matching the reference research implementation
(`optimize_parameters_ammba` in the AMMBA paper code). It deliberately differs
from the clearing node's `sigmoid.py`, which clamps the result to
``[k_lower, k_upper]`` for runtime safety:

- The clearing node clamps so a bad parameter set can never produce an
  out-of-band price at runtime.
- Calibration must NOT clamp, because the objective's boundary term measures how
  fully the sigmoid spans ``[k_lower, k_upper]`` across the observed ratio range.
  With a clamped price that signal would be lost.

The output of this function is always within ``(k_lower, k_upper)`` anyway (the
sigmoid denominator is in ``(1, inf)``); the point is that the *shape* — how
close it gets to each bound at the ratio extremes — is what calibration tunes.

NOTE: keep the core formula in sync with `amm-clearing-node/src/sigmoid.py`.
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
