"""Integration tests for the clearing algorithm with mocked dependencies."""

import pytest

from src.clearing import run_clearing
from src.config import CommunityConfig
from src.offchain_db import OffchainDBClient


class MockDBClient:
    """Mock off-chain DB client for testing."""

    def __init__(self, orders: list[dict], existing_trades: list[dict] | None = None):
        self._orders = orders
        self._existing_trades = existing_trades or []
        self.posted_trades: list[dict] = []

    async def get_orders(self, market_id, start_time, end_time):
        return self._orders

    async def get_trades(self, market_id):
        return self._existing_trades

    async def post_trades(self, trades):
        self.posted_trades.extend(trades)


COMMUNITY = CommunityConfig(
    k_upper_ct_per_kwh=28.5,
    k_lower_ct_per_kwh=8.0,
    theta=1.0,
    steepness=2.5,
    pool_id="AMM_POOL_test",
)


def make_bid(account, energy, rate=25.0, area="area1"):
    return {
        "order_id": f"0xbid_{account}",
        "status": "Open",
        "order_type": "Bid",
        "created_by": account,
        "area_uuid": area,
        "market_id": "market1",
        "time_slot": 100000,
        "creation_time": 99000,
        "energy": energy,
        "energy_rate": rate,
    }


def make_offer(account, energy, rate=5.0, area="area2"):
    return {
        "order_id": f"0xoffer_{account}",
        "status": "Open",
        "order_type": "Offer",
        "created_by": account,
        "area_uuid": area,
        "market_id": "market1",
        "time_slot": 100000,
        "creation_time": 99000,
        "energy": energy,
        "energy_rate": rate,
    }


@pytest.mark.asyncio
async def test_basic_clearing():
    """Test a simple clearing with 2 bids and 2 offers."""
    orders = [
        make_bid("Buyer1", 5.0),
        make_bid("Buyer2", 5.0),
        make_offer("Seller1", 6.0),
        make_offer("Seller2", 4.0),
    ]
    db = MockDBClient(orders)

    result = await run_clearing(
        market_id="market1",
        community_uuid="community1",
        time_slot=100000,
        community_config=COMMUNITY,
        db_client=db,
        contract_client=None,
        time_slot_sec=900,
    )

    assert result["status"] == "cleared"
    assert result["total_supply_kwh"] == 10.0
    assert result["total_demand_kwh"] == 10.0
    assert result["traded_quantity_kwh"] == 10.0
    # 2 bids + 2 offers = 4 trades (each participant trades with pool)
    assert result["num_trades"] == 4
    assert len(db.posted_trades) == 4

    # Verify trade structure
    for trade in db.posted_trades:
        assert trade["status"] == "Settled"
        assert trade["_id"].startswith("0x")
        assert trade["parameters"]["amm_tx_hash"] == "0x0"
        assert "AMM_POOL" in trade["buyer"] or "AMM_POOL" in trade["seller"]


@pytest.mark.asyncio
async def test_supply_exceeds_demand():
    """When supply > demand, sellers get partial fills."""
    orders = [
        make_bid("Buyer1", 5.0),
        make_offer("Seller1", 8.0),
    ]
    db = MockDBClient(orders)

    result = await run_clearing(
        market_id="m2",
        community_uuid="c1",
        time_slot=100000,
        community_config=COMMUNITY,
        db_client=db,
        contract_client=None,
    )

    assert result["status"] == "cleared"
    assert result["traded_quantity_kwh"] == 5.0  # min(8, 5)
    assert len(db.posted_trades) == 2

    # Seller trade should have residual
    seller_trade = [t for t in db.posted_trades if t["seller"] != "AMM_POOL_test"][0]
    assert seller_trade["residual_offer"] is not None
    assert abs(seller_trade["residual_offer"]["energy"] - 3.0) < 1e-9

    # Buyer trade should be fully filled
    buyer_trade = [t for t in db.posted_trades if t["buyer"] != "AMM_POOL_test"][0]
    assert buyer_trade["residual_bid"] is None


@pytest.mark.asyncio
async def test_demand_exceeds_supply():
    """When demand > supply, buyers get partial fills."""
    orders = [
        make_bid("Buyer1", 10.0),
        make_offer("Seller1", 3.0),
    ]
    db = MockDBClient(orders)

    result = await run_clearing(
        market_id="m3",
        community_uuid="c1",
        time_slot=100000,
        community_config=COMMUNITY,
        db_client=db,
        contract_client=None,
    )

    assert result["status"] == "cleared"
    assert result["traded_quantity_kwh"] == 3.0

    buyer_trade = [t for t in db.posted_trades if t["buyer"] != "AMM_POOL_test"][0]
    assert buyer_trade["residual_bid"] is not None
    assert abs(buyer_trade["residual_bid"]["energy"] - 7.0) < 1e-9


@pytest.mark.asyncio
async def test_no_bids():
    """No bids → no trade."""
    orders = [make_offer("Seller1", 5.0)]
    db = MockDBClient(orders)

    result = await run_clearing(
        market_id="m4",
        community_uuid="c1",
        time_slot=100000,
        community_config=COMMUNITY,
        db_client=db,
        contract_client=None,
    )

    assert result["status"] == "no_trade"
    assert len(db.posted_trades) == 0


@pytest.mark.asyncio
async def test_no_offers():
    """No offers → no trade."""
    orders = [make_bid("Buyer1", 5.0)]
    db = MockDBClient(orders)

    result = await run_clearing(
        market_id="m5",
        community_uuid="c1",
        time_slot=100000,
        community_config=COMMUNITY,
        db_client=db,
        contract_client=None,
    )

    assert result["status"] == "no_trade"


@pytest.mark.asyncio
async def test_idempotency_skips_if_trades_exist():
    """If trades already exist for the market, skip clearing."""
    orders = [make_bid("B1", 5.0), make_offer("S1", 5.0)]
    existing = [{"trade_uuid": "existing_trade"}]
    db = MockDBClient(orders, existing_trades=existing)

    result = await run_clearing(
        market_id="m6",
        community_uuid="c1",
        time_slot=100000,
        community_config=COMMUNITY,
        db_client=db,
        contract_client=None,
    )

    assert result["status"] == "skipped"
    assert len(db.posted_trades) == 0


@pytest.mark.asyncio
async def test_filters_non_open_orders():
    """Only Open orders should be considered for clearing."""
    orders = [
        make_bid("B1", 5.0),
        make_offer("S1", 5.0),
        {**make_bid("B2", 10.0), "status": "Executed"},
        {**make_offer("S2", 10.0), "status": "Expired"},
    ]
    db = MockDBClient(orders)

    result = await run_clearing(
        market_id="m7",
        community_uuid="c1",
        time_slot=100000,
        community_config=COMMUNITY,
        db_client=db,
        contract_client=None,
    )

    assert result["status"] == "cleared"
    assert result["total_supply_kwh"] == 5.0  # Only S1
    assert result["total_demand_kwh"] == 5.0  # Only B1
    assert result["num_trades"] == 2


@pytest.mark.asyncio
async def test_clearing_price_within_bounds():
    """Clearing price must always be within [K_lower, K_upper]."""
    orders = [
        make_bid("B1", 5.0),
        make_offer("S1", 5.0),
    ]
    db = MockDBClient(orders)

    result = await run_clearing(
        market_id="m8",
        community_uuid="c1",
        time_slot=100000,
        community_config=COMMUNITY,
        db_client=db,
        contract_client=None,
    )

    price = result["clearing_price_ct_per_kwh"]
    assert COMMUNITY.k_lower_ct_per_kwh <= price <= COMMUNITY.k_upper_ct_per_kwh


@pytest.mark.asyncio
async def test_pro_rata_allocation_multiple_participants():
    """Pro-rata: each participant gets proportional share."""
    orders = [
        make_bid("B1", 3.0),
        make_bid("B2", 7.0),
        make_offer("S1", 4.0),
        make_offer("S2", 6.0),
    ]
    db = MockDBClient(orders)

    result = await run_clearing(
        market_id="m9",
        community_uuid="c1",
        time_slot=100000,
        community_config=COMMUNITY,
        db_client=db,
        contract_client=None,
    )

    assert result["status"] == "cleared"
    assert result["num_trades"] == 4

    # Check allocations via trade parameters
    buyer_trades = [t for t in db.posted_trades if t["buyer"] != "AMM_POOL_test"]
    seller_trades = [t for t in db.posted_trades if t["seller"] != "AMM_POOL_test"]

    buyer_energies = {
        t["buyer"]: t["parameters"]["selected_energy"] for t in buyer_trades
    }
    seller_energies = {
        t["seller"]: t["parameters"]["selected_energy"] for t in seller_trades
    }

    # Balanced market: traded_quantity = 10.0
    # B1: 3/10 * 10 = 3.0, B2: 7/10 * 10 = 7.0
    assert abs(buyer_energies["B1"] - 3.0) < 1e-9
    assert abs(buyer_energies["B2"] - 7.0) < 1e-9
    # S1: 4/10 * 10 = 4.0, S2: 6/10 * 10 = 6.0
    assert abs(seller_energies["S1"] - 4.0) < 1e-9
    assert abs(seller_energies["S2"] - 6.0) < 1e-9
