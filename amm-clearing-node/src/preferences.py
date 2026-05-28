"""User preference matching — Post-Price Clearing Framework.

Implements the preference management framework from
GSY_DEX_Multi_User_Preference_Matching.docx.md:

1. Preferred Trading Partners (Priority Allocation):
   - Identify mutual pairs (buyer listed seller, seller listed buyer)
   - Allocate their quantities first at the clearing price
   - Remaining volume distributed pro-rata to residual pool

2. Energy Type Multipliers (Differential Pricing):
   - Community manager defines green_subsidy and grey_levy multipliers
   - Green trades: final_price = clearing_price * (1 + green_multiplier)
   - Grey trades: final_price = clearing_price * (1 - grey_levy)
   - Safety: Levy Cap + Dynamic Subsidy Scaling (zero-sum)
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class EnergyTypeMultipliers:
    """Community-defined multipliers for differential pricing."""
    green_subsidy_rate: float = 0.0     # e.g. 0.10 = +10% for green producers
    grey_levy_rate: float = 0.0         # e.g. 0.05 = -5% for grey participants
    levy_cap_ct_per_kwh: float = 5.0    # Max levy per kWh on grey


# Energy types recognized by the system (from GSY DEX spec)
GREEN_TYPES = {"GREEN", "PV", "HYDRO", "BIOMASS", "BATTERY"}
GREY_TYPES = {"GREY"}


def find_mutual_preferred_pairs(
    bids: list[dict], offers: list[dict]
) -> list[tuple[dict, dict]]:
    """Identify buyer-seller pairs with mutual trading partner preferences.

    A mutual pair exists when:
    - Buyer's requirements.trading_partner_id includes the seller's created_by
    - Seller's requirements.trading_partner_id includes the buyer's created_by

    Returns list of (bid, offer) tuples for mutual pairs.
    """
    pairs = []

    for bid in bids:
        bid_reqs = bid.get("requirements") or {}
        bid_partners = set(bid_reqs.get("trading_partner_id") or [])
        if not bid_partners:
            continue

        for offer in offers:
            offer_reqs = offer.get("requirements") or {}
            offer_partners = set(offer_reqs.get("trading_partner_id") or [])

            # Check mutual preference
            buyer_wants_seller = offer.get("created_by") in bid_partners
            seller_wants_buyer = bid.get("created_by") in offer_partners

            if buyer_wants_seller and seller_wants_buyer:
                pairs.append((bid, offer))

    return pairs


def apply_priority_allocation(
    bids: list[dict],
    offers: list[dict],
    clearing_price: float,
    traded_quantity: float,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Apply Preferred Trading Partner priority allocation.

    1. Find mutual preferred pairs
    2. Allocate volume to mutual pairs first (up to their demanded/offered quantities)
    3. Reduce allocated_energy for matched participants
    4. Return bids, offers, and list of preference-matched allocations

    The preference-matched allocations are separate from the pool trades —
    they represent direct buyer↔seller trades at the clearing price.
    """
    mutual_pairs = find_mutual_preferred_pairs(bids, offers)

    if not mutual_pairs:
        return bids, offers, []

    preference_matches = []

    for bid, offer in mutual_pairs:
        # How much can this pair trade?
        available_bid = bid.get("allocated_energy", 0)
        available_offer = offer.get("allocated_energy", 0)

        if available_bid <= 0 or available_offer <= 0:
            continue

        match_energy = min(available_bid, available_offer)

        # Deduct from their pool allocation
        bid["allocated_energy"] -= match_energy
        offer["allocated_energy"] -= match_energy

        preference_matches.append({
            "buyer": bid["created_by"],
            "seller": offer["created_by"],
            "buyer_area_uuid": bid["area_uuid"],
            "seller_area_uuid": offer["area_uuid"],
            "energy": match_energy,
            "energy_rate": clearing_price,
            "bid_order_id": bid.get("order_id", ""),
            "offer_order_id": offer.get("order_id", ""),
        })

        logger.info(
            "Preference match: %s <-> %s, %.4f kWh at %.4f ct/kWh",
            bid["created_by"],
            offer["created_by"],
            match_energy,
            clearing_price,
        )

    return bids, offers, preference_matches


def apply_energy_type_multipliers(
    trades: list[dict],
    bids: list[dict],
    offers: list[dict],
    clearing_price: float,
    multipliers: EnergyTypeMultipliers | None,
) -> list[dict]:
    """Apply ex-post energy type multipliers to trade prices.

    This implements the Post-Price Clearing differential pricing:
    - Green energy producers receive: clearing_price * (1 + green_subsidy_rate)
    - Grey energy participants pay/receive adjusted price with levy
    - Safety: Levy Cap limits per-unit grey penalty
    - Safety: Dynamic Subsidy Scaling if grey revenue insufficient

    The system is zero-sum: green subsidies are funded by grey levies.
    """
    if multipliers is None:
        return trades

    if multipliers.green_subsidy_rate == 0 and multipliers.grey_levy_rate == 0:
        return trades

    # Build lookup for energy types from offer attributes
    offer_energy_types: dict[str, set[str]] = {}
    for offer in offers:
        attrs = offer.get("attributes") or {}
        energy_types = set(attrs.get("energy_type") or [])
        offer_energy_types[offer.get("created_by", "")] = energy_types

    # Classify trades as green or grey based on the seller's energy type
    green_trades = []
    grey_trades = []
    neutral_trades = []

    for trade in trades:
        seller = trade.get("seller", "")
        # Pool→Seller trades: the seller is the participant
        # Buyer→Pool trades: the seller is the pool
        if "AMM_POOL" in seller:
            # This is a Buyer→Pool trade — classify by what the buyer requested
            buyer_id = trade.get("buyer", "")
            bid = next(
                (b for b in bids if b.get("created_by") == buyer_id), None
            )
            if bid:
                reqs = bid.get("requirements") or {}
                energy_source = set(reqs.get("energy_source") or [])
                if energy_source & GREEN_TYPES:
                    green_trades.append(trade)
                elif energy_source & GREY_TYPES:
                    grey_trades.append(trade)
                else:
                    neutral_trades.append(trade)
            else:
                neutral_trades.append(trade)
        else:
            # Pool→Seller trade — classify by seller's energy type attribute
            types = offer_energy_types.get(seller, set())
            if types & GREEN_TYPES:
                green_trades.append(trade)
            elif types & GREY_TYPES:
                grey_trades.append(trade)
            else:
                neutral_trades.append(trade)

    # Calculate volumes
    green_volume = sum(
        t.get("parameters", {}).get("selected_energy", 0) for t in green_trades
    )
    grey_volume = sum(
        t.get("parameters", {}).get("selected_energy", 0) for t in grey_trades
    )

    if green_volume == 0 or grey_volume == 0:
        # Can't do zero-sum redistribution without both sides
        return trades

    # Calculate target green subsidy total
    target_subsidy_per_kwh = clearing_price * multipliers.green_subsidy_rate
    target_subsidy_total = target_subsidy_per_kwh * green_volume

    # Calculate available grey levy revenue
    levy_per_kwh = min(
        clearing_price * multipliers.grey_levy_rate,
        multipliers.levy_cap_ct_per_kwh,
    )
    grey_revenue = levy_per_kwh * grey_volume

    # Dynamic Subsidy Scaling: if grey revenue < target subsidy, scale down
    if grey_revenue < target_subsidy_total and target_subsidy_total > 0:
        scaling_factor = grey_revenue / target_subsidy_total
        actual_subsidy_per_kwh = target_subsidy_per_kwh * scaling_factor
        logger.info(
            "Dynamic subsidy scaling: %.2f (grey revenue %.4f < target %.4f)",
            scaling_factor,
            grey_revenue,
            target_subsidy_total,
        )
    else:
        actual_subsidy_per_kwh = target_subsidy_per_kwh

    # Apply multipliers to trade energy_rate in parameters
    for trade in green_trades:
        params = trade.get("parameters", {})
        params["base_energy_rate"] = params.get("energy_rate", clearing_price)
        params["energy_rate"] = clearing_price + actual_subsidy_per_kwh
        params["energy_type_adjustment"] = actual_subsidy_per_kwh
        params["energy_type"] = "GREEN"

    for trade in grey_trades:
        params = trade.get("parameters", {})
        params["base_energy_rate"] = params.get("energy_rate", clearing_price)
        params["energy_rate"] = clearing_price - levy_per_kwh
        params["energy_type_adjustment"] = -levy_per_kwh
        params["energy_type"] = "GREY"

    logger.info(
        "Energy type multipliers applied: green +%.4f ct/kWh (%d trades), "
        "grey -%.4f ct/kWh (%d trades), %d neutral",
        actual_subsidy_per_kwh,
        len(green_trades),
        levy_per_kwh,
        len(grey_trades),
        len(neutral_trades),
    )

    return trades


def apply_preference_allocation(
    bids: list[dict],
    offers: list[dict],
    clearing_price: float,
    traded_quantity: float,
) -> tuple[list[dict], list[dict]]:
    """Apply user preference matching to allocated orders.

    Main entry point called from clearing.py. Handles:
    1. Preferred Trading Partner priority allocation
    2. Returns updated bids/offers with adjusted allocated_energy

    Energy type multipliers are applied separately to trades in clearing.py
    via apply_energy_type_multipliers().
    """
    has_preferences = any(
        o.get("requirements") is not None or o.get("attributes") is not None
        for o in bids + offers
    )

    if not has_preferences:
        return bids, offers

    # Apply priority allocation for mutual preferred trading partners
    bids, offers, preference_matches = apply_priority_allocation(
        bids, offers, clearing_price, traded_quantity
    )

    if preference_matches:
        logger.info(
            "%d preference-matched pairs, total %.4f kWh",
            len(preference_matches),
            sum(m["energy"] for m in preference_matches),
        )

    # Store preference matches on bids/offers for trade builder to use
    # (The clearing.py will check for this and generate direct trades)
    if preference_matches:
        for bid in bids:
            bid["_preference_matches"] = [
                m for m in preference_matches
                if m["buyer"] == bid.get("created_by")
            ]
        for offer in offers:
            offer["_preference_matches"] = [
                m for m in preference_matches
                if m["seller"] == offer.get("created_by")
            ]

    return bids, offers
