"""Translation between the GSY DEX ``int.*`` ontology and the internal shape.

The clearing algorithm (``clearing.py``, ``preferences.py``) works on a flat
internal order dict using AMM-native names (``energy``, ``energy_rate``,
``status``, ``order_type``, nested ``requirements`` / ``attributes``). The wire
contract is the ``int.*`` ontology: camelCase, ISO-8601 timestamps, flat
preference fields, EUR/kWh prices, UUID identifiers.

Everything that crosses the service boundary is converted here so the rest of
the codebase never sees ontology field names, and both transports (direct REST
and EWDS publish/poll) share one mapping. Keeping the mapping in one place also
keeps the integration conventions (price units, the pool actor / pool order
representation, which order statuses count as matchable) explicit and easy to
revisit.
"""

import uuid
from datetime import UTC, datetime

# Internal prices are in ct/kWh (matches the sigmoid community bounds); the
# ontology carries EUR/kWh. Convert only at the boundary.
CT_PER_EUR = 100.0

# int:Order.orderStatus values that the AMM treats as open and eligible to
# match: "submitted" is the ontology's open status. (partially_filled is not
# expected in the batch-AMM flow — orders are fresh each slot; revisit if
# partial fills ever reach the AMM.)
MATCHABLE_ORDER_STATUSES = {"submitted"}
INTERNAL_OPEN = "Open"

# int:Trade.tradeStatus of a trade produced by clearing. "matched": the trade is
# allocated but not yet settled on-chain (settlement sets "settled").
CLEARED_TRADE_STATUS = "matched"

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


def storage_market_id(market_id: str) -> str:
    """The ``0x``-hex form the off-chain storage uses for market (and order) IDs.

    Markets are announced with UUID IDs, while orders and trades carry the same
    16 bytes as ``0x`` + 32 hex digits, and ``orders.query`` / ``trades.query``
    match the stored form literally. Accepts either form; anything else is
    returned unchanged so the storage reports it.
    """
    text = market_id.strip()
    try:
        return "0x" + uuid.UUID(text).hex
    except ValueError:
        pass
    hex_part = text[2:] if text.lower().startswith("0x") else text
    if len(hex_part) == 32:
        try:
            int(hex_part, 16)
            return "0x" + hex_part.lower()
        except ValueError:
            pass
    return text


def pool_actor_uuid(community_pool_uuid: str) -> str:
    """The pool's actor identity. Configured per community; passed through."""
    return community_pool_uuid


def pool_order_uuid(market_id: str, side: str) -> str:
    """Deterministic UUID for the pool's standing order on a side of a market.

    The AMM pool is a virtual counterparty: it does not submit real orders, but
    ``int:Trade`` requires both a ``bidId`` and an ``offerId``. We model the pool
    as holding one standing bid and one standing offer per market slot, with
    stable derived UUIDs. On-chain, the settlement engine registers one
    synthetic pool order per pool trade instead (see amm-execution-node).
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
        # Internal order types keep the capitalised "Bid" / "Offer".
        "order_type": order["orderType"].capitalize(),
        "status": internal_status,
        "created_by": order["createdBy"],
        "area_uuid": order["createdBy"],
        "time_slot": iso_to_unix(order["timeSlot"]),
        "creation_time": iso_to_unix(order["creationTime"]),
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


# The current EWDS order DTO follows the int:Order ontology (camelCase,
# lower-case enums, RFC 3339 times). Older handler versions emitted other
# dialects ("status": "open", PascalCase enums, nested requirements/attributes,
# unix timestamps, "createdAt"); ewds_order_to_int_order still accepts them and
# always returns the canonical int:Order shape, so the rest of the pipeline
# stays on the single ontology contract. See docs/integration/ewds.md.
_EWDS_STATUS_TO_ONTOLOGY = {
    "open": "submitted",  # legacy DB status for an open order
    "submitted": "submitted",
    "partially_filled": "partially_filled",
    "partiallyfilled": "partially_filled",
    "filled": "filled",
    "cancelled": "cancelled",
    "deleted": "cancelled",  # legacy DB status with no ontology home
    "expired": "expired",
    "rejected": "rejected",
    "executed": "executed",
}


def _first(order: dict, *keys: str):
    """First non-null value among aliases (camelCase and snake_case)."""
    for key in keys:
        if order.get(key) is not None:
            return order[key]
    return None


def _to_iso(value) -> str | None:
    """Normalize a unix int or ISO string timestamp to ISO-8601 ``Z`` form."""
    if value is None:
        return None
    if isinstance(value, int | float):
        return unix_to_iso(int(value))
    return value


_ENERGY_ENUM = {"GREEN", "PV", "HYDRO", "BIOMASS", "BATTERY"}


def _normalize_energy(value) -> str | None:
    """Map DTO energy-type values onto the ontology enum casing.

    An absent energy type arrives as the value "NONE" (or "None"/null); it
    becomes an *absent* field. Unknown non-empty values (including "GREY",
    which the ontology no longer lists) pass through unchanged so ontology
    validation surfaces them.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in ("NONE", "NULL"):
        return None
    return text.upper() if text.upper() in _ENERGY_ENUM else text


def ewds_order_to_int_order(dto: dict) -> dict:
    """Normalize an EWDS order DTO (any known dialect) to int:Order shape.

    Tolerant on input, canonical on output. Unknown/extra DTO fields (areaUuid,
    nonce, rejectReason, ...) are dropped — int:Order is additionalProperties:
    false. Raises KeyError/TypeError on structurally unusable input; callers
    skip-and-log per order.
    """
    order_type = str(_first(dto, "orderType", "order_type")).lower()

    raw_status = _first(dto, "orderStatus", "order_status", "status") or "submitted"
    status = _EWDS_STATUS_TO_ONTOLOGY.get(str(raw_status).lower(), str(raw_status))

    requirements = dto.get("requirements") or {}
    attributes = dto.get("attributes") or {}

    partner = _first(dto, "preferredTradingPartner", "preferred_trading_partner")
    if partner is None:
        partner = _first(requirements, "tradingPartnerId", "trading_partner_id")

    source_pref = _first(dto, "energySourcePreference", "energy_source_preference")
    if source_pref is None:
        source_pref = _first(requirements, "energyType", "energy_type")

    energy_type = _first(dto, "energyType", "energy_type")
    if energy_type is None:
        energy_type = _first(attributes, "energyType", "energy_type")

    normalized = {
        "orderId": _first(dto, "orderId", "order_id"),
        "marketId": _first(dto, "marketId", "market_id"),
        "orderType": order_type,
        "orderStatus": status,
        "timeSlot": _to_iso(_first(dto, "timeSlot", "time_slot")),
        "quantity": _first(dto, "quantity", "energy_kWh", "energy"),
        "priceLimit": _first(dto, "priceLimit", "price_limit", "energy_rate"),
        "createdBy": _first(dto, "createdBy", "created_by"),
        "creationTime": _to_iso(
            _first(dto, "creationTime", "creation_time", "createdAt", "created_at")
        ),
    }
    if partner is not None:
        normalized["preferredTradingPartner"] = partner
    preferred_rate = _first(dto, "preferredEnergyRate", "preferred_energy_rate")
    if preferred_rate is not None:
        normalized["preferredEnergyRate"] = preferred_rate
    source_pref = _normalize_energy(source_pref)
    if source_pref is not None:
        normalized["energySourcePreference"] = source_pref
    energy_type = _normalize_energy(energy_type)
    if energy_type is not None:
        normalized["energyType"] = energy_type

    return normalized


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
    status: str = CLEARED_TRADE_STATUS,
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
        "timestamp": traded_at_iso,
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
        "tradeQuantity": traded_quantity_kwh,
        "numTrades": num_trades,
        "txHash": tx_hash,
        "createdAt": created_at_iso,
    }


def _to_unix(value) -> int | None:
    """Normalize an ISO string or unix int timestamp to a unix second."""
    if value is None:
        return None
    if isinstance(value, str):
        return iso_to_unix(value)
    return int(value)


def ewds_market_to_internal(dto: dict) -> dict:
    """Normalize a market DTO (int:Market or the older MarketSchema dialect).

    ``markets.query`` returns int:Market: camelCase, UUID ``marketId``, RFC 3339
    times and a lower-case ``matchingAlgorithm`` ("amm"). The snake_case
    MarketSchema dialect is still accepted; times become unix seconds
    internally.
    """
    return {
        "market_id": _first(dto, "marketId", "market_id"),
        "community_id": _first(dto, "communityId", "community_id"),
        "opening_time": _to_unix(_first(dto, "openingTime", "opening_time")),
        "closing_time": _to_unix(_first(dto, "closingTime", "closing_time")),
        "delivery_start_time": _to_unix(_first(dto, "deliveryStartTime", "delivery_start_time")),
        "delivery_end_time": _to_unix(_first(dto, "deliveryEndTime", "delivery_end_time")),
        "matching_algorithm": str(
            _first(dto, "matchingAlgorithm", "matching_algorithm") or ""
        ).lower(),
    }
