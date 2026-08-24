"""Tests for penalty calculation functions.

Cross-validates against the reference implementation in simulation.py.
"""

from src.penalties import (
    compute_buyer_externality_penalty,
    compute_penalties_for_trades,
    compute_seller_externality_penalty,
    compute_seller_shortfall_penalty,
)
from src.sigmoid import sigmoid_price

# Standard test parameters
K_UPPER = 28.5
K_LOWER = 8.0
THETA = 1.0
STEEPNESS = 2.5
GAMMA = 1.1
ETA = 0.0


class TestSellerShortfallPenalty:
    def test_no_shortfall(self):
        """Seller delivered what they traded — no penalty."""
        p = compute_seller_shortfall_penalty(
            energy_traded=5.0,
            actual_delivered=5.0,
            k_upper=K_UPPER,
            gamma=GAMMA,
            eta=ETA,
        )
        assert p == 0.0

    def test_over_delivery(self):
        """Seller delivered more than traded — no penalty."""
        p = compute_seller_shortfall_penalty(
            energy_traded=5.0,
            actual_delivered=7.0,
            k_upper=K_UPPER,
            gamma=GAMMA,
            eta=ETA,
        )
        assert p == 0.0

    def test_shortfall(self):
        """Seller delivered less than traded — penalty applies."""
        p = compute_seller_shortfall_penalty(
            energy_traded=5.0,
            actual_delivered=3.0,
            k_upper=K_UPPER,
            gamma=GAMMA,
            eta=ETA,
        )
        k_sho = GAMMA * K_UPPER  # 1.1 * 28.5 = 31.35
        expected = k_sho * (5.0 - 3.0)  # 31.35 * 2.0 = 62.7
        assert abs(p - expected) < 1e-9

    def test_shortfall_with_tolerance(self):
        """Tolerance (eta) absorbs small deviations."""
        p = compute_seller_shortfall_penalty(
            energy_traded=5.0,
            actual_delivered=4.5,
            k_upper=K_UPPER,
            gamma=GAMMA,
            eta=0.5,
        )
        # shortfall = 5.0 - 4.5 - 0.5 = 0.0 → no penalty
        assert p == 0.0

    def test_shortfall_beyond_tolerance(self):
        """Shortfall exceeding tolerance gets penalized."""
        p = compute_seller_shortfall_penalty(
            energy_traded=5.0,
            actual_delivered=4.0,
            k_upper=K_UPPER,
            gamma=GAMMA,
            eta=0.5,
        )
        k_sho = GAMMA * K_UPPER
        expected = k_sho * (5.0 - 4.0 - 0.5)  # 31.35 * 0.5
        assert abs(p - expected) < 1e-9


class TestSellerExternalityPenalty:
    def test_no_withholding(self):
        """Seller delivered exactly what they traded — no penalty."""
        p = compute_seller_externality_penalty(
            actual_deliverable=5.0,
            energy_traded=5.0,
            total_supply=10.0,
            total_demand=10.0,
            clearing_price=18.0,
            traded_quantity=10.0,
            k_upper=K_UPPER,
            k_lower=K_LOWER,
            theta=THETA,
            steepness=STEEPNESS,
            eta=ETA,
        )
        assert p == 0.0

    def test_withholding_raises_price(self):
        """Seller withheld supply → counterfactual price is lower → penalty > 0."""
        total_supply = 8.0
        total_demand = 10.0
        ratio = total_supply / total_demand
        clearing_price = sigmoid_price(ratio, K_UPPER, K_LOWER, THETA, STEEPNESS)
        traded_quantity = min(total_supply, total_demand)  # 8.0

        actual_deliverable = 6.0  # Seller could deliver 6 but only traded 4
        energy_traded = 4.0
        withheld = actual_deliverable - energy_traded  # 2.0

        p = compute_seller_externality_penalty(
            actual_deliverable=actual_deliverable,
            energy_traded=energy_traded,
            total_supply=total_supply,
            total_demand=total_demand,
            clearing_price=clearing_price,
            traded_quantity=traded_quantity,
            k_upper=K_UPPER,
            k_lower=K_LOWER,
            theta=THETA,
            steepness=STEEPNESS,
            eta=ETA,
        )

        # Counterfactual: supply would have been 8 + 2 = 10
        cf_ratio = (total_supply + withheld) / total_demand
        p_cf = sigmoid_price(cf_ratio, K_UPPER, K_LOWER, THETA, STEEPNESS)
        expected = max(0, (clearing_price - p_cf) * traded_quantity)

        assert abs(p - expected) < 1e-9
        assert p > 0  # More supply → lower price → positive penalty

    def test_withholding_within_tolerance(self):
        """Withholding within eta tolerance → no penalty."""
        p = compute_seller_externality_penalty(
            actual_deliverable=5.5,
            energy_traded=5.0,
            total_supply=10.0,
            total_demand=10.0,
            clearing_price=18.0,
            traded_quantity=10.0,
            k_upper=K_UPPER,
            k_lower=K_LOWER,
            theta=THETA,
            steepness=STEEPNESS,
            eta=0.5,
        )
        assert p == 0.0


class TestBuyerExternalityPenalty:
    def test_no_underreporting(self):
        """Buyer reported actual demand — no penalty."""
        p = compute_buyer_externality_penalty(
            actual_demand=5.0,
            reported_demand=5.0,
            total_supply=10.0,
            total_demand=10.0,
            clearing_price=18.0,
            traded_quantity=10.0,
            k_upper=K_UPPER,
            k_lower=K_LOWER,
            theta=THETA,
            steepness=STEEPNESS,
        )
        assert p == 0.0

    def test_underreporting_lowers_price(self):
        """Buyer underreported → counterfactual price is higher → penalty > 0."""
        total_supply = 10.0
        total_demand = 8.0
        ratio = total_supply / total_demand
        clearing_price = sigmoid_price(ratio, K_UPPER, K_LOWER, THETA, STEEPNESS)
        traded_quantity = min(total_supply, total_demand)  # 8.0

        actual_demand = 6.0
        reported_demand = 4.0
        withheld = actual_demand - reported_demand  # 2.0

        p = compute_buyer_externality_penalty(
            actual_demand=actual_demand,
            reported_demand=reported_demand,
            total_supply=total_supply,
            total_demand=total_demand,
            clearing_price=clearing_price,
            traded_quantity=traded_quantity,
            k_upper=K_UPPER,
            k_lower=K_LOWER,
            theta=THETA,
            steepness=STEEPNESS,
        )

        # Counterfactual: demand would have been 8 + 2 = 10
        cf_ratio = total_supply / (total_demand + withheld)
        p_cf = sigmoid_price(cf_ratio, K_UPPER, K_LOWER, THETA, STEEPNESS)
        expected = max(0, (p_cf - clearing_price) * traded_quantity)

        assert abs(p - expected) < 1e-9
        assert p > 0  # More demand → higher price → positive penalty

    def test_overreporting_no_penalty(self):
        """Buyer overreported (actual < reported) → no penalty."""
        p = compute_buyer_externality_penalty(
            actual_demand=3.0,
            reported_demand=5.0,
            total_supply=10.0,
            total_demand=10.0,
            clearing_price=18.0,
            traded_quantity=10.0,
            k_upper=K_UPPER,
            k_lower=K_LOWER,
            theta=THETA,
            steepness=STEEPNESS,
        )
        assert p == 0.0


class TestComputePenaltiesForTrades:
    def _make_trade(
        self,
        buyer,
        seller,
        area_uuid_offer,
        area_uuid_bid,
        selected_energy,
        clearing_price=18.0,
        total_supply=10.0,
        total_demand=10.0,
    ):
        return {
            "trade_uuid": f"trade_{buyer}_{seller}",
            "status": "Settled",
            "buyer": buyer,
            "seller": seller,
            "offer": {
                "seller": seller,
                "offer_component": {"area_uuid": area_uuid_offer},
            },
            "bid": {
                "buyer": buyer,
                "bid_component": {"area_uuid": area_uuid_bid},
            },
            "parameters": {
                "selected_energy": selected_energy,
                "energy_rate": clearing_price,
                "total_supply_kwh": total_supply,
                "total_demand_kwh": total_demand,
                "theta": THETA,
                "steepness": STEEPNESS,
            },
        }

    def test_no_deviations(self):
        """When measurements match trades, no penalties."""
        trades = [
            self._make_trade("AMM_POOL_c1", "Seller1", "area_s1", "AMM_POOL_c1", 5.0),
            self._make_trade("Buyer1", "AMM_POOL_c1", "AMM_POOL_c1", "area_b1", 5.0),
        ]
        measurements = {"area_s1": 5.0, "area_b1": 5.0}
        config = {"k_upper": K_UPPER, "k_lower": K_LOWER, "theta": THETA, "steepness": STEEPNESS}

        results = compute_penalties_for_trades(trades, measurements, config)
        assert len(results) == 2
        assert all(r["total_penalty"] == 0.0 for r in results)

    def test_seller_shortfall_detected(self):
        """Seller delivered less → shortfall penalty."""
        trades = [
            self._make_trade("AMM_POOL_c1", "Seller1", "area_s1", "AMM_POOL_c1", 5.0),
        ]
        measurements = {"area_s1": 3.0}  # Delivered 3, traded 5
        config = {"k_upper": K_UPPER, "k_lower": K_LOWER, "theta": THETA, "steepness": STEEPNESS}

        results = compute_penalties_for_trades(trades, measurements, config)
        assert len(results) == 1
        assert results[0]["seller_shortfall_penalty"] > 0
        expected_shortfall = GAMMA * K_UPPER * 2.0  # K_sho * (5-3)
        assert abs(results[0]["seller_shortfall_penalty"] - expected_shortfall) < 1e-9

    def test_empty_trades(self):
        """Empty trade list returns empty results."""
        results = compute_penalties_for_trades([], {}, {"k_upper": K_UPPER, "k_lower": K_LOWER})
        assert results == []
