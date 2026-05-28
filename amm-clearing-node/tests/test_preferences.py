"""Tests for user preference matching."""

import pytest

from src.preferences import (
    EnergyTypeMultipliers,
    apply_energy_type_multipliers,
    apply_preference_allocation,
    apply_priority_allocation,
    find_mutual_preferred_pairs,
)


def make_bid(account, energy, partners=None, energy_source=None, area="area1"):
    bid = {
        "order_id": f"0xbid_{account}",
        "status": "Open",
        "order_type": "Bid",
        "created_by": account,
        "area_uuid": area,
        "market_id": "m1",
        "time_slot": 100000,
        "creation_time": 99000,
        "energy": energy,
        "energy_rate": 25.0,
        "allocated_energy": energy,
    }
    if partners or energy_source:
        reqs = {}
        if partners:
            reqs["trading_partner_id"] = partners
        if energy_source:
            reqs["energy_source"] = energy_source
        bid["requirements"] = reqs
    return bid


def make_offer(account, energy, partners=None, energy_type=None, area="area2"):
    offer = {
        "order_id": f"0xoffer_{account}",
        "status": "Open",
        "order_type": "Offer",
        "created_by": account,
        "area_uuid": area,
        "market_id": "m1",
        "time_slot": 100000,
        "creation_time": 99000,
        "energy": energy,
        "energy_rate": 5.0,
        "allocated_energy": energy,
    }
    if partners or energy_type:
        if partners:
            offer["requirements"] = {"trading_partner_id": partners}
        if energy_type:
            offer["attributes"] = {"energy_type": energy_type}
    return offer


class TestFindMutualPreferredPairs:
    def test_mutual_match(self):
        """Buyer lists Seller and Seller lists Buyer → mutual pair."""
        bids = [make_bid("Buyer1", 5.0, partners=["Seller1"])]
        offers = [make_offer("Seller1", 5.0, partners=["Buyer1"])]
        pairs = find_mutual_preferred_pairs(bids, offers)
        assert len(pairs) == 1
        assert pairs[0][0]["created_by"] == "Buyer1"
        assert pairs[0][1]["created_by"] == "Seller1"

    def test_one_sided_no_match(self):
        """Buyer lists Seller but Seller doesn't list Buyer → no match."""
        bids = [make_bid("Buyer1", 5.0, partners=["Seller1"])]
        offers = [make_offer("Seller1", 5.0)]
        pairs = find_mutual_preferred_pairs(bids, offers)
        assert len(pairs) == 0

    def test_no_preferences(self):
        """No preferences → no matches."""
        bids = [make_bid("Buyer1", 5.0)]
        offers = [make_offer("Seller1", 5.0)]
        pairs = find_mutual_preferred_pairs(bids, offers)
        assert len(pairs) == 0

    def test_multiple_mutual_pairs(self):
        """Multiple mutual pairs identified."""
        bids = [
            make_bid("B1", 3.0, partners=["S1"]),
            make_bid("B2", 4.0, partners=["S2"]),
        ]
        offers = [
            make_offer("S1", 3.0, partners=["B1"]),
            make_offer("S2", 4.0, partners=["B2"]),
        ]
        pairs = find_mutual_preferred_pairs(bids, offers)
        assert len(pairs) == 2


class TestApplyPriorityAllocation:
    def test_mutual_pair_priority(self):
        """Mutual pair gets volume allocated first."""
        bids = [make_bid("B1", 5.0, partners=["S1"])]
        offers = [make_offer("S1", 5.0, partners=["B1"])]

        bids, offers, matches = apply_priority_allocation(
            bids, offers, clearing_price=18.0, traded_quantity=5.0
        )

        assert len(matches) == 1
        assert matches[0]["energy"] == 5.0
        assert matches[0]["buyer"] == "B1"
        assert matches[0]["seller"] == "S1"
        # Pool allocation should be zero after preference match
        assert bids[0]["allocated_energy"] == 0.0
        assert offers[0]["allocated_energy"] == 0.0

    def test_partial_preference_match(self):
        """When bid/offer sizes differ, match to minimum."""
        bids = [make_bid("B1", 8.0, partners=["S1"])]
        offers = [make_offer("S1", 3.0, partners=["B1"])]

        bids, offers, matches = apply_priority_allocation(
            bids, offers, clearing_price=18.0, traded_quantity=3.0
        )

        assert matches[0]["energy"] == 3.0
        assert bids[0]["allocated_energy"] == 5.0  # 8 - 3 remains for pool
        assert offers[0]["allocated_energy"] == 0.0

    def test_no_preferences_returns_empty(self):
        """No preferences → no matches, allocations unchanged."""
        bids = [make_bid("B1", 5.0)]
        offers = [make_offer("S1", 5.0)]

        bids, offers, matches = apply_priority_allocation(
            bids, offers, clearing_price=18.0, traded_quantity=5.0
        )

        assert len(matches) == 0
        assert bids[0]["allocated_energy"] == 5.0
        assert offers[0]["allocated_energy"] == 5.0


class TestApplyEnergyTypeMultipliers:
    def _make_trade(self, buyer, seller, energy, clearing_price=50.0):
        return {
            "buyer": buyer,
            "seller": seller,
            "parameters": {
                "selected_energy": energy,
                "energy_rate": clearing_price,
            },
        }

    def test_green_subsidy_applied(self):
        """Green sellers get higher price."""
        trades = [
            self._make_trade("AMM_POOL", "GreenSeller", 10.0),
            self._make_trade("AMM_POOL", "GreySeller", 10.0),
        ]
        offers = [
            make_offer("GreenSeller", 10.0, energy_type=["PV"]),
            make_offer("GreySeller", 10.0, energy_type=["GREY"]),
        ]
        bids = [make_bid("B1", 20.0)]
        multipliers = EnergyTypeMultipliers(
            green_subsidy_rate=0.10, grey_levy_rate=0.10, levy_cap_ct_per_kwh=10.0
        )

        result = apply_energy_type_multipliers(
            trades, bids, offers, 50.0, multipliers
        )

        green_trade = [t for t in result if t["seller"] == "GreenSeller"][0]
        grey_trade = [t for t in result if t["seller"] == "GreySeller"][0]

        # Green gets +5 ct/kWh (10% of 50)
        assert green_trade["parameters"]["energy_rate"] == 55.0
        # Grey gets -5 ct/kWh (10% of 50)
        assert grey_trade["parameters"]["energy_rate"] == 45.0

    def test_levy_cap_enforced(self):
        """Grey levy doesn't exceed levy cap."""
        trades = [
            self._make_trade("AMM_POOL", "GreenSeller", 10.0, clearing_price=100.0),
            self._make_trade("AMM_POOL", "GreySeller", 10.0, clearing_price=100.0),
        ]
        offers = [
            make_offer("GreenSeller", 10.0, energy_type=["GREEN"]),
            make_offer("GreySeller", 10.0, energy_type=["GREY"]),
        ]
        bids = [make_bid("B1", 20.0)]
        multipliers = EnergyTypeMultipliers(
            green_subsidy_rate=0.20,  # Would be 20 ct/kWh
            grey_levy_rate=0.20,      # Would be 20 ct/kWh
            levy_cap_ct_per_kwh=5.0,  # Cap at 5 ct/kWh
        )

        result = apply_energy_type_multipliers(
            trades, bids, offers, 100.0, multipliers
        )

        grey_trade = [t for t in result if t["seller"] == "GreySeller"][0]
        # Levy capped at 5 ct/kWh despite rate suggesting 20
        assert grey_trade["parameters"]["energy_rate"] == 95.0

    def test_dynamic_subsidy_scaling(self):
        """When grey revenue < target subsidy, green subsidy scales down."""
        # Small grey volume (2 kWh) vs large green volume (10 kWh)
        trades = [
            self._make_trade("AMM_POOL", "GreenSeller", 10.0, clearing_price=50.0),
            self._make_trade("AMM_POOL", "GreySeller", 2.0, clearing_price=50.0),
        ]
        offers = [
            make_offer("GreenSeller", 10.0, energy_type=["PV"]),
            make_offer("GreySeller", 2.0, energy_type=["GREY"]),
        ]
        bids = [make_bid("B1", 12.0)]
        multipliers = EnergyTypeMultipliers(
            green_subsidy_rate=0.10,    # Target: 5 ct/kWh * 10 kWh = 50 ct total
            grey_levy_rate=0.10,        # Grey levy: 5 ct/kWh * 2 kWh = 10 ct total
            levy_cap_ct_per_kwh=10.0,
        )

        result = apply_energy_type_multipliers(
            trades, bids, offers, 50.0, multipliers
        )

        green_trade = [t for t in result if t["seller"] == "GreenSeller"][0]
        # Grey revenue = 5 * 2 = 10, target subsidy = 5 * 10 = 50
        # Scaling factor = 10/50 = 0.2, actual subsidy = 5 * 0.2 = 1.0 ct/kWh
        assert abs(green_trade["parameters"]["energy_rate"] - 51.0) < 0.01

    def test_no_multipliers_returns_unchanged(self):
        """None multipliers returns trades unchanged."""
        trades = [self._make_trade("AMM_POOL", "S1", 5.0)]
        result = apply_energy_type_multipliers(
            trades, [], [], 50.0, None
        )
        assert result[0]["parameters"]["energy_rate"] == 50.0

    def test_zero_rates_returns_unchanged(self):
        """Zero rates returns trades unchanged."""
        trades = [self._make_trade("AMM_POOL", "S1", 5.0)]
        m = EnergyTypeMultipliers(green_subsidy_rate=0, grey_levy_rate=0)
        result = apply_energy_type_multipliers(
            trades, [], [], 50.0, m
        )
        assert result[0]["parameters"]["energy_rate"] == 50.0


class TestPreferenceAllocationIntegration:
    """Integration tests combining preferences with clearing."""

    def test_full_flow_with_preferences(self):
        """Full preference allocation with mutual pairs."""
        bids = [
            make_bid("B1", 5.0, partners=["S1"]),
            make_bid("B2", 5.0),
        ]
        offers = [
            make_offer("S1", 5.0, partners=["B1"]),
            make_offer("S2", 5.0),
        ]

        bids, offers = apply_preference_allocation(
            bids, offers, clearing_price=18.0, traded_quantity=10.0
        )

        # B1↔S1 preference matched: allocated_energy should be reduced
        assert bids[0]["allocated_energy"] == 0.0  # B1 fully matched with S1
        assert offers[0]["allocated_energy"] == 0.0  # S1 fully matched with B1
        # B2 and S2 remain unchanged (no preferences)
        assert bids[1]["allocated_energy"] == 5.0
        assert offers[1]["allocated_energy"] == 5.0

        # Check preference matches stored
        assert len(bids[0].get("_preference_matches", [])) == 1
