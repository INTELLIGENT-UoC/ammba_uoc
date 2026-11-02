"""Build on-chain market settlements from an AMM clearing outcome.

Implements the pool representation agreed with GSY (option (a), 2026-08-24):
the engine registers standing pool orders on-chain and settles matches against
them. Because settlement marks both orders as executed, one pool order can
settle exactly ONE match — so a distinct pool order is synthesized per pool
trade (deterministic UUID derived from the trade id).

Pool order pricing exploits the settlement invariant for ``Standard`` matches,
``bid.energyRate ≥ clearingPrice ≥ offer.energyRate``: the pool's synthetic
bid is priced at the community ceiling (k_upper) and its synthetic offer at
the floor (k_lower), so the pool side can never cause a PriceMismatch for any
clearing price inside the band. Participant limit prices are NOT adjusted —
if a participant's limit conflicts with the clearing price the validator
flags it before any gas is spent (see validator.py; AMM clearing does not
price-condition on limits). Direct trades of mutual preferred partners are
``Preferred`` matches.

``settleBatch`` takes one ``MarketSettlement`` per market: the market's
matches and its clearing result, built from the clearing node's
``int:ClearingResult``. A participant order that a match fills only partly
leaves a residual order, which the registry creates under a fresh id; a later
match of the same order (for example the pool leg after a direct preference
trade) consumes that residual.

Inputs are the clearing node's wire artifacts: the int:Trade list, the
int:Order objects by id and the int:ClearingResult of each market.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from src.ids import uuid_to_bytes16
from src.structs import (
    MATCH_TYPE_PREFERRED,
    MATCH_TYPE_STANDARD,
    SCALING_FACTOR,
    ClearingResult,
    MarketSettlement,
    Match,
    OrderParams,
    scale,
)

_POOL_SETTLE_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://ammba.uoc/settlement")


def pool_settle_order_uuid(trade_id: str) -> str:
    """Deterministic UUID for the pool order backing one settled match.

    Convention mirrors the clearing node's derived-UUID approach
    (amm-clearing-node/src/adapters.py) — keep the namespaces distinct but the
    style in sync.
    """
    return str(uuid.uuid5(_POOL_SETTLE_NS, f"pool-order:{trade_id}"))


def residual_order_uuid(order_id: str, trade_id: str) -> str:
    """Deterministic id for the residual an order leaves after one match."""
    return str(uuid.uuid5(_POOL_SETTLE_NS, f"residual:{order_id}:{trade_id}"))


@dataclass(frozen=True)
class BuildResult:
    settlements: list[MarketSettlement]
    pool_orders: list[OrderParams] = field(default_factory=list)  # must exist on-chain

    @property
    def matches(self) -> list[Match]:
        return [m for s in self.settlements for m in s.matches]


def _to_unix(value) -> int:
    if isinstance(value, int | float):
        return int(value)
    return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())


def _participant_params(order: dict, is_bid: bool) -> OrderParams:
    """int:Order → OrderParams, as the GSY DEX community client registered it."""
    return OrderParams(
        order_id=order["orderId"],
        created_by=order["createdBy"],
        market_id=order["marketId"],
        time_slot=_to_unix(order["timeSlot"]),
        creation_time=_to_unix(order.get("creationTime", order.get("createdAt"))),
        energy_kwh=order["quantity"],
        energy_rate=order["priceLimit"],
        is_bid=is_bid,
        energy_source_preference=order.get("energySourcePreference"),
        energy_type=order.get("energyType"),
        preferred_trading_partner=order.get("preferredTradingPartner"),
        preferred_energy_rate=order.get("preferredEnergyRate"),
    )


def _clearing_result(result: dict, num_trades: int) -> ClearingResult:
    return ClearingResult(
        market_id=result["marketId"],
        clearing_status=str(result["clearingStatus"]).lower(),
        clearing_price=result["clearingPrice"],
        total_supply_kwh=result["totalSupply"],
        total_demand_kwh=result["totalDemand"],
        traded_quantity_kwh=result.get("tradeQuantity", result.get("tradedQuantity")),
        num_trades=num_trades,
    )


def build_settlements(
    trades: list[dict],
    orders_by_id: dict[str, dict],
    clearing_results: list[dict],
    pool_actor_uuid: str,
    k_upper: float,
    k_lower: float,
) -> BuildResult:
    """Transform int:Trade records into one MarketSettlement per market.

    ``k_upper``/``k_lower`` are the community price bounds in EUR/kWh, the unit
    of the trades' ``tradePrice``.
    """
    results_by_market = {uuid_to_bytes16(r["marketId"]): r for r in clearing_results}
    live: dict[str, OrderParams] = {}  # original order id -> its current (residual) form
    matches_by_market: dict[bytes, list[Match]] = {}
    pool_orders: list[OrderParams] = []

    def take(order: dict, is_bid: bool, quantity: float, trade_id: str):
        """The order (or its residual) a match consumes, and the residual id it leaves."""
        key = order["orderId"]
        current = live.get(key) or _participant_params(order, is_bid)
        remaining = scale(current.energy_kwh) - scale(quantity)
        if remaining > 0:
            residual_id = residual_order_uuid(key, trade_id)
            live[key] = current.residual(residual_id, remaining / SCALING_FACTOR)
            return current, residual_id
        live[key] = current  # fully filled (or over-allocated: the validator flags it)
        return current, None

    for trade in trades:
        trade_id = trade["tradeId"]
        quantity = trade["tradeQuantity"]
        buyer_is_pool = trade["buyerId"] == pool_actor_uuid
        seller_is_pool = trade["sellerId"] == pool_actor_uuid
        if buyer_is_pool and seller_is_pool:
            raise ValueError(f"trade {trade_id} has the pool on both sides")

        residual_bid = residual_offer = None
        if not buyer_is_pool and not seller_is_pool:
            # Direct trade of mutual preferred partners — two registered orders.
            bid, residual_bid = take(orders_by_id[trade["bidId"]], True, quantity, trade_id)
            offer, residual_offer = take(orders_by_id[trade["offerId"]], False, quantity, trade_id)
            match_type = MATCH_TYPE_PREFERRED
        elif seller_is_pool:
            # Buyer → Pool: real bid, synthetic pool offer priced at the floor.
            bid, residual_bid = take(orders_by_id[trade["bidId"]], True, quantity, trade_id)
            offer = OrderParams(
                order_id=pool_settle_order_uuid(trade_id),
                created_by=pool_actor_uuid,
                market_id=bid.market_id,
                time_slot=bid.time_slot,
                creation_time=bid.creation_time,
                energy_kwh=quantity,
                energy_rate=k_lower,
                is_bid=False,
            )
            pool_orders.append(offer)
            match_type = MATCH_TYPE_STANDARD
        else:
            # Pool → Seller: synthetic pool bid priced at the ceiling.
            offer, residual_offer = take(orders_by_id[trade["offerId"]], False, quantity, trade_id)
            bid = OrderParams(
                order_id=pool_settle_order_uuid(trade_id),
                created_by=pool_actor_uuid,
                market_id=offer.market_id,
                time_slot=offer.time_slot,
                creation_time=offer.creation_time,
                energy_kwh=quantity,
                energy_rate=k_upper,
                is_bid=True,
            )
            pool_orders.append(bid)
            match_type = MATCH_TYPE_STANDARD

        match = Match(
            trade_id=trade_id,
            bid=bid,
            offer=offer,
            selected_energy_kwh=quantity,
            clearing_price=trade["tradePrice"],
            residual_bid_id=residual_bid,
            residual_offer_id=residual_offer,
            match_type=match_type,
        )
        matches_by_market.setdefault(uuid_to_bytes16(trade["marketId"]), []).append(match)

    settlements = []
    for market, matches in matches_by_market.items():
        if market not in results_by_market:
            raise ValueError(f"no clearing result for market 0x{market.hex()}")
        result = results_by_market[market]
        settlements.append(
            MarketSettlement(
                market_id=result["marketId"],
                matches=tuple(matches),
                clearing_result=_clearing_result(result, len(matches)),
            )
        )
    return BuildResult(settlements=settlements, pool_orders=pool_orders)
