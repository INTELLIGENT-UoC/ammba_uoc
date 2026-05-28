"""Tests for trade object construction and blake2b hashing."""

from src.trade_builder import (
    blake2b_hash,
    build_buyer_pool_trade,
    build_pool_seller_trade,
)


class TestBlake2bHash:
    def test_deterministic(self):
        data = {"key": "value", "number": 42}
        h1 = blake2b_hash(data)
        h2 = blake2b_hash(data)
        assert h1 == h2

    def test_starts_with_0x(self):
        h = blake2b_hash({"a": 1})
        assert h.startswith("0x")

    def test_hex_length(self):
        """blake2b-256 = 32 bytes = 64 hex chars + '0x' prefix."""
        h = blake2b_hash({"a": 1})
        assert len(h) == 66  # "0x" + 64 hex chars

    def test_sorted_keys(self):
        """Key order shouldn't matter."""
        h1 = blake2b_hash({"b": 2, "a": 1})
        h2 = blake2b_hash({"a": 1, "b": 2})
        assert h1 == h2

    def test_different_data_different_hash(self):
        h1 = blake2b_hash({"a": 1})
        h2 = blake2b_hash({"a": 2})
        assert h1 != h2


SAMPLE_BID = {
    "order_id": "0xbid123",
    "status": "Open",
    "order_type": "Bid",
    "created_by": "Account1",
    "area_uuid": "areaid_1",
    "market_id": "market1",
    "time_slot": 123123,
    "creation_time": 456456,
    "energy": 0.26,
    "energy_rate": 0.123,
    "allocated_energy": 0.20,
}

SAMPLE_OFFER = {
    "order_id": "0xoffer456",
    "status": "Open",
    "order_type": "Offer",
    "created_by": "Account2",
    "area_uuid": "areaid_2",
    "market_id": "market1",
    "time_slot": 123123,
    "creation_time": 456456,
    "energy": 0.30,
    "energy_rate": 0.080,
    "allocated_energy": 0.20,
}


class TestBuildBuyerPoolTrade:
    def test_structure(self):
        trade = build_buyer_pool_trade(
            bid=SAMPLE_BID,
            pool_id="AMM_POOL_community1",
            market_id="market1",
            time_slot=123123,
            clearing_price=15.0,
            tx_hash="0xabc",
            theta=1.0,
            steepness=2.5,
            total_supply_kwh=12.5,
            total_demand_kwh=10.0,
        )

        # Top-level fields
        assert trade["status"] == "Settled"
        assert trade["buyer"] == "Account1"
        assert trade["seller"] == "AMM_POOL_community1"
        assert trade["market_id"] == "market1"
        assert trade["time_slot"] == 123123
        assert trade["_id"].startswith("0x")
        assert trade["trade_uuid"]

        # Bid component
        assert trade["bid"]["buyer"] == "Account1"
        assert trade["bid"]["bid_component"]["energy"] == 0.20
        assert trade["bid"]["bid_component"]["energy_rate"] == 15.0

        # Offer component (pool side)
        assert trade["offer"]["seller"] == "AMM_POOL_community1"
        assert trade["offer"]["offer_component"]["energy"] == 0.20
        assert trade["offer"]["offer_component"]["energy_rate"] == 15.0

        # Hashes
        assert trade["bid_hash"] == "0xbid123"
        assert trade["offer_hash"] == "0xabc"

        # Parameters
        assert trade["parameters"]["selected_energy"] == 0.20
        assert trade["parameters"]["energy_rate"] == 15.0
        assert trade["parameters"]["amm_tx_hash"] == "0xabc"
        assert trade["parameters"]["theta"] == 1.0
        assert trade["parameters"]["steepness"] == 2.5
        assert trade["parameters"]["preference_matched"] is False

    def test_residual_bid_partial_fill(self):
        """When allocated < energy, residual_bid should be set."""
        trade = build_buyer_pool_trade(
            bid=SAMPLE_BID,  # energy=0.26, allocated=0.20
            pool_id="pool",
            market_id="m1",
            time_slot=1,
            clearing_price=15.0,
            tx_hash="0x1",
            theta=1.0,
            steepness=2.5,
            total_supply_kwh=10.0,
            total_demand_kwh=12.0,
        )
        assert trade["residual_bid"] is not None
        assert abs(trade["residual_bid"]["energy"] - 0.06) < 1e-9
        assert trade["residual_bid"]["energy_rate"] == 0.123
        assert trade["residual_offer"] is None

    def test_no_residual_full_fill(self):
        """When allocated == energy, no residual."""
        bid = {**SAMPLE_BID, "allocated_energy": 0.26}
        trade = build_buyer_pool_trade(
            bid=bid,
            pool_id="pool",
            market_id="m1",
            time_slot=1,
            clearing_price=15.0,
            tx_hash="0x1",
            theta=1.0,
            steepness=2.5,
            total_supply_kwh=10.0,
            total_demand_kwh=10.0,
        )
        assert trade["residual_bid"] is None


class TestBuildPoolSellerTrade:
    def test_structure(self):
        trade = build_pool_seller_trade(
            offer=SAMPLE_OFFER,
            pool_id="AMM_POOL_community1",
            market_id="market1",
            time_slot=123123,
            clearing_price=15.0,
            tx_hash="0xdef",
            theta=1.0,
            steepness=2.5,
            total_supply_kwh=12.5,
            total_demand_kwh=10.0,
        )

        assert trade["status"] == "Settled"
        assert trade["buyer"] == "AMM_POOL_community1"
        assert trade["seller"] == "Account2"
        assert trade["offer"]["seller"] == "Account2"
        assert trade["bid"]["buyer"] == "AMM_POOL_community1"
        assert trade["offer_hash"] == "0xoffer456"
        assert trade["bid_hash"] == "0xdef"

    def test_residual_offer_partial_fill(self):
        """When allocated < energy, residual_offer should be set."""
        trade = build_pool_seller_trade(
            offer=SAMPLE_OFFER,  # energy=0.30, allocated=0.20
            pool_id="pool",
            market_id="m1",
            time_slot=1,
            clearing_price=15.0,
            tx_hash="0x1",
            theta=1.0,
            steepness=2.5,
            total_supply_kwh=12.0,
            total_demand_kwh=10.0,
        )
        assert trade["residual_offer"] is not None
        assert abs(trade["residual_offer"]["energy"] - 0.10) < 1e-9
        assert trade["residual_offer"]["energy_rate"] == 0.080
        assert trade["residual_bid"] is None
