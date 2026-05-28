"""Execution cycle — fetches trades and measurements, computes penalties.

Runs after delivery period ends (controlled by EXECUTION_OFFSET_MIN).
"""

import logging
import time

from src.config import CommunityConfig, PenaltyConfig
from src.offchain_db import OffchainDBClient
from src.penalties import compute_penalties_for_trades

logger = logging.getLogger(__name__)


def compute_previous_timeslot(
    time_slot_sec: int, execution_offset_min: int
) -> int:
    """Compute the most recently completed delivery slot eligible for execution.

    Rounds current time back to the most recently completed slot that is
    older than |execution_offset_min| minutes.
    """
    now = int(time.time())
    offset_sec = abs(execution_offset_min) * 60
    eligible_time = now - offset_sec

    # Round down to the nearest time slot boundary
    return (eligible_time // time_slot_sec) * time_slot_sec


async def run_execution_cycle(
    community_uuid: str,
    market_id: str,
    time_slot: int,
    community_config: CommunityConfig,
    penalty_config: PenaltyConfig,
    db_client: OffchainDBClient,
) -> dict:
    """Execute penalty calculation for a single market slot.

    1. Fetch settled trades for this market
    2. Fetch post-delivery measurements for each participant
    3. Compute penalties
    4. Return penalty results (caller decides how to persist)
    """
    # Step 1: Fetch settled trades
    trades = await db_client.get_trades(market_id)
    settled_trades = [t for t in trades if t.get("status") == "Settled"]

    if not settled_trades:
        logger.info("No settled trades for market_id=%s, skipping", market_id)
        return {"status": "skipped", "reason": "no_settled_trades"}

    # Step 2: Fetch measurements for each participant's area
    measurements: dict[str, float] = {}

    for trade in settled_trades:
        # Collect area_uuids from both sides of the trade
        areas_to_fetch = set()

        offer_area = (
            trade.get("offer", {})
            .get("offer_component", {})
            .get("area_uuid", "")
        )
        bid_area = (
            trade.get("bid", {})
            .get("bid_component", {})
            .get("area_uuid", "")
        )

        # Skip pool areas
        if offer_area and "AMM_POOL" not in offer_area:
            areas_to_fetch.add(offer_area)
        if bid_area and "AMM_POOL" not in bid_area:
            areas_to_fetch.add(bid_area)

        for area_uuid in areas_to_fetch:
            if area_uuid not in measurements:
                try:
                    ms = await db_client.get_asset_measurements(
                        community_uuid, area_uuid
                    )
                    # Find measurement matching this time_slot
                    for m in ms:
                        meta = m.get("metadata", {})
                        if meta.get("time_slot") == time_slot:
                            # Use energy_kWh for general, or sum injection/discharge
                            energy = m.get("energy_kWh", 0)
                            if energy == 0:
                                energy = m.get(
                                    "energy_grid_injection_kWh",
                                    m.get("energy_discharge_kWh", 0),
                                )
                            measurements[area_uuid] = energy
                            break
                    else:
                        logger.warning(
                            "No measurement for area=%s slot=%d",
                            area_uuid,
                            time_slot,
                        )
                        measurements[area_uuid] = 0.0
                except Exception:
                    logger.exception(
                        "Failed to fetch measurements for area=%s", area_uuid
                    )
                    measurements[area_uuid] = 0.0

    # Step 3: Compute penalties
    community_dict = {
        "k_upper": community_config.k_upper_ct_per_kwh,
        "k_lower": community_config.k_lower_ct_per_kwh,
        "theta": community_config.theta,
        "steepness": community_config.steepness,
    }

    penalty_results = compute_penalties_for_trades(
        trades=settled_trades,
        measurements=measurements,
        community_config=community_dict,
        gamma=penalty_config.gamma,
        eta=penalty_config.eta,
    )

    total_penalties = sum(r["total_penalty"] for r in penalty_results)
    logger.info(
        "Market %s: computed penalties for %d trades, total=%.4f",
        market_id,
        len(penalty_results),
        total_penalties,
    )

    return {
        "status": "executed",
        "market_id": market_id,
        "time_slot": time_slot,
        "num_trades": len(settled_trades),
        "penalty_results": penalty_results,
        "total_penalties": total_penalties,
    }
