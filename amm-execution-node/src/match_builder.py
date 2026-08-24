"""Build on-chain Match structs from an AMM clearing outcome.

Implements GSY's chosen pool representation (option (a), 2026-08-24): the
engine registers standing pool orders on-chain and settles matches against
them. Because ``_settleTrade`` flips both orders to Executed, one pool order
can settle exactly ONE match — so a distinct pool order is synthesized per
pool trade (deterministic UUID derived from the trade id).

Pool order pricing exploits the settlement invariant
``bid.energyRate ≥ clearingPrice ≥ offer.energyRate``: the pool's synthetic
bid is priced at the community ceiling (k_upper) and its synthetic offer at
the floor (k_lower), so the pool side can never cause a PriceMismatch for any
clearing price inside the band. Participant limit prices are NOT adjusted —
if a participant's limit conflicts with the clearing price the validator
flags it before any gas is spent (see validator.py; open design point with
GSY, since AMM clearing does not price-condition on limits).

Inputs are the clearing node's wire artifacts: the int:Trade list plus the
int:Order objects by id (for participant-side OrderData).
"""

import uuid
from dataclasses import dataclass

from src.structs import Match, OrderData, OrderParams

_POOL_SETTLE_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://ammba.uoc/settlement")


def pool_settle_order_uuid(trade_id: str) -> str:
    """Deterministic UUID for the pool order backing one settled match.

    Convention mirrors the clearing node's derived-UUID approach
    (amm-clearing-node/src/adapters.py) — keep the namespaces distinct but the
    style in sync.
    """
    return str(uuid.uuid5(_POOL_SETTLE_NS, f"pool-order:{trade_id}"))


@dataclass(frozen=True)
class BuildResult:
    matches: list[Match]
    pool_orders: list[OrderParams]  # standing orders that must exist on-chain


def _participant_order_data(order: dict, market_id: str) -> OrderData:
    """int:Order → OrderData (participant side, real registered order)."""
    from src.structs import scale  # local import to keep module deps flat

    del scale  # values stay floats here; scaling happens in to_tuple()
    return OrderData(
        order_id=order["orderId"],
        created_by=order["createdBy"],
        market_id=market_id,
        time_slot=_to_unix(order["timeSlot"]),
        creation_time=_to_unix(order["createdAt"]),
        energy_kwh=order["quantity"],
        energy_rate=order["priceLimit"],
        energy_source_preference=order.get("energySourcePreference"),
        energy_type=order.get("energyType"),
    )


def _to_unix(value) -> int:
    if isinstance(value, int | float):
        return int(value)
    from datetime import datetime

    return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())


def build_matches(
    trades: list[dict],
    orders_by_id: dict[str, dict],
    pool_actor_uuid: str,
    k_upper: float,
    k_lower: float,
    time_slot: int,
) -> BuildResult:
    """Transform int:Trade records into settleable matches + pool orders.

    ``k_upper``/``k_lower`` are the community price bounds in the same
    currency unit as the trades' ``tradePrice`` (unit decision pending at
    consortium level; this function is unit-agnostic).
    """
    matches: list[Match] = []
    pool_orders: list[OrderParams] = []

    for trade in trades:
        market_id = trade["marketId"]
        buyer_is_pool = trade["buyerId"] == pool_actor_uuid
        seller_is_pool = trade["sellerId"] == pool_actor_uuid

        if buyer_is_pool and seller_is_pool:
            raise ValueError(f"trade {trade['tradeId']} has the pool on both sides")

        if not buyer_is_pool and not seller_is_pool:
            # Direct preference pair — both orders are real and registered.
            bid = _participant_order_data(orders_by_id[trade["bidId"]], market_id)
            offer = _participant_order_data(orders_by_id[trade["offerId"]], market_id)
        elif seller_is_pool:
            # Buyer → Pool: real bid, synthetic pool offer priced at the floor.
            bid = _participant_order_data(orders_by_id[trade["bidId"]], market_id)
            offer = OrderData(
                order_id=pool_settle_order_uuid(trade["tradeId"]),
                created_by=pool_actor_uuid,
                market_id=market_id,
                time_slot=bid.time_slot,
                creation_time=bid.creation_time,
                energy_kwh=trade["tradeQuantity"],
                energy_rate=k_lower,
            )
            pool_orders.append(OrderParams(order=offer, is_bid=False))
        else:
            # Pool → Seller: synthetic pool bid priced at the ceiling.
            offer = _participant_order_data(orders_by_id[trade["offerId"]], market_id)
            bid = OrderData(
                order_id=pool_settle_order_uuid(trade["tradeId"]),
                created_by=pool_actor_uuid,
                market_id=market_id,
                time_slot=offer.time_slot,
                creation_time=offer.creation_time,
                energy_kwh=trade["tradeQuantity"],
                energy_rate=k_upper,
            )
            pool_orders.append(OrderParams(order=bid, is_bid=True))

        matches.append(
            Match(
                trade_id=trade["tradeId"],
                bid=bid,
                offer=offer,
                selected_energy_kwh=trade["tradeQuantity"],
                clearing_price=trade["tradePrice"],
            )
        )

    del time_slot  # reserved: cross-check against order time slots if desired
    return BuildResult(matches=matches, pool_orders=pool_orders)
