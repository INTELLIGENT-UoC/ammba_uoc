"""Penalty calculation module.

Implements the three penalty types of Saber et al., Applied Energy 416 (2026)
127957, Section 2.4, in the order-based form. Reference implementation:
simulation.py in https://github.com/INTELLIGENT-UoC/ammba_simulation.

Penalty types:
1. Seller Shortfall Penalty — seller delivered less than traded
2. Seller Externality Penalty — seller withheld supply (VCG, supply-limited rounds)
3. Buyer Externality Penalty — buyer underreported demand (VCG, demand-limited rounds)

Only the pure formulas live here. Applying them to a market's ``int:Trade``
objects and metered deliveries is tracked in issue #33.
"""

from src.sigmoid import sigmoid_price


def compute_seller_shortfall_penalty(
    energy_traded: float,
    actual_delivered: float,
    k_upper: float,
    gamma: float,
    eta: float,
) -> float:
    """Seller Shortfall Penalty (Φ_t,j).

    Applied when actual delivery < traded quantity.

    Φ_t,j = K_sho * max(0, energy_traded_j - actual_delivered_j - η)
    K_sho = γ * K_upper
    """
    k_sho = gamma * k_upper
    shortfall = energy_traded - actual_delivered - eta
    return k_sho * max(0.0, shortfall)


def compute_seller_externality_penalty(
    actual_deliverable: float,
    energy_traded: float,
    total_supply: float,
    total_demand: float,
    clearing_price: float,
    traded_quantity: float,
    k_upper: float,
    k_lower: float,
    theta: float,
    steepness: float,
    eta: float,
) -> float:
    """Seller Externality Penalty (VCG mechanism, supply-limited rounds).

    Applied when a seller withheld supply, raising the price for all buyers.

    W_sell_j = max(0, actual_deliverable_j - energy_traded_j - η)
    counterfactual_supply = total_supply + W_sell_j
    p_counterfactual = sigmoid(counterfactual_supply / total_demand)
    penalty = max(0, (clearing_price - p_counterfactual) * traded_quantity)
    """
    withheld = actual_deliverable - energy_traded - eta
    if withheld <= 0:
        return 0.0

    cf_supply = total_supply + withheld
    cf_ratio = cf_supply / total_demand
    p_cf = sigmoid_price(cf_ratio, k_upper, k_lower, theta, steepness)

    penalty = (clearing_price - p_cf) * traded_quantity
    return max(0.0, penalty)


def compute_buyer_externality_penalty(
    actual_demand: float,
    reported_demand: float,
    total_supply: float,
    total_demand: float,
    clearing_price: float,
    traded_quantity: float,
    k_upper: float,
    k_lower: float,
    theta: float,
    steepness: float,
) -> float:
    """Buyer Externality Penalty (VCG mechanism, demand-limited rounds).

    Applied when a buyer underreported demand, reducing the price for all sellers.

    W_buy_i = max(0, actual_demand_i - reported_demand_i)
    counterfactual_demand = total_demand + W_buy_i
    p_counterfactual = sigmoid(total_supply / counterfactual_demand)
    penalty = max(0, (p_counterfactual - clearing_price) * traded_quantity)
    """
    withheld = actual_demand - reported_demand
    if withheld <= 0:
        return 0.0

    cf_demand = total_demand + withheld
    cf_ratio = total_supply / cf_demand
    p_cf = sigmoid_price(cf_ratio, k_upper, k_lower, theta, steepness)

    penalty = (p_cf - clearing_price) * traded_quantity
    return max(0.0, penalty)
