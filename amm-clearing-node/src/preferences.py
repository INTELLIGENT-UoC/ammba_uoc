"""User preference matching — Post-Price Clearing Framework.

1. Preferred Trading Partners (Priority Allocation):
   - Identify mutual pairs (buyer listed seller, seller listed buyer)
   - Allocate their quantities first at the clearing price
   - Remaining volume distributed pro-rata to residual pool

2. Energy-Type Differential Pricing (seller-side, zero-sum):
   - The community manager defines a green subsidy rate and a grey levy rate.
   - Applied to Pool→Seller legs only: green producers receive
     clearing + subsidy, grey producers receive clearing − levy (capped).
   - Buyers and direct preference trades stay at the uniform clearing price,
     preserving the consumer-side uniform-price property; the differential is
     settled against the pool account.
   - Safety: Levy Cap bounds the per-kWh levy; Dynamic Subsidy Scaling shrinks
     the subsidy so it never exceeds the collected levy revenue (zero-sum; any
     surplus levy remains with the pool and is reported).
   - The adjusted price goes directly into the wire ``tradePrice``; provenance
     (base price, adjustment, classification) is returned to the caller and
     surfaced in the clearing summary — no ontology change required.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnergyTypeMultipliers:
    """Community-defined multipliers for differential pricing."""

    green_subsidy_rate: float = 0.0  # e.g. 0.10 = +10% target for green producers
    grey_levy_rate: float = 0.0  # e.g. 0.05 = -5% levy on grey producers
    levy_cap_ct_per_kwh: float = 5.0  # Max levy per kWh on grey


# Energy types recognized by the system (from GSY DEX spec)
GREEN_TYPES = {"GREEN", "PV", "HYDRO", "BIOMASS", "BATTERY"}
GREY_TYPES = {"GREY"}


def find_mutual_preferred_pairs(bids: list[dict], offers: list[dict]) -> list[tuple[dict, dict]]:
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

        preference_matches.append(
            {
                "buyer": bid["created_by"],
                "seller": offer["created_by"],
                "buyer_area_uuid": bid["area_uuid"],
                "seller_area_uuid": offer["area_uuid"],
                "energy": match_energy,
                "energy_rate": clearing_price,
                "bid_order_id": bid.get("order_id", ""),
                "offer_order_id": offer.get("order_id", ""),
            }
        )

        logger.info(
            "Preference match: %s <-> %s, %.4f kWh at %.4f ct/kWh",
            bid["created_by"],
            offer["created_by"],
            match_energy,
            clearing_price,
        )

    return bids, offers, preference_matches


def _classify_offer(offer: dict) -> str:
    """Classify an offer as GREEN / GREY / NEUTRAL by its energy-type attribute."""
    attrs = offer.get("attributes") or {}
    types = set(attrs.get("energy_type") or [])
    if types & GREEN_TYPES:
        return "GREEN"
    if types & GREY_TYPES:
        return "GREY"
    return "NEUTRAL"


def compute_seller_price_adjustments(
    offers: list[dict],
    clearing_price: float,
    multipliers: EnergyTypeMultipliers | None,
) -> tuple[dict[str, float], dict | None]:
    """Seller-side differential pricing over the pool allocations (zero-sum).

    Offers with remaining pool allocation are classified by energy type:
    green sellers receive ``clearing + subsidy``, grey sellers receive
    ``clearing − levy`` (levy capped per kWh). The subsidy is scaled down so
    the total subsidy never exceeds the collected levy revenue (Dynamic
    Subsidy Scaling); any surplus levy remains with the pool.

    Buyers and direct preference trades are untouched — consumers keep the
    uniform clearing price, and the differential settles against the pool.

    Returns ``(adjusted_ct_by_order_id, provenance)``; ``({}, None)`` when no
    adjustment applies (no multipliers, zero rates, or a missing side).
    """
    if multipliers is None:
        return {}, None
    if multipliers.green_subsidy_rate == 0 and multipliers.grey_levy_rate == 0:
        return {}, None

    green_offers = []
    grey_offers = []
    for offer in offers:
        if offer.get("allocated_energy", 0) <= 1e-9:
            continue
        classification = _classify_offer(offer)
        if classification == "GREEN":
            green_offers.append(offer)
        elif classification == "GREY":
            grey_offers.append(offer)

    green_volume = sum(o["allocated_energy"] for o in green_offers)
    grey_volume = sum(o["allocated_energy"] for o in grey_offers)
    if green_volume <= 0 or grey_volume <= 0:
        # Zero-sum redistribution needs both a funded and a funding side.
        return {}, None

    levy_per_kwh = min(
        clearing_price * multipliers.grey_levy_rate,
        multipliers.levy_cap_ct_per_kwh,
    )
    levy_revenue = levy_per_kwh * grey_volume

    target_subsidy_per_kwh = clearing_price * multipliers.green_subsidy_rate
    target_subsidy_total = target_subsidy_per_kwh * green_volume

    scaling_factor = 1.0
    if target_subsidy_total > levy_revenue and target_subsidy_total > 0:
        scaling_factor = levy_revenue / target_subsidy_total
        logger.info(
            "Dynamic subsidy scaling: %.2f (levy revenue %.4f < target %.4f)",
            scaling_factor,
            levy_revenue,
            target_subsidy_total,
        )
    subsidy_per_kwh = target_subsidy_per_kwh * scaling_factor
    subsidy_total = subsidy_per_kwh * green_volume

    adjusted: dict[str, float] = {}
    adjustments = []
    for offer in green_offers:
        adjusted[offer["order_id"]] = clearing_price + subsidy_per_kwh
        adjustments.append(
            {
                "sellerId": offer.get("created_by", ""),
                "orderId": offer["order_id"],
                "classification": "GREEN",
                "base_ct_per_kwh": clearing_price,
                "adjusted_ct_per_kwh": clearing_price + subsidy_per_kwh,
            }
        )
    for offer in grey_offers:
        adjusted[offer["order_id"]] = clearing_price - levy_per_kwh
        adjustments.append(
            {
                "sellerId": offer.get("created_by", ""),
                "orderId": offer["order_id"],
                "classification": "GREY",
                "base_ct_per_kwh": clearing_price,
                "adjusted_ct_per_kwh": clearing_price - levy_per_kwh,
            }
        )

    provenance = {
        "scheme": "seller_side_zero_sum",
        "clearing_price_ct_per_kwh": clearing_price,
        "subsidy_ct_per_kwh": subsidy_per_kwh,
        "levy_ct_per_kwh": levy_per_kwh,
        "scaling_factor": scaling_factor,
        "green_volume_kwh": green_volume,
        "grey_volume_kwh": grey_volume,
        "levy_revenue_ct": levy_revenue,
        "subsidy_total_ct": subsidy_total,
        "pool_residual_ct": levy_revenue - subsidy_total,
        "adjustments": adjustments,
    }

    logger.info(
        "Differential pricing: green +%.4f ct/kWh (%d sellers), "
        "grey -%.4f ct/kWh (%d sellers), pool residual %.4f ct",
        subsidy_per_kwh,
        len(green_offers),
        levy_per_kwh,
        len(grey_offers),
        provenance["pool_residual_ct"],
    )
    return adjusted, provenance


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

    Energy-type differential pricing is applied separately in clearing.py via
    compute_seller_price_adjustments().
    """
    has_preferences = any(
        o.get("requirements") is not None or o.get("attributes") is not None for o in bids + offers
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
                m for m in preference_matches if m["buyer"] == bid.get("created_by")
            ]
        for offer in offers:
            offer["_preference_matches"] = [
                m for m in preference_matches if m["seller"] == offer.get("created_by")
            ]

    return bids, offers
