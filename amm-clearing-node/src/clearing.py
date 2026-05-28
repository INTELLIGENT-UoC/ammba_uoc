"""Core clearing algorithm — orchestrates the full market clearing cycle.

Steps (from IMPLEMENTATION_GUIDE.md Section 4.4):
1. Fetch open orders for the closing market slot
2. Aggregate supply and demand
3. Compute clearing price using sigmoid
4. Call the AMM Smart Contract (record on-chain)
5. Compute pro-rata quantity allocations
6. Apply user preference allocation (Phase 2)
7. Generate trade objects (Buyer→Pool and Pool→Seller)
8. POST trades to off-chain DB
"""

import logging

from src.config import CommunityConfig
from src.contract import AMMContractClient
from src.offchain_db import OffchainDBClient
from src.preferences import (
    EnergyTypeMultipliers,
    apply_energy_type_multipliers,
    apply_preference_allocation,
)
from src.sigmoid import sigmoid_price
from src.trade_builder import (
    build_buyer_pool_trade,
    build_direct_preference_trade,
    build_pool_seller_trade,
)

logger = logging.getLogger(__name__)


async def run_clearing(
    market_id: str,
    community_uuid: str,
    time_slot: int,
    community_config: CommunityConfig,
    db_client: OffchainDBClient,
    contract_client: AMMContractClient | None,
    time_slot_sec: int = 900,
    energy_type_multipliers: EnergyTypeMultipliers | None = None,
) -> dict:
    """Execute the full clearing cycle for a single market slot.

    Returns a summary dict with clearing results.
    """
    pool_id = community_config.pool_id

    # ── Step 0: Idempotency check ────────────────────────────────────
    existing_trades = await db_client.get_trades(market_id)
    if existing_trades:
        logger.warning(
            "Trades already exist for market_id=%s, skipping clearing",
            market_id,
        )
        return {"status": "skipped", "reason": "trades_already_exist"}

    # ── Step 1: Fetch open orders ────────────────────────────────────
    start_time = time_slot
    end_time = time_slot + time_slot_sec
    all_orders = await db_client.get_orders(market_id, start_time, end_time)

    # Filter for Open orders only
    open_orders = [o for o in all_orders if o.get("status") == "Open"]

    bids = [o for o in open_orders if o.get("order_type") == "Bid"]
    offers = [o for o in open_orders if o.get("order_type") == "Offer"]

    logger.info(
        "Market %s: %d bids, %d offers (from %d total orders)",
        market_id,
        len(bids),
        len(offers),
        len(all_orders),
    )

    # ── Step 2: Aggregate ────────────────────────────────────────────
    total_supply_kwh = sum(o["energy"] for o in offers)
    total_demand_kwh = sum(b["energy"] for b in bids)

    if total_supply_kwh == 0 or total_demand_kwh == 0:
        logger.info(
            "Market %s: no trade (supply=%.3f, demand=%.3f)",
            market_id,
            total_supply_kwh,
            total_demand_kwh,
        )
        return {
            "status": "no_trade",
            "total_supply_kwh": total_supply_kwh,
            "total_demand_kwh": total_demand_kwh,
        }

    # ── Step 3: Compute clearing price ───────────────────────────────
    ratio = total_supply_kwh / total_demand_kwh
    k_upper = community_config.k_upper_ct_per_kwh
    k_lower = community_config.k_lower_ct_per_kwh
    theta = community_config.theta
    steepness = community_config.steepness

    clearing_price_ct = sigmoid_price(ratio, k_upper, k_lower, theta, steepness)

    logger.info(
        "Market %s: ratio=%.4f, clearing_price=%.4f ct/kWh",
        market_id,
        ratio,
        clearing_price_ct,
    )

    # ── Step 4: Record on-chain ──────────────────────────────────────
    tx_hash = "0x0"  # Default for when contract client is not available
    if contract_client is not None:
        try:
            tx_hash = await contract_client.clear_market(
                market_id=market_id,
                community_uuid=community_uuid,
                time_slot=time_slot,
                total_supply_kwh=total_supply_kwh,
                total_demand_kwh=total_demand_kwh,
                clearing_price=clearing_price_ct,
            )
        except Exception:
            logger.exception(
                "On-chain clearMarket failed for market_id=%s", market_id
            )
            return {"status": "error", "reason": "on_chain_tx_failed"}
    else:
        logger.warning("No contract client configured, skipping on-chain recording")

    # ── Step 5: Pro-rata allocation ──────────────────────────────────
    traded_quantity = min(total_supply_kwh, total_demand_kwh)

    for offer in offers:
        offer["allocated_energy"] = (
            (offer["energy"] / total_supply_kwh) * traded_quantity
        )

    for bid in bids:
        bid["allocated_energy"] = (
            (bid["energy"] / total_demand_kwh) * traded_quantity
        )

    # ── Step 6: Preference allocation (Phase 2 stub) ─────────────────
    bids, offers = apply_preference_allocation(
        bids, offers, clearing_price_ct, traded_quantity
    )

    # ── Step 7: Generate trade objects ───────────────────────────────
    trades = []

    # 7a: Generate direct preference-matched trades (buyer↔seller, no pool)
    for bid in bids:
        for match in bid.get("_preference_matches", []):
            trade = build_direct_preference_trade(
                match=match,
                market_id=market_id,
                time_slot=time_slot,
                tx_hash=tx_hash,
                theta=theta,
                steepness=steepness,
                total_supply_kwh=total_supply_kwh,
                total_demand_kwh=total_demand_kwh,
            )
            trades.append(trade)

    # 7b: Trade A — Buyer → Pool (for remaining allocated_energy after preferences)
    for bid in bids:
        if bid.get("allocated_energy", 0) > 1e-9:
            trade = build_buyer_pool_trade(
                bid=bid,
                pool_id=pool_id,
                market_id=market_id,
                time_slot=time_slot,
                clearing_price=clearing_price_ct,
                tx_hash=tx_hash,
                theta=theta,
                steepness=steepness,
                total_supply_kwh=total_supply_kwh,
                total_demand_kwh=total_demand_kwh,
            )
            trades.append(trade)

    # 7c: Trade B — Pool → Seller (for remaining allocated_energy after preferences)
    for offer in offers:
        if offer.get("allocated_energy", 0) > 1e-9:
            trade = build_pool_seller_trade(
                offer=offer,
                pool_id=pool_id,
                market_id=market_id,
                time_slot=time_slot,
                clearing_price=clearing_price_ct,
                tx_hash=tx_hash,
                theta=theta,
                steepness=steepness,
                total_supply_kwh=total_supply_kwh,
                total_demand_kwh=total_demand_kwh,
            )
            trades.append(trade)

    # ── Step 7d: Apply energy type multipliers ─────────────────────
    if energy_type_multipliers is not None:
        trades = apply_energy_type_multipliers(
            trades, bids, offers, clearing_price_ct, energy_type_multipliers
        )

    # ── Step 8: POST trades ──────────────────────────────────────────
    await db_client.post_trades(trades)

    logger.info(
        "Market %s cleared: %d trades, price=%.4f ct/kWh, tx=%s",
        market_id,
        len(trades),
        clearing_price_ct,
        tx_hash,
    )

    return {
        "status": "cleared",
        "market_id": market_id,
        "total_supply_kwh": total_supply_kwh,
        "total_demand_kwh": total_demand_kwh,
        "clearing_price_ct_per_kwh": clearing_price_ct,
        "traded_quantity_kwh": traded_quantity,
        "num_trades": len(trades),
        "tx_hash": tx_hash,
    }
