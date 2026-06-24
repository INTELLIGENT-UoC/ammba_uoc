"""Integration tests for the clearing pipeline against the int.* contract."""

import pytest
from src.clearing import run_clearing

from tests.conftest import (
    MARKET_ID,
    POOL_ACTOR_UUID,
    TIME_SLOT_UNIX,
    FakeDBClient,
    actor_uuid,
    make_int_order,
)


async def _clear(orders, community, existing_trades=None):
    db = FakeDBClient(orders, existing_trades=existing_trades)
    result = await run_clearing(
        market_id=MARKET_ID,
        community_uuid="11111111-1111-4111-8111-111111111111",
        time_slot=TIME_SLOT_UNIX,
        community_config=community,
        db_client=db,
        contract_client=None,
        time_slot_sec=900,
    )
    return result, db


@pytest.mark.asyncio
async def test_basic_clearing(community):
    orders = [
        make_int_order("B1", "Bid", 5.0),
        make_int_order("B2", "Bid", 5.0),
        make_int_order("S1", "Offer", 6.0),
        make_int_order("S2", "Offer", 4.0),
    ]
    result, db = await _clear(orders, community)

    assert result["status"] == "cleared"
    assert result["total_supply_kwh"] == 10.0
    assert result["total_demand_kwh"] == 10.0
    assert result["traded_quantity_kwh"] == 10.0
    # 2 buyer→pool + 2 pool→seller
    assert result["num_trades"] == 4
    assert len(db.posted_trades) == 4

    for trade in db.posted_trades:
        assert trade["tradeStatus"] == "settled"
        assert trade["marketId"] == MARKET_ID
        # Exactly one side of every pool trade is the pool actor.
        assert POOL_ACTOR_UUID in (trade["buyerId"], trade["sellerId"])

    # A FINAL clearing result was posted.
    assert len(db.posted_clearing_results) == 1
    cr = db.posted_clearing_results[0]
    assert cr["clearingStatus"] == "FINAL"
    assert cr["numTrades"] == 4


@pytest.mark.asyncio
async def test_supply_exceeds_demand(community):
    orders = [
        make_int_order("B1", "Bid", 5.0),
        make_int_order("S1", "Offer", 8.0),
    ]
    result, db = await _clear(orders, community)

    assert result["status"] == "cleared"
    assert result["traded_quantity_kwh"] == 5.0  # min(8, 5)
    assert len(db.posted_trades) == 2

    seller_trade = [t for t in db.posted_trades if t["sellerId"] == actor_uuid("S1")][0]
    # Pool sells the seller's pro-rata share (full traded quantity here).
    assert abs(seller_trade["tradeQuantity"] - 5.0) < 1e-9


@pytest.mark.asyncio
async def test_demand_exceeds_supply(community):
    orders = [
        make_int_order("B1", "Bid", 10.0),
        make_int_order("S1", "Offer", 3.0),
    ]
    result, db = await _clear(orders, community)

    assert result["status"] == "cleared"
    assert result["traded_quantity_kwh"] == 3.0

    buyer_trade = [t for t in db.posted_trades if t["buyerId"] == actor_uuid("B1")][0]
    assert abs(buyer_trade["tradeQuantity"] - 3.0) < 1e-9


@pytest.mark.asyncio
async def test_no_bids(community):
    orders = [make_int_order("S1", "Offer", 5.0)]
    result, db = await _clear(orders, community)

    assert result["status"] == "no_trade"
    assert len(db.posted_trades) == 0
    # NO_BID clearing result still recorded.
    assert db.posted_clearing_results[0]["clearingStatus"] == "NO_BID"


@pytest.mark.asyncio
async def test_no_offers(community):
    orders = [make_int_order("B1", "Bid", 5.0)]
    result, db = await _clear(orders, community)
    assert result["status"] == "no_trade"


@pytest.mark.asyncio
async def test_idempotency_skips_if_trades_exist(community):
    orders = [make_int_order("B1", "Bid", 5.0), make_int_order("S1", "Offer", 5.0)]
    existing = [{"tradeId": "existing"}]
    result, db = await _clear(orders, community, existing_trades=existing)

    assert result["status"] == "skipped"
    assert len(db.posted_trades) == 0


@pytest.mark.asyncio
async def test_filters_non_matchable_orders(community):
    orders = [
        make_int_order("B1", "Bid", 5.0),
        make_int_order("S1", "Offer", 5.0),
        make_int_order("B2", "Bid", 10.0, status="Executed"),
        make_int_order("S2", "Offer", 10.0, status="Cancelled"),
    ]
    result, db = await _clear(orders, community)

    assert result["status"] == "cleared"
    assert result["total_supply_kwh"] == 5.0  # only S1
    assert result["total_demand_kwh"] == 5.0  # only B1
    assert result["num_trades"] == 2


@pytest.mark.asyncio
async def test_clearing_price_within_bounds(community):
    orders = [make_int_order("B1", "Bid", 5.0), make_int_order("S1", "Offer", 5.0)]
    result, _ = await _clear(orders, community)

    price = result["clearing_price_ct_per_kwh"]
    assert community.k_lower_ct_per_kwh <= price <= community.k_upper_ct_per_kwh
    # Wire price is the same value in EUR/kWh.
    assert abs(result["clearing_price_eur_per_kwh"] - price / 100.0) < 1e-12


@pytest.mark.asyncio
async def test_pro_rata_allocation_multiple_participants(community):
    orders = [
        make_int_order("B1", "Bid", 3.0),
        make_int_order("B2", "Bid", 7.0),
        make_int_order("S1", "Offer", 4.0),
        make_int_order("S2", "Offer", 6.0),
    ]
    result, db = await _clear(orders, community)

    assert result["num_trades"] == 4
    buyer_qty = {
        t["buyerId"]: t["tradeQuantity"]
        for t in db.posted_trades
        if t["buyerId"] != POOL_ACTOR_UUID
    }
    seller_qty = {
        t["sellerId"]: t["tradeQuantity"]
        for t in db.posted_trades
        if t["sellerId"] != POOL_ACTOR_UUID
    }
    assert abs(buyer_qty[actor_uuid("B1")] - 3.0) < 1e-9
    assert abs(buyer_qty[actor_uuid("B2")] - 7.0) < 1e-9
    assert abs(seller_qty[actor_uuid("S1")] - 4.0) < 1e-9
    assert abs(seller_qty[actor_uuid("S2")] - 6.0) < 1e-9


@pytest.mark.asyncio
async def test_preference_matched_pair_trades_directly(community):
    """Mutual preferred partners trade directly, not through the pool."""
    orders = [
        make_int_order("B1", "Bid", 5.0, partner=actor_uuid("S1")),
        make_int_order("S1", "Offer", 5.0, partner=actor_uuid("B1")),
        make_int_order("B2", "Bid", 5.0),
        make_int_order("S2", "Offer", 5.0),
    ]
    result, db = await _clear(orders, community)

    assert result["status"] == "cleared"
    # B1↔S1 directly (no pool actor on either side), B2/S2 via the pool.
    direct = [t for t in db.posted_trades if POOL_ACTOR_UUID not in (t["buyerId"], t["sellerId"])]
    assert len(direct) == 1
    assert direct[0]["buyerId"] == actor_uuid("B1")
    assert direct[0]["sellerId"] == actor_uuid("S1")
    assert abs(direct[0]["tradeQuantity"] - 5.0) < 1e-9
