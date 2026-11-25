"""End-to-end test: clearing node ↔ off-chain simulator over the real client.

Drives the actual OffchainDBClient against the actual FastAPI simulator (via
in-memory ASGI transport), seeded from the same int:Order fixtures the sim
ships. Every payload is schema-validated on both sides, so this asserts the
clearing node is wire-compatible end to end without the real GSY environment.
"""

import httpx
import pytest
from sim.offchain_sim import create_app
from src.adapters import trade_uuid
from src.clearing import run_clearing
from src.config import CommunityConfig
from src.offchain_db import OffchainDBClient
from src.ontology import validate_trade

from tests.conftest import TIME_SLOT_UNIX

SEED_MARKET = "33333333-3333-4333-8333-333333333333"


@pytest.mark.asyncio
async def test_clearing_node_against_simulator():
    app = create_app()  # seeds from sim/seed_orders.json
    transport = httpx.ASGITransport(app=app)

    db = OffchainDBClient("http://sim")
    db._client = httpx.AsyncClient(transport=transport, base_url="http://sim")

    community = CommunityConfig(
        k_upper_ct_per_kwh=28.5,
        k_lower_ct_per_kwh=8.0,
        theta=1.0,
        steepness=2.5,
        pool_id="AMM_POOL_test",
    )

    result = await run_clearing(
        market_id=SEED_MARKET,
        community_uuid="11111111-1111-4111-8111-111111111111",
        time_slot=TIME_SLOT_UNIX,
        community_config=community,
        db_client=db,
        contract_client=None,
        time_slot_sec=900,
    )

    assert result["status"] == "cleared"

    # Trades round-trip back from the simulator and validate against int:Trade.
    trades = await db.get_trades(SEED_MARKET)
    assert len(trades) == result["num_trades"]
    for trade in trades:
        validate_trade(trade)

    # The seed contains a mutual preferred pair → one preference trade; the
    # rest are bilateral matches of the sequential fill. Every trade pairs two
    # participant orders, and the trades sum to the traded quantity.
    pref = [
        t
        for t in trades
        if t["tradeId"] == trade_uuid(SEED_MARKET, "pref", f"{t['bidId']}:{t['offerId']}")
    ]
    assert len(pref) == 1, "expected one preference-matched trade"
    order_ids = {o["orderId"] for o in app.state.store.orders}
    assert all({t["bidId"], t["offerId"]} <= order_ids for t in trades)
    assert round(sum(t["tradeQuantity"] for t in trades), 4) == result["traded_quantity_kwh"]

    # A final clearing result was persisted.
    resp = await db._client.get("/clearing-results", params={"market_id": SEED_MARKET})
    results = resp.json()
    assert results and results[0]["clearingStatus"] == "final"

    # Idempotency: a second run sees existing trades and skips.
    second = await run_clearing(
        market_id=SEED_MARKET,
        community_uuid="11111111-1111-4111-8111-111111111111",
        time_slot=TIME_SLOT_UNIX,
        community_config=community,
        db_client=db,
        contract_client=None,
        time_slot_sec=900,
    )
    assert second["status"] == "skipped"

    await db.close()
