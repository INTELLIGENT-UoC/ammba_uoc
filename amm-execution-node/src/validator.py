"""Pre-flight validation mirroring TradeSettlement._settleTrade.

Runs the contract's revert conditions locally so a bad match is caught before
any gas is spent, and so the whole batch cannot be poisoned by one entry.

Contract checks mirrored (TradeSettlement.sol):
- InvalidOrderParams: zero ids, market or time-slot mismatch between sides
- PriceMismatch: requires bid.energyRate ≥ clearingPrice ≥ offer.energyRate
- EnergyMismatch: selectedEnergy must not exceed either side's energy

Note the PriceMismatch check is where the AMM's mechanism meets the contract's
limit-order semantics: AMM clearing does not condition on participant limit
prices, so a buyer whose priceLimit lies below the clearing price produces a
match the contract WILL reject. That conflict is an open design point with
GSY; until resolved, this validator makes it visible per-trade instead of a
mid-batch revert.
"""

from dataclasses import dataclass

from src.structs import Match, scale


@dataclass(frozen=True)
class Violation:
    trade_id: str
    code: str
    detail: str


def validate_match(match: Match) -> list[Violation]:
    violations = []

    def flag(code: str, detail: str) -> None:
        violations.append(Violation(match.trade_id, code, detail))

    for label, value in (
        ("tradeId", match.trade_id),
        ("bid.orderId", match.bid.order_id),
        ("offer.orderId", match.offer.order_id),
        ("bid.createdBy", match.bid.created_by),
        ("offer.createdBy", match.offer.created_by),
    ):
        if not value:
            flag("InvalidOrderParams", f"{label} is empty")

    if match.bid.market_id != match.offer.market_id:
        flag("InvalidOrderParams", "bid/offer market mismatch")
    if match.bid.time_slot != match.offer.time_slot:
        flag("InvalidOrderParams", "bid/offer timeSlot mismatch")

    # Contract compares scaled integers; do the same to avoid float edge cases.
    price = scale(match.clearing_price)
    if scale(match.bid.energy_rate) < price:
        flag(
            "PriceMismatch",
            f"bid limit {match.bid.energy_rate} < clearing {match.clearing_price} "
            "(AMM ignores limits; the contract does not — open point with GSY)",
        )
    if scale(match.offer.energy_rate) > price:
        flag(
            "PriceMismatch",
            f"offer limit {match.offer.energy_rate} > clearing {match.clearing_price}",
        )

    selected = scale(match.selected_energy_kwh)
    if selected > scale(match.bid.energy_kwh):
        flag("EnergyMismatch", "selectedEnergy exceeds bid energy")
    if selected > scale(match.offer.energy_kwh):
        flag("EnergyMismatch", "selectedEnergy exceeds offer energy")

    return violations


def validate_batch(matches: list[Match]) -> dict[str, list[Violation]]:
    """Validate every match; returns violations keyed by trade id (empty = ok)."""
    result: dict[str, list[Violation]] = {}
    for match in matches:
        found = validate_match(match)
        if found:
            result[match.trade_id] = found
    return result
