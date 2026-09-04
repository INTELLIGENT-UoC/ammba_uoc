"""On-chain struct mirrors for TradeSettlement / OrderRegistry.

Mirrors ``gsy-contracts/contracts/TradeSettlement.sol`` (Match, OrderData) and
``OrderRegistry.sol`` (OrderParams, energy-type codes) as of the GSYDEXv2
snapshot vendored locally. The contracts are still WIP upstream ("end of
month" freeze announced) — treat field order as provisional until the ABI is
frozen; every encoding detail lives in this one module.

Unit conventions:
- Energy: kWh scaled by ``SCALING_FACTOR`` (×10000) into u64 — confirmed to
  match GSY's convention (2026-08-24).
- Price: rate per kWh scaled by ``SCALING_FACTOR`` into u64. ⚠ The CURRENCY
  UNIT (EUR vs ct) is not yet decided at consortium level — this module takes
  already-chosen-unit floats and only scales them; the decision plugs in at
  the call site via ``rate_unit`` on the builder (see match_builder).
- Energy types: the on-chain u8 coding INCLUDES GREY (=6), even though the
  current off-chain wire DTO rejects it — drift raised with GSY.
- Identifiers: order/trade/market ids are the UUID's bytes; ACTOR ids
  (``createdBy``) are blake2b-128 hashes of the off-chain id per GSY's
  id-mapping convention (see ids.py) — never the UUID bytes.
"""

from dataclasses import dataclass

from src.ids import ZERO_BYTES16, actor_onchain_id, uuid_to_bytes16

SCALING_FACTOR = 10_000  # confirmed identical on the GSY side (2026-08-24)

# OrderRegistry.sol energy-type codes (u8).
ENERGY_TYPE_CODES = {
    None: 0,  # ENERGY_TYPE_UNSPECIFIED
    "GREEN": 1,
    "PV": 2,
    "HYDRO": 3,
    "BIOMASS": 4,
    "BATTERY": 5,
    "GREY": 6,
}

# ABI component types, in struct field order.
ORDER_DATA_ABI = "(bytes16,bytes16,bytes16,uint64,uint64,uint64,uint64,uint8,uint8)"
MATCH_ABI = f"(bytes16,{ORDER_DATA_ABI},{ORDER_DATA_ABI},bytes16,bytes16,uint256,uint256)"
ORDER_PARAMS_ABI = "(bytes16,bytes16,bytes16,uint64,uint64,uint64,uint64,uint8,uint8,bool)"


def scale(value: float) -> int:
    """Scale a float domain value to the on-chain integer representation."""
    return int(round(value * SCALING_FACTOR))


def energy_type_code(value: str | None) -> int:
    """Map a wire energy-type string (or absent) to the on-chain u8 code."""
    if value is None:
        return 0
    code = ENERGY_TYPE_CODES.get(str(value).upper())
    if code is None:
        raise ValueError(f"unknown energy type for on-chain coding: {value!r}")
    return code


@dataclass(frozen=True)
class OrderData:
    """TradeSettlement.OrderData — one side of a match."""

    order_id: str  # UUID
    created_by: str  # UUID (actor)
    market_id: str  # UUID
    time_slot: int  # unix seconds
    creation_time: int  # unix seconds
    energy_kwh: float
    energy_rate: float  # per kWh, in the agreed currency unit (pending)
    energy_source_preference: str | None = None
    energy_type: str | None = None

    def to_tuple(self) -> tuple:
        return (
            uuid_to_bytes16(self.order_id),
            actor_onchain_id(self.created_by),
            uuid_to_bytes16(self.market_id),
            self.time_slot,
            self.creation_time,
            scale(self.energy_kwh),
            scale(self.energy_rate),
            energy_type_code(self.energy_source_preference),
            energy_type_code(self.energy_type),
        )


@dataclass(frozen=True)
class Match:
    """TradeSettlement.Match — a settleable bid/offer pairing."""

    trade_id: str  # UUID
    bid: OrderData
    offer: OrderData
    selected_energy_kwh: float
    clearing_price: float  # per kWh, agreed currency unit (pending)
    residual_bid_id: str | None = None
    residual_offer_id: str | None = None

    def to_tuple(self) -> tuple:
        return (
            uuid_to_bytes16(self.trade_id),
            self.bid.to_tuple(),
            self.offer.to_tuple(),
            uuid_to_bytes16(self.residual_bid_id) if self.residual_bid_id else ZERO_BYTES16,
            uuid_to_bytes16(self.residual_offer_id) if self.residual_offer_id else ZERO_BYTES16,
            scale(self.selected_energy_kwh),
            scale(self.clearing_price),
        )


@dataclass(frozen=True)
class OrderParams:
    """OrderRegistry.OrderParams — for placing (pool) orders on-chain."""

    order: OrderData
    is_bid: bool

    def to_tuple(self) -> tuple:
        return (*self.order.to_tuple(), self.is_bid)
