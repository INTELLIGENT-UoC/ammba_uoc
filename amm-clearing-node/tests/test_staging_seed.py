"""Tests for the staging test data set (sim/staging_seed.py)."""

from collections import defaultdict
from datetime import date

import httpx
import pytest
import yaml
from sim.offchain_sim import create_app
from sim.staging_seed import (
    actor_uuid,
    build_seed,
    community_snippet,
    community_uuid,
    main,
    pool_actor_uuid,
)
from src.adapters import iso_to_unix
from src.config import CommunityConfig, Settings
from src.offchain_db import OffchainDBClient
from src.ontology import validate_trade
from src.scheduler import run_scheduler_tick

DAY = date(2026, 11, 10)


def _orders_by_market(seed: dict) -> dict[str, list[dict]]:
    by_market = defaultdict(list)
    for order in seed["orders"]:
        by_market[order["marketId"]].append(order)
    return by_market


def test_seed_is_deterministic_and_complete():
    seed = build_seed(DAY, history_days=2)  # build_seed validates every object
    assert seed == build_seed(DAY, history_days=2)

    assert len(seed["markets"]) == 96
    assert {m["matchingAlgorithm"] for m in seed["markets"]} == {"amm"}
    assert {m["communityId"] for m in seed["markets"]} == {community_uuid()}
    assert len({o["orderId"] for o in seed["orders"]}) == len(seed["orders"])

    by_market = _orders_by_market(seed)
    pair = {actor_uuid("household-1"), actor_uuid("biomass-chp")}
    for market in seed["markets"]:
        orders = by_market[market["marketId"]]
        assert {o["orderType"] for o in orders} == {"bid", "offer"}
        preferring = {o["createdBy"] for o in orders if o.get("preferredTradingPartner")}
        assert preferring == pair

    # Metering covers the two days before the market day, every slot.
    slots = {m["timeSlot"] for m in seed["measurements"]}
    assert len(slots) == 2 * 96
    assert min(slots) == "2026-11-08T00:00:00Z"
    assert max(slots) == "2026-11-09T23:45:00Z"


def test_supply_demand_ratio_spans_the_sigmoid():
    """Evening peaks sit below the midpoint, midday reaches the clamped band."""
    ratios = []
    for orders in _orders_by_market(build_seed(DAY, history_days=0)).values():
        supply = sum(o["quantity"] for o in orders if o["orderType"] == "offer")
        demand = sum(o["quantity"] for o in orders if o["orderType"] == "bid")
        ratios.append(supply / demand)
    assert min(ratios) < 0.5
    assert max(ratios) > 2.0


def test_community_snippet_is_valid_config():
    config = yaml.safe_load(community_snippet())
    assert list(config) == [community_uuid()]
    parsed = CommunityConfig(**config[community_uuid()])
    assert parsed.pool_actor_uuid == pool_actor_uuid()


@pytest.mark.asyncio
async def test_scheduler_clears_the_seeded_day(tmp_path, monkeypatch):
    """The simulator serves the generated set; a tick at noon clears every closed market,
    including those whose orders the storage has already expired."""
    assert main(["--date", DAY.isoformat(), "--out", str(tmp_path)]) == 0
    monkeypatch.setenv("SIM_SEED_DIR", str(tmp_path))
    app = create_app()
    assert len(app.state.store.markets) == 96

    config = CommunityConfig(**yaml.safe_load(community_snippet())[community_uuid()])
    settings = Settings(communities={community_uuid(): config})
    db = OffchainDBClient("http://sim")
    db._client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://sim")

    now = iso_to_unix("2026-11-10T12:00:00Z")
    # As on the storage, orders of started slots have expired before the AMM clears.
    expired = (await db._client.post("/_expire_orders", params={"now": now})).json()["expired"]
    assert 0 < expired < len(app.state.store.orders)
    results = await run_scheduler_tick(settings, db, None, set(), now=now)
    await db.close()

    # Closing times 00:00 … 12:00 inclusive: 49 markets due, all cleared.
    assert len(results) == 49
    assert {r["status"] for r in results} == {"cleared"}

    trades = app.state.store.trades
    for trade in trades:
        validate_trade(trade)
    pool = pool_actor_uuid()
    direct = {t["marketId"] for t in trades if pool not in (t["buyerId"], t["sellerId"])}
    assert len(direct) == 49  # the mutual preferred pair trades directly in every market
