"""Core clearing algorithm — orchestrates the full market clearing cycle.

Steps:
0. Idempotency check (skip if the market already has trades)
1. Fetch open orders, translate int:Order → internal, validate inbound
2. Aggregate supply and demand
3. Compute the uniform clearing price via the sigmoid
4. Record the result on-chain via clearMarket() (optional / deferred)
5. Compute pro-rata quantity allocations
6. Apply user preference allocation (mutual preferred pairs), then optional
   seller-side energy-type differential pricing (6b, zero-sum vs the pool)
7. Generate int:Trade objects (direct preference pairs, Buyer→Pool, Pool→Seller)
8. Post int:Trade list and the int:ClearingResult back to the off-chain DB

The AMM pool is a virtual counterparty: every participant trades with the pool
at the uniform clearing price, except preference-matched mutual pairs who trade
directly. Pool half-trades serialize to the bilateral int:Trade schema by
referencing a configured pool actor and deterministic pool standing orders.
"""

import logging
import time

from src.adapters import (
    build_buyer_pool_int_trade,
    build_direct_int_trade,
    build_int_clearing_result,
    build_pool_seller_int_trade,
    ct_to_eur,
    int_order_to_internal,
    pool_actor_uuid,
    pool_order_uuid,
    unix_to_iso,
)
from src.config import CommunityConfig
from src.contract import AMMContractClient
from src.offchain_db import OffchainDBClient
from src.ontology import (
    SchemaValidationError,
    validate_clearing_result,
    validate_order,
    validate_trade,
)
from src.preferences import (
    EnergyTypeMultipliers,
    apply_preference_allocation,
    compute_seller_price_adjustments,
)
from src.sigmoid import sigmoid_price

logger = logging.getLogger(__name__)


async def run_clearing(
    market_id: str,
    community_uuid: str,
    time_slot: int,
    community_config: CommunityConfig,
    db_client: OffchainDBClient,
    contract_client: AMMContractClient | None,
    time_slot_sec: int = 900,
    strict_validation: bool = True,
) -> dict:
    """Execute the full clearing cycle for a single market slot.

    ``strict_validation=False`` keeps inbound orders that fail int:Order
    validation (logging the violation) — needed against the GSY staging
    gateway while their DTOs are still being aligned with the ontology.

    Returns a summary dict with clearing results.
    """
    pool_actor = pool_actor_uuid(community_config.pool_actor_uuid)

    # ── Step 0: Idempotency check ────────────────────────────────────
    existing_trades = await db_client.get_trades(market_id)
    if existing_trades:
        logger.warning(
            "Trades already exist for market_id=%s, skipping clearing",
            market_id,
        )
        return {"status": "skipped", "reason": "trades_already_exist"}

    # ── Step 1: Fetch open orders + translate from the int:Order ontology ──
    start_time = time_slot
    end_time = time_slot + time_slot_sec
    raw_orders = await db_client.get_orders(market_id, start_time, end_time)

    internal_orders = []
    for raw in raw_orders:
        try:
            validate_order(raw)
        except SchemaValidationError:
            if strict_validation:
                logger.warning(
                    "Dropping order failing int:Order validation: %s",
                    raw.get("orderId", "<no id>"),
                    exc_info=True,
                )
                continue
            logger.warning(
                "Order %s fails int:Order validation; keeping it " "(strict_validation=False)",
                raw.get("orderId", "<no id>"),
                exc_info=True,
            )
        try:
            internal_orders.append(int_order_to_internal(raw))
        except Exception:
            logger.warning(
                "Dropping order that could not be converted: %s",
                raw.get("orderId", "<no id>"),
                exc_info=True,
            )

    open_orders = [o for o in internal_orders if o.get("status") == "Open"]
    bids = [o for o in open_orders if o.get("order_type") == "Bid"]
    offers = [o for o in open_orders if o.get("order_type") == "Offer"]

    logger.info(
        "Market %s: %d bids, %d offers (from %d orders)",
        market_id,
        len(bids),
        len(offers),
        len(raw_orders),
    )

    now = int(time.time())
    traded_at = unix_to_iso(now)

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
        await _post_clearing_result(
            db_client,
            build_int_clearing_result(
                market_id=market_id,
                clearing_status="NO_BID",
                clearing_price_eur=0.0,
                total_supply_kwh=total_supply_kwh,
                total_demand_kwh=total_demand_kwh,
                traded_quantity_kwh=0.0,
                num_trades=0,
                tx_hash="0x0",
                created_at_iso=traded_at,
                no_bid_reason="invalid_inputs",
            ),
        )
        return {
            "status": "no_trade",
            "total_supply_kwh": total_supply_kwh,
            "total_demand_kwh": total_demand_kwh,
        }

    # ── Step 3: Compute clearing price ───────────────────────────────
    ratio = total_supply_kwh / total_demand_kwh
    clearing_price_ct = sigmoid_price(
        ratio,
        community_config.k_upper_ct_per_kwh,
        community_config.k_lower_ct_per_kwh,
        community_config.theta,
        community_config.steepness,
    )
    clearing_price_eur = ct_to_eur(clearing_price_ct)

    logger.info(
        "Market %s: ratio=%.4f, clearing_price=%.4f ct/kWh",
        market_id,
        ratio,
        clearing_price_ct,
    )

    # ── Step 4: Record on-chain (optional; deferred for the MVP) ──────
    tx_hash = "0x0"
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
            logger.exception("On-chain clearMarket failed for market_id=%s", market_id)
            return {"status": "error", "reason": "on_chain_tx_failed"}
    else:
        logger.warning("No contract client configured, skipping on-chain recording")

    # ── Step 5: Pro-rata allocation ──────────────────────────────────
    traded_quantity = min(total_supply_kwh, total_demand_kwh)
    for offer in offers:
        offer["allocated_energy"] = (offer["energy"] / total_supply_kwh) * traded_quantity
    for bid in bids:
        bid["allocated_energy"] = (bid["energy"] / total_demand_kwh) * traded_quantity

    # ── Step 6: Preference allocation (mutual preferred pairs) ────────
    bids, offers = apply_preference_allocation(bids, offers, clearing_price_ct, traded_quantity)

    # ── Step 6b: Seller-side differential pricing (optional) ──────────
    # Green sellers receive clearing + subsidy, grey sellers clearing − levy
    # (zero-sum against the pool). Buyers and direct preference trades keep
    # the uniform clearing price. The adjusted price goes straight into the
    # wire tradePrice; provenance is returned in the clearing summary.
    multipliers = None
    if community_config.green_subsidy_rate or community_config.grey_levy_rate:
        multipliers = EnergyTypeMultipliers(
            green_subsidy_rate=community_config.green_subsidy_rate,
            grey_levy_rate=community_config.grey_levy_rate,
            levy_cap_ct_per_kwh=community_config.levy_cap_ct_per_kwh,
        )
    adjusted_seller_ct, price_provenance = compute_seller_price_adjustments(
        offers, clearing_price_ct, multipliers
    )

    # ── Step 7: Generate int:Trade objects ───────────────────────────
    pool_bid_id = pool_order_uuid(market_id, "bid")
    pool_offer_id = pool_order_uuid(market_id, "offer")
    trades: list[dict] = []

    # 7a: Direct preference-matched trades (buyer↔seller, no pool)
    for bid in bids:
        for match in bid.get("_preference_matches", []):
            trades.append(build_direct_int_trade(match, market_id, clearing_price_eur, traded_at))

    # 7b: Buyer → Pool for remaining allocated energy
    for bid in bids:
        if bid.get("allocated_energy", 0) > 1e-9:
            trades.append(
                build_buyer_pool_int_trade(
                    bid,
                    pool_actor,
                    pool_offer_id,
                    market_id,
                    clearing_price_eur,
                    traded_at,
                )
            )

    # 7c: Pool → Seller for remaining allocated energy (price may carry the
    # seller-side energy-type adjustment from step 6b)
    for offer in offers:
        if offer.get("allocated_energy", 0) > 1e-9:
            seller_price_eur = ct_to_eur(
                adjusted_seller_ct.get(offer["order_id"], clearing_price_ct)
            )
            trades.append(
                build_pool_seller_int_trade(
                    offer,
                    pool_actor,
                    pool_bid_id,
                    market_id,
                    seller_price_eur,
                    traded_at,
                )
            )

    for trade in trades:
        validate_trade(trade)

    # ── Step 8: Post trades + clearing result ────────────────────────
    await db_client.post_trades(trades)
    await _post_clearing_result(
        db_client,
        build_int_clearing_result(
            market_id=market_id,
            clearing_status="FINAL",
            clearing_price_eur=clearing_price_eur,
            total_supply_kwh=total_supply_kwh,
            total_demand_kwh=total_demand_kwh,
            traded_quantity_kwh=traded_quantity,
            num_trades=len(trades),
            tx_hash=tx_hash,
            created_at_iso=traded_at,
        ),
    )

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
        "clearing_price_eur_per_kwh": clearing_price_eur,
        "traded_quantity_kwh": traded_quantity,
        "num_trades": len(trades),
        "tx_hash": tx_hash,
        # Differential-pricing provenance (None when not applied). Kept out of
        # the int.* wire objects on purpose — internal fields over ontology
        # changes; a dedicated AMM topic can carry this later if needed.
        "price_adjustments": price_provenance,
    }


async def _post_clearing_result(db_client: OffchainDBClient, result: dict) -> None:
    """Validate and post an int:ClearingResult, tolerating older DB stubs."""
    validate_clearing_result(result)
    post = getattr(db_client, "post_clearing_result", None)
    if post is None:
        logger.debug("DB client has no post_clearing_result; skipping result post")
        return
    await post(result)
