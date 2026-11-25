"""Pre-flight validation mirroring TradeSettlement.settleBatch.

Runs the contract's revert conditions locally so a bad market settlement is
caught before any gas is spent. The contract reverts the whole transaction on
the first invalid match, so a market with any violation is held back as a
whole.

Contract checks mirrored (TradeSettlement.sol, GSYDEXv2 ``f0ea6c8``):
- InvalidOrderParams: zero ids, self-trade, market or time-slot mismatch,
  wrong ``isBid`` flags
- PriceMismatch (``Standard``): ``bid.energyRate ≥ clearingPrice ≥ offer.energyRate``
- InvalidPreferredPartner / PriceMismatch (``Preferred``): every declared
  partner is the counterparty, and the price lies between the effective rates
  (``preferredEnergyRate`` when set, otherwise ``energyRate``)
- EnergyMismatch: selected energy is positive and fits both orders
- TradedQuantityMismatch: the selected energy of a market's matches sums to the
  clearing result's traded quantity

Two checks are where the AMM's mechanism meets the contract's order-book
semantics. AMM clearing does not condition on participant limit prices, so a
buyer whose priceLimit lies below the clearing price (or a seller whose limit
lies above it) produces a match the contract rejects; the limit-price
convention is an open design point. And the sequential fill can pair an actor
with itself when only its own bids remain (a self-trade). Until resolved, this
validator makes both visible instead of a revert. The quantity check passes by
construction: every trade is one bilateral match, and the clearing result
states the sum of the trades.
"""

from dataclasses import dataclass

from src.ids import uuid_to_bytes16
from src.structs import MATCH_TYPE_PREFERRED, SCALING_FACTOR, MarketSettlement, Match, scale


@dataclass(frozen=True)
class Violation:
    subject: str  # trade id, or market id for market-level checks
    code: str
    detail: str


def _bytes(value: str) -> bytes | None:
    try:
        return uuid_to_bytes16(value)
    except ValueError:
        return None


def _effective_rate(order) -> float:
    return order.preferred_energy_rate if order.preferred_energy_rate else order.energy_rate


Issue = tuple[str, str]  # (contract error code, detail)


def _order_param_issues(match: Match) -> list[Issue]:
    """InvalidOrderParams: ids, self-trade, market and time slot, bid/offer sides."""
    issues = [
        ("InvalidOrderParams", f"{label} is empty")
        for label, value in (
            ("tradeId", match.trade_id),
            ("bid.orderId", match.bid.order_id),
            ("offer.orderId", match.offer.order_id),
            ("bid.createdBy", match.bid.created_by),
            ("offer.createdBy", match.offer.created_by),
        )
        if not value
    ]
    if match.bid.created_by == match.offer.created_by:
        issues.append(("InvalidOrderParams", "self-trade: bid and offer have the same creator"))
    if _bytes(match.bid.market_id) != _bytes(match.offer.market_id):
        issues.append(("InvalidOrderParams", "bid/offer market mismatch"))
    if match.bid.time_slot != match.offer.time_slot:
        issues.append(("InvalidOrderParams", "bid/offer timeSlot mismatch"))
    if not match.bid.is_bid or match.offer.is_bid:
        issues.append(("InvalidOrderParams", "isBid flags do not match the bid/offer sides"))
    return issues


def _preferred_issues(match: Match, price: int) -> list[Issue]:
    """InvalidPreferredPartner and PriceMismatch of a ``Preferred`` match."""
    issues = []
    bid_partner = match.bid.preferred_trading_partner
    offer_partner = match.offer.preferred_trading_partner
    if not bid_partner and not offer_partner:
        issues.append(("InvalidPreferredPartner", "preferred match without a declared partner"))
    if bid_partner and bid_partner != match.offer.created_by:
        issues.append(("InvalidPreferredPartner", "the bid's partner is not the offer's creator"))
    if offer_partner and offer_partner != match.bid.created_by:
        issues.append(("InvalidPreferredPartner", "the offer's partner is not the bid's creator"))
    bid_rate = scale(_effective_rate(match.bid))
    offer_rate = scale(_effective_rate(match.offer))
    if bid_rate < offer_rate or price > bid_rate or price < offer_rate:
        issues.append(
            (
                "PriceMismatch",
                f"clearing {match.clearing_price} outside the effective rates "
                f"[{_effective_rate(match.offer)}, {_effective_rate(match.bid)}]",
            )
        )
    return issues


def _standard_price_issues(match: Match, price: int) -> list[Issue]:
    """PriceMismatch of a ``Standard`` match: bid limit ≥ price ≥ offer limit."""
    issues = []
    if scale(match.bid.energy_rate) < price:
        issues.append(
            (
                "PriceMismatch",
                f"bid limit {match.bid.energy_rate} < clearing {match.clearing_price} "
                "(AMM clearing ignores limit prices; the contract does not)",
            )
        )
    if scale(match.offer.energy_rate) > price:
        issues.append(
            (
                "PriceMismatch",
                f"offer limit {match.offer.energy_rate} > clearing {match.clearing_price}",
            )
        )
    return issues


def _energy_issues(match: Match) -> list[Issue]:
    """EnergyMismatch: selected energy is positive and fits both orders."""
    issues = []
    selected = scale(match.selected_energy_kwh)
    if selected <= 0:
        issues.append(("EnergyMismatch", "selectedEnergy must be positive"))
    if selected > scale(match.bid.energy_kwh):
        issues.append(("EnergyMismatch", "selectedEnergy exceeds bid energy"))
    if selected > scale(match.offer.energy_kwh):
        issues.append(("EnergyMismatch", "selectedEnergy exceeds offer energy"))
    return issues


def validate_match(match: Match) -> list[Violation]:
    # The contract compares scaled integers; do the same to avoid float edge cases.
    price = scale(match.clearing_price)
    if match.match_type == MATCH_TYPE_PREFERRED:
        price_issues = _preferred_issues(match, price)
    else:
        price_issues = _standard_price_issues(match, price)
    issues = _order_param_issues(match) + price_issues + _energy_issues(match)
    return [Violation(match.trade_id, code, detail) for code, detail in issues]


def validate_settlement(settlement: MarketSettlement) -> list[Violation]:
    """All violations of one market: its matches and the quantity check."""
    violations = [v for m in settlement.matches for v in validate_match(m)]
    selected = sum(scale(m.selected_energy_kwh) for m in settlement.matches)
    traded = scale(settlement.clearing_result.traded_quantity_kwh)
    if selected != traded:
        violations.append(
            Violation(
                settlement.market_id,
                "TradedQuantityMismatch",
                f"matches sum to {selected / SCALING_FACTOR} kWh, clearing result reports "
                f"{traded / SCALING_FACTOR} kWh",
            )
        )
    return violations


def validate_batch(settlements: list[MarketSettlement]) -> dict[str, list[Violation]]:
    """Validate every market; returns violations keyed by market id (empty = ok)."""
    result: dict[str, list[Violation]] = {}
    for settlement in settlements:
        found = validate_settlement(settlement)
        if found:
            result[settlement.market_id] = found
    return result
