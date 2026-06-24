"""End-to-end test: clearing node ↔ off-chain simulator over the real client.

Drives the actual OffchainDBClient against the actual FastAPI simulator (via
in-memory ASGI transport), seeded from the same int:Order fixtures the sim
ships. Every payload is schema-validated on both sides, so this asserts the
clearing node is wire-compatible end to end without the real GSY environment.
"""

import httpx
import pytest
from sim.offchain_sim import create_app
from src.clearing import run_clearing
from src.config import CommunityConfig
from src.offchain_db import OffchainDBClient
from src.ontology import validate_trade

from tests.conftest import POOL_ACTOR_UUID, TIME_SLOT_UNIX

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
        pool_actor_uuid=POOL_ACTOR_UUID,
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

    # The seed contains a mutual preferred pair → at least one direct trade.
    direct = [t for t in trades if POOL_ACTOR_UUID not in (t["buyerId"], t["sellerId"])]
    assert direct, "expected a direct preference-matched trade"

    # A FINAL clearing result was persisted.
    resp = await db._client.get("/clearing-results", params={"market_id": SEED_MARKET})
    results = resp.json()
    assert results and results[0]["clearingStatus"] == "FINAL"

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
