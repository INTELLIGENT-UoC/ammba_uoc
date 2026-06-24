"""Shared test fixtures.

The fake off-chain DB validates every payload it receives against the vendored
int.* schemas, and the order fixtures are emitted in the int:Order ontology
shape — so a test passes only if the clearing node both consumes and produces
wire-compatible data. This replaces the per-module hand-rolled mocks that used
to encode the AMM's internal shape instead of the agreed contract.
"""

import uuid
from datetime import datetime

import pytest
from src.config import CommunityConfig
from src.ontology import (
    validate_clearing_result,
    validate_order,
    validate_trade,
)

POOL_ACTOR_UUID = "22222222-2222-4222-8222-222222222222"
MARKET_ID = "33333333-3333-4333-8333-333333333333"
TIME_SLOT_ISO = "2026-07-01T10:00:00Z"
TIME_SLOT_UNIX = int(datetime.fromisoformat("2026-07-01T10:00:00+00:00").timestamp())
CREATED_AT_ISO = "2026-07-01T09:45:00Z"


def stable_uuid(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ammba-test:{label}"))


def actor_uuid(label: str) -> str:
    return stable_uuid(f"actor:{label}")


def make_int_order(
    label: str,
    order_type: str,
    quantity: float,
    *,
    market_id: str = MARKET_ID,
    price_limit: float = 0.20,
    status: str = "Submitted",
    time_slot: str = TIME_SLOT_ISO,
    created_at: str = CREATED_AT_ISO,
    created_by: str | None = None,
    energy_type: str | None = None,
    energy_source: str | None = None,
    partner: str | None = None,
) -> dict:
    """Build a schema-valid int:Order. ``label`` derives stable UUIDs."""
    order = {
        "orderId": stable_uuid(f"order:{label}"),
        "marketId": market_id,
        "orderType": order_type,
        "orderStatus": status,
        "timeSlot": time_slot,
        "quantity": quantity,
        "priceLimit": price_limit,
        "createdBy": created_by or actor_uuid(label),
        "createdAt": created_at,
    }
    if energy_type is not None:
        order["energyType"] = energy_type
    if energy_source is not None:
        order["energySourcePreference"] = energy_source
    if partner is not None:
        order["preferredTradingPartner"] = partner
    validate_order(order)
    return order


@pytest.fixture
def community() -> CommunityConfig:
    return CommunityConfig(
        k_upper_ct_per_kwh=28.5,
        k_lower_ct_per_kwh=8.0,
        theta=1.0,
        steepness=2.5,
        pool_id="AMM_POOL_test",
        pool_actor_uuid=POOL_ACTOR_UUID,
    )


class FakeDBClient:
    """In-memory off-chain DB that validates payloads against int.* schemas."""

    def __init__(
        self,
        orders: list[dict] | None = None,
        existing_trades: list[dict] | None = None,
    ):
        self._orders = orders or []
        self._existing_trades = existing_trades or []
        self.posted_trades: list[dict] = []
        self.posted_clearing_results: list[dict] = []

    async def get_orders(self, market_id, start_time, end_time):
        return list(self._orders)

    async def get_trades(self, market_id):
        return self._existing_trades

    async def post_trades(self, trades):
        for trade in trades:
            validate_trade(trade)
        self.posted_trades.extend(trades)

    async def post_clearing_result(self, result):
        validate_clearing_result(result)
        self.posted_clearing_results.append(result)
