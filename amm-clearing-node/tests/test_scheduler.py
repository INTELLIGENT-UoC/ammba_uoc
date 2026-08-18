"""Tests for market discovery and the self-trigger scheduler."""

import httpx
import pytest
from sim.offchain_sim import create_app
from src.adapters import ewds_market_to_internal, iso_to_unix
from src.config import Settings
from src.ewds_client import EwdsConfig, EwdsOffchainClient
from src.offchain_db import OffchainDBClient
from src.scheduler import run_scheduler_tick, select_due_markets

from tests.conftest import TIME_SLOT_UNIX, community  # noqa: F401

SEED_MARKET = "33333333-3333-4333-8333-333333333333"
COMMUNITY = "11111111-1111-4111-8111-111111111111"
CLOSING = iso_to_unix("2026-07-01T10:00:00Z")


def _market(**overrides) -> dict:
    market = {
        "market_id": SEED_MARKET,
        "community_id": COMMUNITY,
        "opening_time": CLOSING - 1800,
        "closing_time": CLOSING,
        "delivery_start_time": CLOSING,
        "delivery_end_time": CLOSING + 900,
        "matching_algorithm": "amm",
    }
    market.update(overrides)
    return market


class TestMarketNormalizer:
    def test_market_schema_dialect(self):
        """GSY DB MarketSchema: snake_case, ISO strings, lowercase algorithm."""
        internal = ewds_market_to_internal(
            {
                "market_id": SEED_MARKET,
                "community_id": COMMUNITY,
                "opening_time": "2026-07-01T09:30:00Z",
                "closing_time": "2026-07-01T10:00:00Z",
                "delivery_start_time": "2026-07-01T10:00:00Z",
                "delivery_end_time": "2026-07-01T10:15:00Z",
                "market_type": "local_spot",
                "matching_algorithm": "amm",
                "created_at": "2026-07-01T09:30:00Z",
            }
        )
        assert internal["market_id"] == SEED_MARKET
        assert internal["closing_time"] == CLOSING
        assert internal["delivery_start_time"] == TIME_SLOT_UNIX
        assert internal["matching_algorithm"] == "amm"

    def test_int_market_dialect(self):
        """int:Market ontology: camelCase, 'AMM' — normalizes to the same."""
        internal = ewds_market_to_internal(
            {
                "marketId": SEED_MARKET,
                "communityId": COMMUNITY,
                "openingTime": CLOSING - 1800,
                "closingTime": CLOSING,
                "deliveryStartTime": CLOSING,
                "deliveryEndTime": CLOSING + 900,
                "matchingAlgorithm": "AMM",
            }
        )
        assert internal["closing_time"] == CLOSING
        assert internal["matching_algorithm"] == "amm"


class TestSelectDueMarkets:
    def test_closed_amm_market_is_due(self):
        due = select_due_markets([_market()], {COMMUNITY}, CLOSING + 1, set())
        assert [m["market_id"] for m in due] == [SEED_MARKET]

    def test_still_open_market_not_due(self):
        due = select_due_markets([_market()], {COMMUNITY}, CLOSING - 1, set())
        assert due == []

    def test_closing_exactly_now_is_due(self):
        due = select_due_markets([_market()], {COMMUNITY}, CLOSING, set())
        assert len(due) == 1

    def test_non_amm_market_skipped(self):
        due = select_due_markets(
            [_market(matching_algorithm="pay_as_bid")], {COMMUNITY}, CLOSING + 1, set()
        )
        assert due == []

    def test_unknown_community_skipped(self):
        due = select_due_markets([_market()], {"other-community"}, CLOSING + 1, set())
        assert due == []

    def test_processed_market_skipped(self):
        due = select_due_markets([_market()], {COMMUNITY}, CLOSING + 1, {SEED_MARKET})
        assert due == []


def _settings(community_config) -> Settings:
    return Settings(
        communities={COMMUNITY: community_config},
        scheduler_enabled=True,
        scheduler_poll_interval_sec=1,
    )


@pytest.mark.asyncio
async def test_scheduler_tick_end_to_end_rest(community):  # noqa: F811
    """Tick discovers the closed AMM seed market and clears it via REST."""
    app = create_app()
    db = OffchainDBClient("http://sim")
    db._client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://sim")

    processed: set[str] = set()
    results = await run_scheduler_tick(_settings(community), db, None, processed, now=CLOSING + 60)

    # Only the AMM market cleared — the seeded pay_as_bid market is ignored.
    assert [r["market_id"] for r in results] == [SEED_MARKET]
    assert results[0]["status"] == "cleared"
    assert SEED_MARKET in processed
    assert len(app.state.store.trades) == results[0]["num_trades"]

    # Second tick: market already processed -> nothing to do.
    second = await run_scheduler_tick(_settings(community), db, None, processed, now=CLOSING + 120)
    assert second == []
    await db.close()


@pytest.mark.asyncio
async def test_scheduler_tick_end_to_end_ewds(community):  # noqa: F811
    """Same discovery flow over the EWDS gateway (marketsQuery publish/poll)."""
    app = create_app()
    client = EwdsOffchainClient(
        EwdsConfig(gateway_url="http://sim", poll_interval_ms=5, timeout_ms=2000)
    )
    client._client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://sim"
    )

    results = await run_scheduler_tick(_settings(community), client, None, set(), now=CLOSING + 60)
    assert [r["market_id"] for r in results] == [SEED_MARKET]
    assert results[0]["status"] == "cleared"
    await client.close()
