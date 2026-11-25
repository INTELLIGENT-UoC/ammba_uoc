"""Build on-chain market settlements from an AMM clearing outcome.

The clearing node emits bilateral trades only: every ``int:Trade`` pairs a
participant bid with a participant offer at the uniform clearing price. Each
trade becomes one on-chain ``Match`` between the two registered orders; no
synthetic orders are needed.

- **Match type.** A trade whose two orders name each other as preferred
  trading partners is a ``Preferred`` match (the clearing node's direct trade
  of a mutual pair); every other trade is a ``Standard`` match. The clearing
  node exhausts one side of a mutual pair in its preference step, so the same
  two orders never meet again in the sequential fill.
- **Limit prices.** ``Standard`` matches require
  ``bid.energyRate ≥ clearingPrice ≥ offer.energyRate``. AMM clearing does
  not price-condition on limits, so a participant whose limit conflicts with
  the clearing price is flagged by the validator before any gas is spent
  (see validator.py).
- **Residual chaining.** A participant order that a match fills only partly
  leaves a residual order, which the registry creates under a fresh id; a
  later match of the same order (for example a fill match after a direct
  preference trade) consumes that residual.

``settleBatch`` takes one ``MarketSettlement`` per market: the market's
matches and its clearing result, built from the clearing node's
``int:ClearingResult``. Because every match is bilateral, the selected energy
of a market's matches sums to its traded quantity.

Inputs are the clearing node's wire artifacts: the int:Trade list, the
int:Order objects by id and the int:ClearingResult of each market.
"""

import uuid
from dataclasses import dataclass
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

_SETTLE_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://ammba.uoc/settlement")


def residual_order_uuid(order_id: str, trade_id: str) -> str:
    """Deterministic id for the residual an order leaves after one match.

    Convention mirrors the clearing node's derived-UUID approach
    (amm-clearing-node/src/adapters.py) — keep the namespaces distinct but the
    style in sync.
    """
    return str(uuid.uuid5(_SETTLE_NS, f"residual:{order_id}:{trade_id}"))


@dataclass(frozen=True)
class BuildResult:
    settlements: list[MarketSettlement]

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


def is_mutual_pair(bid: dict, offer: dict) -> bool:
    """True if the two int:Orders name each other as preferred trading partners."""
    return (
        bid.get("preferredTradingPartner") == offer["createdBy"]
        and offer.get("preferredTradingPartner") == bid["createdBy"]
    )


def build_settlements(
    trades: list[dict],
    orders_by_id: dict[str, dict],
    clearing_results: list[dict],
) -> BuildResult:
    """Transform int:Trade records into one MarketSettlement per market.

    Trades are processed in list order, which is the order residuals chain in.
    """
    results_by_market = {uuid_to_bytes16(r["marketId"]): r for r in clearing_results}
    live: dict[str, OrderParams] = {}  # original order id -> its current (residual) form
    matches_by_market: dict[bytes, list[Match]] = {}

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
        bid_order = orders_by_id[trade["bidId"]]
        offer_order = orders_by_id[trade["offerId"]]
        bid, residual_bid = take(bid_order, True, quantity, trade_id)
        offer, residual_offer = take(offer_order, False, quantity, trade_id)
        match_type = (
            MATCH_TYPE_PREFERRED if is_mutual_pair(bid_order, offer_order) else MATCH_TYPE_STANDARD
        )

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
    return BuildResult(settlements=settlements)
