"""Translation between the GSY DEX ``int.*`` ontology and the internal shape.

The clearing algorithm (``clearing.py``, ``preferences.py``) works on a flat
internal order dict using AMM-native names (``energy``, ``energy_rate``,
``status``, ``order_type``, nested ``requirements`` / ``attributes``). The wire
contract is the ``int.*`` ontology: camelCase, ISO-8601 timestamps, flat
preference fields, EUR/kWh prices, UUID identifiers.

Everything that crosses the service boundary is converted here so the rest of
the codebase never sees ontology field names, and a future transport change
(REST today, EW CGW publish/poll later) only touches this module plus the
client. Keeping the mapping in one place also makes the open alignment questions
with GSY (price units, the pool actor / pool order representation, which order
statuses count as matchable) explicit and easy to revisit.
"""

import uuid
from datetime import UTC, datetime

# Internal prices are in ct/kWh (matches the sigmoid community bounds); the
# ontology carries EUR/kWh. Convert only at the boundary.
CT_PER_EUR = 100.0

# int:Order.orderStatus values that the AMM treats as open and eligible to
# match. GSY confirmed "Submitted" is the ontology's representation of the open
# status. (PartiallyFilled is not expected in the batch-AMM flow — orders are
# fresh each slot; revisit if partial fills ever reach the AMM.)
MATCHABLE_ORDER_STATUSES = {"Submitted"}
INTERNAL_OPEN = "Open"

# Deterministic namespace for derived UUIDs (pool actor, pool orders, trade ids).
# Fixed so re-running a clearing cycle yields identical identifiers (idempotency).
_AMMBA_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://ammba.uoc/ontology")


def ct_to_eur(value_ct: float) -> float:
    return value_ct / CT_PER_EUR


def iso_to_unix(value: str) -> int:
    """Parse an ISO-8601 timestamp (``Z`` or offset) to a unix second."""
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def unix_to_iso(value: int) -> str:
    """Render a unix second as an ISO-8601 UTC timestamp with a ``Z`` suffix."""
    return datetime.fromtimestamp(value, tz=UTC).isoformat().replace("+00:00", "Z")


def pool_actor_uuid(community_pool_uuid: str) -> str:
    """The pool's actor identity. Configured per community; passed through."""
    return community_pool_uuid


def pool_order_uuid(market_id: str, side: str) -> str:
    """Deterministic UUID for the pool's standing order on a side of a market.

    The AMM pool is a virtual counterparty: it does not submit real orders, but
    ``int:Trade`` requires both a ``bidId`` and an ``offerId``. We model the pool
    as holding one standing bid and one standing offer per market slot, with
    stable derived UUIDs. Provisional convention pending GSY's pool-registration
    decision.
    """
    return str(uuid.uuid5(_AMMBA_NS, f"pool-order:{side}:{market_id}"))


def trade_uuid(market_id: str, kind: str, key: str) -> str:
    """Deterministic ``tradeId`` so a re-run produces stable identifiers."""
    return str(uuid.uuid5(_AMMBA_NS, f"trade:{market_id}:{kind}:{key}"))


def int_order_to_internal(order: dict) -> dict:
    """Convert a validated ``int:Order`` into the internal order dict.

    ``int:Order`` carries no area, so ``area_uuid`` falls back to the actor; it
    is internal-only book-keeping and never leaves the node (``int:Trade`` is
    flat and references actors and orders by UUID, not areas).
    """
    status = order.get("orderStatus")
    internal_status = INTERNAL_OPEN if status in MATCHABLE_ORDER_STATUSES else status

    internal = {
        "order_id": order["orderId"],
        "market_id": order["marketId"],
        "order_type": order["orderType"],
        "status": internal_status,
        "created_by": order["createdBy"],
        "area_uuid": order["createdBy"],
        "time_slot": iso_to_unix(order["timeSlot"]),
        "creation_time": iso_to_unix(order["createdAt"]),
        "energy": order["quantity"],
        # priceLimit is EUR/kWh; the AMM pool sets price from the supply/demand
        # ratio and does not use limit prices, so it is carried only for record.
        "energy_rate": order.get("priceLimit"),
    }

    requirements: dict = {}
    if order.get("preferredTradingPartner"):
        requirements["trading_partner_id"] = [order["preferredTradingPartner"]]
    if order.get("energySourcePreference"):
        requirements["energy_source"] = [order["energySourcePreference"]]
    if requirements:
        internal["requirements"] = requirements

    if order.get("energyType"):
        internal["attributes"] = {"energy_type": [order["energyType"]]}

    return internal


def _int_trade(
    trade_id: str,
    market_id: str,
    bid_id: str,
    buyer_id: str,
    offer_id: str,
    seller_id: str,
    quantity: float,
    price_eur: float,
    traded_at_iso: str,
    status: str = "settled",
) -> dict:
    """Assemble a flat ``int:Trade`` object."""
    return {
        "tradeId": trade_id,
        "marketId": market_id,
        "bidId": bid_id,
        "buyerId": buyer_id,
        "offerId": offer_id,
        "sellerId": seller_id,
        "tradeStatus": status,
        "tradeQuantity": quantity,
        "tradePrice": price_eur,
        "tradedAt": traded_at_iso,
    }


def build_direct_int_trade(
    match: dict,
    market_id: str,
    price_eur: float,
    traded_at_iso: str,
) -> dict:
    """``int:Trade`` for a preference-matched mutual pair (direct buyer↔seller)."""
    return _int_trade(
        trade_id=trade_uuid(
            market_id, "pref", f"{match['bid_order_id']}:{match['offer_order_id']}"
        ),
        market_id=market_id,
        bid_id=match["bid_order_id"],
        buyer_id=match["buyer"],
        offer_id=match["offer_order_id"],
        seller_id=match["seller"],
        quantity=match["energy"],
        price_eur=price_eur,
        traded_at_iso=traded_at_iso,
    )


def build_buyer_pool_int_trade(
    bid: dict,
    pool_actor: str,
    pool_offer_id: str,
    market_id: str,
    price_eur: float,
    traded_at_iso: str,
) -> dict:
    """``int:Trade`` for Buyer → Pool: the buyer's order vs the pool's offer."""
    return _int_trade(
        trade_id=trade_uuid(market_id, "buyer-pool", bid["order_id"]),
        market_id=market_id,
        bid_id=bid["order_id"],
        buyer_id=bid["created_by"],
        offer_id=pool_offer_id,
        seller_id=pool_actor,
        quantity=bid["allocated_energy"],
        price_eur=price_eur,
        traded_at_iso=traded_at_iso,
    )


def build_pool_seller_int_trade(
    offer: dict,
    pool_actor: str,
    pool_bid_id: str,
    market_id: str,
    price_eur: float,
    traded_at_iso: str,
) -> dict:
    """``int:Trade`` for Pool → Seller: the pool's bid vs the seller's order."""
    return _int_trade(
        trade_id=trade_uuid(market_id, "pool-seller", offer["order_id"]),
        market_id=market_id,
        bid_id=pool_bid_id,
        buyer_id=pool_actor,
        offer_id=offer["order_id"],
        seller_id=offer["created_by"],
        quantity=offer["allocated_energy"],
        price_eur=price_eur,
        traded_at_iso=traded_at_iso,
    )


def build_int_clearing_result(
    market_id: str,
    clearing_status: str,
    clearing_price_eur: float,
    total_supply_kwh: float,
    total_demand_kwh: float,
    traded_quantity_kwh: float,
    num_trades: int,
    tx_hash: str,
    created_at_iso: str,
    no_bid_reason: str | None = None,
) -> dict:
    """Assemble an ``int:ClearingResult`` for the market slot."""
    return {
        "marketId": market_id,
        "clearingStatus": clearing_status,
        "noBidReason": no_bid_reason,
        "clearingPrice": clearing_price_eur,
        "totalSupply": total_supply_kwh,
        "totalDemand": total_demand_kwh,
        "tradedQuantity": traded_quantity_kwh,
        "numTrades": num_trades,
        "txHash": tx_hash,
        "createdAt": created_at_iso,
    }
