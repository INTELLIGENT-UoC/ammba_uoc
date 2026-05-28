"""Sigmoid price function — shared with clearing node.

Used by the execution node for counterfactual "what-if" price calculations
in VCG externality penalty formulas.
"""

import math


def sigmoid_price(
    ratio: float,
    k_upper: float,
    k_lower: float,
    theta: float,
    steepness: float,
) -> float:
    """Compute the AMMBA clearing price via the sigmoid function.

    price = K_upper - (K_upper - K_lower) / (1 + exp(-B * (ratio - θ)))
    """
    if k_upper <= k_lower:
        return k_lower

    exponent = -steepness * (ratio - theta)
    if exponent > 500:
        denominator = float("inf")
    elif exponent < -500:
        denominator = 1.0
    else:
        denominator = 1 + math.exp(exponent)

    if denominator == 0:
        return k_lower

    price = k_upper - (k_upper - k_lower) / denominator
    return max(k_lower, min(k_upper, price))
