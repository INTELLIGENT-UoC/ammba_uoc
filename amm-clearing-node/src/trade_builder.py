"""Trade object construction and blake2b hashing.

Builds trade objects in the format expected by POST /trades-normalized,
matching the GSY DEX off-chain DB schema (Postman collection).
"""

import hashlib
import json
import time
from uuid import uuid4


def blake2b_hash(data: dict) -> str:
    """Produce a blake2b-256 hex hash of a JSON-serialised dict (sorted keys).

    Matches the GSY DEX hashing convention for order/trade IDs.
    """
    encoded = json.dumps(data, sort_keys=True).encode("utf-8")
    h = hashlib.new("blake2b", encoded, digest_size=32)
    return "0x" + h.hexdigest()


def build_buyer_pool_trade(
    bid: dict,
    pool_id: str,
    market_id: str,
    time_slot: int,
    clearing_price: float,
    tx_hash: str,
    theta: float,
    steepness: float,
    total_supply_kwh: float,
    total_demand_kwh: float,
) -> dict:
    """Build Trade A: Buyer → Pool.

    Each buyer trades with the AMM pool at the uniform clearing price.
    """
    now = int(time.time())
    trade_uuid = str(uuid4())

    allocated = bid["allocated_energy"]
    residual_energy = bid["energy"] - allocated

    offer_component = {
        "area_uuid": pool_id,
        "market_id": market_id,
        "time_slot": time_slot,
        "creation_time": now,
        "energy": allocated,
        "energy_rate": clearing_price,
    }

    bid_component = {
        "area_uuid": bid["area_uuid"],
        "market_id": bid["market_id"],
        "time_slot": bid["time_slot"],
        "creation_time": bid["creation_time"],
        "energy": allocated,
        "energy_rate": clearing_price,
    }

    trade = {
        "trade_uuid": trade_uuid,
        "status": "Settled",
        "buyer": bid["created_by"],
        "seller": pool_id,
        "market_id": market_id,
        "time_slot": time_slot,
        "creation_time": now,
        "offer": {
            "seller": pool_id,
            "offer_component": offer_component,
        },
        "offer_hash": tx_hash,
        "bid": {
            "buyer": bid["created_by"],
            "nonce": bid.get("nonce", 1),
            "bid_component": bid_component,
        },
        "bid_hash": bid.get("order_id", bid.get("_id", "")),
        "residual_offer": None,
        "residual_bid": (
            {"energy": residual_energy, "energy_rate": bid["energy_rate"]}
            if residual_energy > 1e-9
            else None
        ),
        "parameters": {
            "selected_energy": allocated,
            "energy_rate": clearing_price,
            "trade_uuid": trade_uuid,
            "amm_tx_hash": tx_hash,
            "theta": theta,
            "steepness": steepness,
            "total_supply_kwh": total_supply_kwh,
            "total_demand_kwh": total_demand_kwh,
            "preference_matched": False,
        },
    }

    trade["_id"] = blake2b_hash(trade)
    return trade


def build_pool_seller_trade(
    offer: dict,
    pool_id: str,
    market_id: str,
    time_slot: int,
    clearing_price: float,
    tx_hash: str,
    theta: float,
    steepness: float,
    total_supply_kwh: float,
    total_demand_kwh: float,
) -> dict:
    """Build Trade B: Pool → Seller.

    Each seller trades with the AMM pool at the uniform clearing price.
    """
    now = int(time.time())
    trade_uuid = str(uuid4())

    allocated = offer["allocated_energy"]
    residual_energy = offer["energy"] - allocated

    offer_component = {
        "area_uuid": offer["area_uuid"],
        "market_id": offer["market_id"],
        "time_slot": offer["time_slot"],
        "creation_time": offer["creation_time"],
        "energy": allocated,
        "energy_rate": clearing_price,
    }

    bid_component = {
        "area_uuid": pool_id,
        "market_id": market_id,
        "time_slot": time_slot,
        "creation_time": now,
        "energy": allocated,
        "energy_rate": clearing_price,
    }

    trade = {
        "trade_uuid": trade_uuid,
        "status": "Settled",
        "buyer": pool_id,
        "seller": offer["created_by"],
        "market_id": market_id,
        "time_slot": time_slot,
        "creation_time": now,
        "offer": {
            "seller": offer["created_by"],
            "offer_component": offer_component,
        },
        "offer_hash": offer.get("order_id", offer.get("_id", "")),
        "bid": {
            "buyer": pool_id,
            "nonce": 1,
            "bid_component": bid_component,
        },
        "bid_hash": tx_hash,
        "residual_offer": (
            {"energy": residual_energy, "energy_rate": offer["energy_rate"]}
            if residual_energy > 1e-9
            else None
        ),
        "residual_bid": None,
        "parameters": {
            "selected_energy": allocated,
            "energy_rate": clearing_price,
            "trade_uuid": trade_uuid,
            "amm_tx_hash": tx_hash,
            "theta": theta,
            "steepness": steepness,
            "total_supply_kwh": total_supply_kwh,
            "total_demand_kwh": total_demand_kwh,
            "preference_matched": False,
        },
    }

    trade["_id"] = blake2b_hash(trade)
    return trade


def build_direct_preference_trade(
    match: dict,
    market_id: str,
    time_slot: int,
    tx_hash: str,
    theta: float,
    steepness: float,
    total_supply_kwh: float,
    total_demand_kwh: float,
) -> dict:
    """Build a direct Buyer → Seller trade for preference-matched pairs.

    Unlike pool trades, this is a direct trade between buyer and seller
    who have mutual trading partner preferences.
    """
    now = int(time.time())
    trade_uuid = str(uuid4())

    energy = match["energy"]
    clearing_price = match["energy_rate"]

    bid_component = {
        "area_uuid": match["buyer_area_uuid"],
        "market_id": market_id,
        "time_slot": time_slot,
        "creation_time": now,
        "energy": energy,
        "energy_rate": clearing_price,
    }

    offer_component = {
        "area_uuid": match["seller_area_uuid"],
        "market_id": market_id,
        "time_slot": time_slot,
        "creation_time": now,
        "energy": energy,
        "energy_rate": clearing_price,
    }

    trade = {
        "trade_uuid": trade_uuid,
        "status": "Settled",
        "buyer": match["buyer"],
        "seller": match["seller"],
        "market_id": market_id,
        "time_slot": time_slot,
        "creation_time": now,
        "offer": {
            "seller": match["seller"],
            "offer_component": offer_component,
        },
        "offer_hash": match.get("offer_order_id", ""),
        "bid": {
            "buyer": match["buyer"],
            "nonce": 1,
            "bid_component": bid_component,
        },
        "bid_hash": match.get("bid_order_id", ""),
        "residual_offer": None,
        "residual_bid": None,
        "parameters": {
            "selected_energy": energy,
            "energy_rate": clearing_price,
            "trade_uuid": trade_uuid,
            "amm_tx_hash": tx_hash,
            "theta": theta,
            "steepness": steepness,
            "total_supply_kwh": total_supply_kwh,
            "total_demand_kwh": total_demand_kwh,
            "preference_matched": True,
        },
    }

    trade["_id"] = blake2b_hash(trade)
    return trade
