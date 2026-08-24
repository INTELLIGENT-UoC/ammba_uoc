"""Penalty calculation module.

Implements the three penalty types from IMPLEMENTATION_GUIDE.md Section 5.3,
matching the reference implementation in simulation.py.

Penalty types:
1. Seller Shortfall Penalty — seller delivered less than traded
2. Seller Externality Penalty — seller withheld supply (VCG, supply-limited rounds)
3. Buyer Externality Penalty — buyer underreported demand (VCG, demand-limited rounds)
"""

import logging
import math

from src.sigmoid import sigmoid_price

logger = logging.getLogger(__name__)


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


def compute_penalties_for_trades(
    trades: list[dict],
    measurements: dict[str, float],
    community_config: dict,
    gamma: float = 1.1,
    eta: float = 0.0,
) -> list[dict]:
    """Compute penalties for all trades in a market slot.

    Args:
        trades: List of settled trade objects from off-chain DB.
        measurements: Mapping of area_uuid -> actual energy delivered/consumed (kWh).
            Positive = energy injected (sellers), negative or absolute = energy consumed (buyers).
        community_config: Dict with k_upper, k_lower, theta, steepness.
        gamma: Shortfall penalty multiplier.
        eta: Tolerance threshold (kWh).

    Returns:
        List of penalty result dicts, one per trade.
    """
    if not trades:
        return []

    # Extract clearing parameters from first trade's parameters field
    first_params = trades[0].get("parameters", {})
    total_supply = first_params.get("total_supply_kwh", 0)
    total_demand = first_params.get("total_demand_kwh", 0)
    clearing_price = first_params.get("energy_rate", 0)
    theta = first_params.get("theta", community_config.get("theta", 1.0))
    steepness = first_params.get("steepness", community_config.get("steepness", 2.5))
    k_upper = community_config["k_upper"]
    k_lower = community_config["k_lower"]

    traded_quantity = min(total_supply, total_demand)
    is_supply_limited = math.isclose(traded_quantity, total_supply, rel_tol=1e-9)
    is_demand_limited = math.isclose(traded_quantity, total_demand, rel_tol=1e-9)

    results = []

    for trade in trades:
        params = trade.get("parameters", {})
        selected_energy = params.get("selected_energy", 0)
        trade_uuid = trade.get("trade_uuid", "")

        # Determine if this is a seller or buyer trade relative to the pool
        # Pool→Seller trade: trade["buyer"] contains pool_id
        # Buyer→Pool trade: trade["seller"] contains pool_id
        is_seller_trade = "AMM_POOL" in trade.get("buyer", "")
        is_buyer_trade = "AMM_POOL" in trade.get("seller", "")

        penalty_result = {
            "trade_uuid": trade_uuid,
            "seller_shortfall_penalty": 0.0,
            "seller_externality_penalty": 0.0,
            "buyer_externality_penalty": 0.0,
            "total_penalty": 0.0,
        }

        if is_seller_trade:
            # This is a Pool→Seller trade
            area_uuid = trade.get("offer", {}).get("offer_component", {}).get("area_uuid", "")
            actual_delivered = measurements.get(area_uuid, selected_energy)

            # 1. Seller Shortfall Penalty
            shortfall_penalty = compute_seller_shortfall_penalty(
                energy_traded=selected_energy,
                actual_delivered=actual_delivered,
                k_upper=k_upper,
                gamma=gamma,
                eta=eta,
            )
            penalty_result["seller_shortfall_penalty"] = shortfall_penalty

            # 2. Seller Externality Penalty (only in supply-limited rounds)
            if is_supply_limited:
                ext_penalty = compute_seller_externality_penalty(
                    actual_deliverable=actual_delivered,
                    energy_traded=selected_energy,
                    total_supply=total_supply,
                    total_demand=total_demand,
                    clearing_price=clearing_price,
                    traded_quantity=traded_quantity,
                    k_upper=k_upper,
                    k_lower=k_lower,
                    theta=theta,
                    steepness=steepness,
                    eta=eta,
                )
                penalty_result["seller_externality_penalty"] = ext_penalty

        elif is_buyer_trade:
            # This is a Buyer→Pool trade
            area_uuid = trade.get("bid", {}).get("bid_component", {}).get("area_uuid", "")
            actual_demand = measurements.get(area_uuid, selected_energy)
            reported_demand = selected_energy

            # 3. Buyer Externality Penalty (only in demand-limited rounds)
            if is_demand_limited:
                ext_penalty = compute_buyer_externality_penalty(
                    actual_demand=actual_demand,
                    reported_demand=reported_demand,
                    total_supply=total_supply,
                    total_demand=total_demand,
                    clearing_price=clearing_price,
                    traded_quantity=traded_quantity,
                    k_upper=k_upper,
                    k_lower=k_lower,
                    theta=theta,
                    steepness=steepness,
                )
                penalty_result["buyer_externality_penalty"] = ext_penalty

        penalty_result["total_penalty"] = (
            penalty_result["seller_shortfall_penalty"]
            + penalty_result["seller_externality_penalty"]
            + penalty_result["buyer_externality_penalty"]
        )

        results.append(penalty_result)

    return results
