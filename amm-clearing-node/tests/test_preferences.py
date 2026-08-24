"""Tests for user preference matching."""

from src.preferences import (
    EnergyTypeMultipliers,
    apply_preference_allocation,
    apply_priority_allocation,
    compute_seller_price_adjustments,
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


class TestSellerPriceAdjustments:
    def _offer(self, account, allocated, energy_type=None):
        offer = {
            "order_id": f"offer_{account}",
            "created_by": account,
            "allocated_energy": allocated,
        }
        if energy_type:
            offer["attributes"] = {"energy_type": [energy_type]}
        return offer

    def test_green_subsidy_and_grey_levy(self):
        """Equal volumes, 10%/10% at price 50 -> green +5, grey -5, zero-sum."""
        offers = [
            self._offer("GreenSeller", 10.0, "PV"),
            self._offer("GreySeller", 10.0, "GREY"),
        ]
        m = EnergyTypeMultipliers(green_subsidy_rate=0.10, grey_levy_rate=0.10)
        adjusted, prov = compute_seller_price_adjustments(offers, 50.0, m)

        assert adjusted["offer_GreenSeller"] == 55.0
        assert adjusted["offer_GreySeller"] == 45.0
        assert prov["scheme"] == "seller_side_zero_sum"
        assert prov["subsidy_total_ct"] <= prov["levy_revenue_ct"] + 1e-9
        assert abs(prov["pool_residual_ct"]) < 1e-9

    def test_levy_cap_enforced_and_subsidy_scaled_to_revenue(self):
        """Cap bounds the levy; the subsidy shrinks to what the levy funds."""
        offers = [
            self._offer("GreenSeller", 10.0, "GREEN"),
            self._offer("GreySeller", 10.0, "GREY"),
        ]
        m = EnergyTypeMultipliers(
            green_subsidy_rate=0.20,  # target 20 ct/kWh at price 100
            grey_levy_rate=0.20,  # would be 20 ct/kWh
            levy_cap_ct_per_kwh=5.0,  # capped at 5
        )
        adjusted, prov = compute_seller_price_adjustments(offers, 100.0, m)

        assert adjusted["offer_GreySeller"] == 95.0  # levy capped
        # Revenue 5*10=50 funds subsidy 50/10 = 5 ct/kWh (scaled from 20).
        assert abs(adjusted["offer_GreenSeller"] - 105.0) < 1e-9
        assert abs(prov["scaling_factor"] - 0.25) < 1e-9
        assert prov["subsidy_total_ct"] <= prov["levy_revenue_ct"] + 1e-9

    def test_dynamic_subsidy_scaling(self):
        """Small grey volume -> subsidy scales down to the levy revenue."""
        offers = [
            self._offer("GreenSeller", 10.0, "PV"),
            self._offer("GreySeller", 2.0, "GREY"),
        ]
        m = EnergyTypeMultipliers(
            green_subsidy_rate=0.10, grey_levy_rate=0.10, levy_cap_ct_per_kwh=10.0
        )
        adjusted, prov = compute_seller_price_adjustments(offers, 50.0, m)

        # Revenue 5*2=10 vs target 5*10=50 -> scaling 0.2 -> subsidy 1 ct/kWh.
        assert abs(adjusted["offer_GreenSeller"] - 51.0) < 1e-9
        assert abs(prov["scaling_factor"] - 0.2) < 1e-9

    def test_no_multipliers_or_zero_rates(self):
        offers = [self._offer("S1", 5.0, "PV"), self._offer("S2", 5.0, "GREY")]
        assert compute_seller_price_adjustments(offers, 50.0, None) == ({}, None)
        zero = EnergyTypeMultipliers(green_subsidy_rate=0, grey_levy_rate=0)
        assert compute_seller_price_adjustments(offers, 50.0, zero) == ({}, None)

    def test_missing_side_disables_adjustment(self):
        """Zero-sum needs both a funded and a funding side."""
        m = EnergyTypeMultipliers(green_subsidy_rate=0.10, grey_levy_rate=0.10)
        only_green = [self._offer("S1", 5.0, "PV")]
        assert compute_seller_price_adjustments(only_green, 50.0, m) == ({}, None)
        only_grey = [self._offer("S1", 5.0, "GREY")]
        assert compute_seller_price_adjustments(only_grey, 50.0, m) == ({}, None)

    def test_unallocated_and_neutral_offers_excluded(self):
        offers = [
            self._offer("GreenSeller", 10.0, "PV"),
            self._offer("GreySeller", 10.0, "GREY"),
            self._offer("SpentSeller", 0.0, "GREY"),  # fully preference-matched
            self._offer("NeutralSeller", 10.0),  # no energy type
        ]
        m = EnergyTypeMultipliers(green_subsidy_rate=0.10, grey_levy_rate=0.10)
        adjusted, prov = compute_seller_price_adjustments(offers, 50.0, m)

        assert "offer_SpentSeller" not in adjusted
        assert "offer_NeutralSeller" not in adjusted
        assert prov["grey_volume_kwh"] == 10.0


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
