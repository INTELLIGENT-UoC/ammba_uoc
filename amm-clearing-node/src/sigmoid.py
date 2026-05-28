"""Sigmoid price function and scaling utilities.

Matches the formula from IMPLEMENTATION_GUIDE.md Section 3.3 and
the reference implementation in simulation.py.
"""

import math

NODE_FLOAT_SCALING_FACTOR = 10000


def to_node_int(float_val: float) -> int:
    """Convert a float to the GSY DEX integer-scaled representation."""
    return int(round(float_val * NODE_FLOAT_SCALING_FACTOR))


def from_node_int(int_val: int) -> float:
    """Convert a GSY DEX integer-scaled value back to float."""
    return int_val / NODE_FLOAT_SCALING_FACTOR


def sigmoid_price(
    ratio: float,
    k_upper: float,
    k_lower: float,
    theta: float,
    steepness: float,
) -> float:
    """Compute the AMMBA clearing price via the sigmoid function.

    price = K_upper - (K_upper - K_lower) / (1 + exp(-B * (ratio - θ)))

    Args:
        ratio: total_supply / total_demand
        k_upper: community retail buy price (ct/kWh)
        k_lower: community feed-in tariff (ct/kWh)
        theta: sigmoid midpoint parameter
        steepness: sigmoid steepness parameter (B)

    Returns:
        Clearing price in ct/kWh, clamped to [k_lower, k_upper].
    """
    if k_upper <= k_lower:
        return k_lower

    exponent = -steepness * (ratio - theta)
    # Guard against overflow in exp()
    if exponent > 500:
        denominator = float("inf")
    elif exponent < -500:
        denominator = 1.0
    else:
        denominator = 1 + math.exp(exponent)

    if denominator == 0:
        return k_lower

    price = k_upper - (k_upper - k_lower) / denominator

    # Clamp to bounds
    return max(k_lower, min(k_upper, price))
