"""Tests for the execution cycle with mocked dependencies."""

import pytest

from src.config import CommunityConfig, PenaltyConfig
from src.execution import compute_previous_timeslot, run_execution_cycle


class MockDBClient:
    def __init__(self, trades=None, measurements=None):
        self._trades = trades or []
        self._measurements = measurements or {}

    async def get_trades(self, market_id):
        return self._trades

    async def get_asset_measurements(self, community_uuid, area_uuid):
        return self._measurements.get(area_uuid, [])


COMMUNITY = CommunityConfig(
    k_upper_ct_per_kwh=28.5,
    k_lower_ct_per_kwh=8.0,
    theta=1.0,
    steepness=2.5,
)

PENALTIES = PenaltyConfig(gamma=1.1, eta=0.0)


def make_seller_trade(seller, area, energy, clearing_price=18.0,
                      total_supply=10.0, total_demand=10.0):
    return {
        "trade_uuid": f"trade_pool_{seller}",
        "status": "Settled",
        "buyer": "AMM_POOL_test",
        "seller": seller,
        "offer": {"seller": seller, "offer_component": {"area_uuid": area}},
        "bid": {"buyer": "AMM_POOL_test", "bid_component": {"area_uuid": "AMM_POOL_test"}},
        "parameters": {
            "selected_energy": energy,
            "energy_rate": clearing_price,
            "total_supply_kwh": total_supply,
            "total_demand_kwh": total_demand,
            "theta": 1.0,
            "steepness": 2.5,
        },
    }


def make_buyer_trade(buyer, area, energy, clearing_price=18.0,
                     total_supply=10.0, total_demand=10.0):
    return {
        "trade_uuid": f"trade_{buyer}_pool",
        "status": "Settled",
        "buyer": buyer,
        "seller": "AMM_POOL_test",
        "offer": {"seller": "AMM_POOL_test", "offer_component": {"area_uuid": "AMM_POOL_test"}},
        "bid": {"buyer": buyer, "bid_component": {"area_uuid": area}},
        "parameters": {
            "selected_energy": energy,
            "energy_rate": clearing_price,
            "total_supply_kwh": total_supply,
            "total_demand_kwh": total_demand,
            "theta": 1.0,
            "steepness": 2.5,
        },
    }


def make_measurement(area_uuid, time_slot, energy_kwh):
    return {
        "metadata": {
            "area_uuid": area_uuid,
            "community_uuid": "c1",
            "time_slot": time_slot,
        },
        "energy_kWh": energy_kwh,
    }


class TestComputePreviousTimeslot:
    def test_rounds_down(self):
        slot = compute_previous_timeslot(900, -120)
        # Should be a multiple of 900
        assert slot % 900 == 0

    def test_offset_applied(self):
        import time
        now = int(time.time())
        slot = compute_previous_timeslot(900, -120)
        # Slot should be at least 2 hours old
        assert slot <= now - 7200


@pytest.mark.asyncio
async def test_execution_no_trades():
    """No settled trades → skip."""
    db = MockDBClient(trades=[])
    result = await run_execution_cycle(
        community_uuid="c1",
        market_id="m1",
        time_slot=100000,
        community_config=COMMUNITY,
        penalty_config=PENALTIES,
        db_client=db,
    )
    assert result["status"] == "skipped"


@pytest.mark.asyncio
async def test_execution_with_shortfall():
    """Seller shortfall detected via measurements."""
    time_slot = 100000
    trades = [
        make_seller_trade("Seller1", "area_s1", 5.0),
        make_buyer_trade("Buyer1", "area_b1", 5.0),
    ]
    measurements = {
        "area_s1": [make_measurement("area_s1", time_slot, 3.0)],
        "area_b1": [make_measurement("area_b1", time_slot, 5.0)],
    }
    db = MockDBClient(trades=trades, measurements=measurements)

    result = await run_execution_cycle(
        community_uuid="c1",
        market_id="m1",
        time_slot=time_slot,
        community_config=COMMUNITY,
        penalty_config=PENALTIES,
        db_client=db,
    )

    assert result["status"] == "executed"
    assert result["total_penalties"] > 0

    # Find the seller penalty result
    seller_result = [
        r for r in result["penalty_results"]
        if r["trade_uuid"] == "trade_pool_Seller1"
    ][0]
    assert seller_result["seller_shortfall_penalty"] > 0


@pytest.mark.asyncio
async def test_execution_no_deviations():
    """When measurements match trades, total penalties = 0."""
    time_slot = 100000
    trades = [
        make_seller_trade("Seller1", "area_s1", 5.0),
        make_buyer_trade("Buyer1", "area_b1", 5.0),
    ]
    measurements = {
        "area_s1": [make_measurement("area_s1", time_slot, 5.0)],
        "area_b1": [make_measurement("area_b1", time_slot, 5.0)],
    }
    db = MockDBClient(trades=trades, measurements=measurements)

    result = await run_execution_cycle(
        community_uuid="c1",
        market_id="m1",
        time_slot=time_slot,
        community_config=COMMUNITY,
        penalty_config=PENALTIES,
        db_client=db,
    )

    assert result["status"] == "executed"
    assert result["total_penalties"] == 0.0
