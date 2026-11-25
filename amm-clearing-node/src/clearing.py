"""Core clearing algorithm — orchestrates the full market clearing cycle.

Steps:
0. Idempotency check (skip if the market already has trades)
1. Fetch open orders, translate int:Order → internal, validate inbound
2. Aggregate supply and demand
3. Compute the uniform clearing price via the sigmoid
4. Record the result on-chain via clearMarket() (optional / deferred)
5. Compute pro-rata quantity allocations, quantised to the on-chain resolution
6. Apply user preference allocation (mutual preferred pairs); 6b computes the
   optional energy-type adjustments for the summary only
7. Generate int:Trade objects: direct preference pairs, then the sequential
   fill of the remaining allocations into buyer↔seller matches
8. Post int:Trade list and the int:ClearingResult back to the off-chain DB

The AMM pool is the pricing and allocation mechanism: it sets the uniform price
and allocates the traded energy pro rata. It does not appear on the wire. Every
trade is a bilateral buyer↔seller match at the uniform clearing price; the
pairing reproduces every participant's allocation.
"""

import logging
import time

from src.adapters import (
    build_bilateral_int_trade,
    build_direct_int_trade,
    build_int_clearing_result,
    ct_to_eur,
    int_order_to_internal,
    unix_to_iso,
    wire_value,
)
from src.config import CommunityConfig
from src.contract import AMMContractClient
from src.decompose import apportion, order_key, sequential_fill
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
from src.sigmoid import from_node_int, sigmoid_price, to_node_int

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

    # Sorted by actor id, then order id, so every later step (rounding ties,
    # preference pairs, the fill) is independent of the order of arrival.
    open_orders = sorted((o for o in internal_orders if o.get("status") == "Open"), key=order_key)
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
                clearing_status="no_bid",
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

    # ── Step 5: Pro-rata allocation, quantised ───────────────────────
    # Quantities are integers of the on-chain resolution (1e-4 kWh). The
    # traded quantity is apportioned over each side by the largest-remainder
    # method, so both sides sum to the same integer total and the short side
    # receives exactly its order quantities.
    offer_units = [to_node_int(o["energy"]) for o in offers]
    bid_units = [to_node_int(b["energy"]) for b in bids]
    traded_units = min(sum(offer_units), sum(bid_units))
    for offer, units in zip(offers, apportion(offer_units, traded_units), strict=True):
        offer["allocated_energy"] = from_node_int(units)
    for bid, units in zip(bids, apportion(bid_units, traded_units), strict=True):
        bid["allocated_energy"] = from_node_int(units)

    # ── Step 6: Preference allocation (mutual preferred pairs) ────────
    bids, offers = apply_preference_allocation(bids, offers, clearing_price_ct)

    # ── Step 6b: Energy-type adjustments (summary only) ──────────────
    # A match has one price for both sides, so individual prices (energy-type
    # subsidy and levy, preferred rates, penalties) cannot go into the trade
    # price. They belong to the execution step; until it applies them, the
    # adjustments are computed for the clearing summary only.
    multipliers = None
    if community_config.green_subsidy_rate or community_config.grey_levy_rate:
        multipliers = EnergyTypeMultipliers(
            green_subsidy_rate=community_config.green_subsidy_rate,
            grey_levy_rate=community_config.grey_levy_rate,
            levy_cap_ct_per_kwh=community_config.levy_cap_ct_per_kwh,
        )
        logger.warning(
            "Market %s: energy-type differential pricing is configured, but trade "
            "prices stay at the clearing price; the adjustments are reported in "
            "the clearing summary only",
            market_id,
        )
    _, price_provenance = compute_seller_price_adjustments(offers, clearing_price_ct, multipliers)

    # ── Step 7: Generate int:Trade objects ───────────────────────────
    trades: list[dict] = []
    traded_trade_units = 0

    # 7a: Direct preference-matched trades (mutual pairs) at the clearing price
    for bid in bids:
        for match in bid.get("_preference_matches", []):
            units = to_node_int(match["energy"])
            if units <= 0:
                continue
            match["energy"] = from_node_int(units)
            trades.append(build_direct_int_trade(match, market_id, clearing_price_eur, traded_at))
            traded_trade_units += units

    # 7b: Sequential fill of the remaining allocations into buyer↔seller
    # matches at the clearing price (at most n + m − 1 trades)
    fills = sequential_fill(
        [(o, to_node_int(o.get("allocated_energy", 0.0))) for o in offers],
        [(b, to_node_int(b.get("allocated_energy", 0.0))) for b in bids],
    )
    for offer, bid, units in fills:
        trades.append(
            build_bilateral_int_trade(
                bid,
                offer,
                from_node_int(units),
                market_id,
                clearing_price_eur,
                traded_at,
            )
        )
        traded_trade_units += units

    # The clearing result states what the trades carry.
    traded_quantity = from_node_int(traded_trade_units)

    for trade in trades:
        validate_trade(trade)

    # ── Step 8: Post trades + clearing result ────────────────────────
    await db_client.post_trades(trades)
    await _post_clearing_result(
        db_client,
        build_int_clearing_result(
            market_id=market_id,
            clearing_status="final",
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
        # Wire values: the price and the traded quantity the trades carry.
        "clearing_price_eur_per_kwh": wire_value(clearing_price_eur),
        "traded_quantity_kwh": traded_quantity,
        "num_trades": len(trades),
        "tx_hash": tx_hash,
        # Energy-type adjustments (None when not configured or not applicable).
        # Reported here only: trade prices stay at the clearing price, and the
        # execution step is where individual prices are applied.
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
