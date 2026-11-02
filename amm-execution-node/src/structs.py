"""On-chain struct mirrors for TradeSettlement / OrderRegistry.

Mirrors the GSY DEX settlement contracts (GSYDEXv2 ``f0ea6c8``):
``OrderRegistry.OrderParams`` (one struct for placing orders and for both sides
of a match) and ``TradeSettlement``'s ``Match``, ``ClearingResult`` and
``MarketSettlement``. ``settleBatch`` takes ``MarketSettlement[]``: the matches
of one market together with its clearing result. Every encoding detail lives in
this one module.

Unit conventions:
- Energy: kWh scaled by ``SCALING_FACTOR`` (×10000) into u64/u256.
- Price: EUR/kWh scaled by ``SCALING_FACTOR``, the convention of the GSY DEX
  community client (``energyRate = priceLimit × 10 000``). This module takes the
  trades' ``tradePrice`` (EUR/kWh on the wire) and only scales it.
- Energy types: u8 codes ``NONE``=0, ``GREEN``=1, ``PV``=2, ``HYDRO``=3,
  ``BIOMASS``=4, ``BATTERY``=5.
- Identifiers: order/trade/market ids are the 16 bytes of their UUID (or of the
  storage's ``0x``-hex form); ACTOR ids (``createdBy``,
  ``preferredTradingPartner``) are blake2b-128 hashes of the off-chain id per
  the GSY DEX id-mapping convention (see ids.py) — never the UUID bytes.
"""

from dataclasses import dataclass, replace

from src.ids import ZERO_BYTES16, actor_onchain_id, uuid_to_bytes16

SCALING_FACTOR = 10_000  # same factor as the GSY DEX contracts

# OrderRegistry energy-type codes (u8), as in primitives::db_api_schema.
ENERGY_TYPE_CODES = {
    "NONE": 0,
    "GREEN": 1,
    "PV": 2,
    "HYDRO": 3,
    "BIOMASS": 4,
    "BATTERY": 5,
}

# TradeSettlement.MatchType
MATCH_TYPE_STANDARD = 0
MATCH_TYPE_PREFERRED = 1

# ClearingResult.clearingStatus (u8), as in primitives ClearingStatus::to_evm.
CLEARING_STATUS_CODES = {"final": 1, "partial": 2, "rejected": 3, "no_bid": 4}

# ABI component types, in struct field order.
ORDER_PARAMS_ABI = (
    "(bytes16,bytes16,bytes16,uint64,uint64,uint64,uint64,uint8,uint8,bool,bytes16,uint64)"
)
MATCH_ABI = f"(bytes16,{ORDER_PARAMS_ABI},{ORDER_PARAMS_ABI},bytes16,bytes16,uint256,uint256,uint8)"
CLEARING_RESULT_ABI = "(bytes16,uint8,uint256,uint256,uint256,uint256,uint32)"
MARKET_SETTLEMENT_ABI = f"({MATCH_ABI}[],{CLEARING_RESULT_ABI})"


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
class OrderParams:
    """OrderRegistry.OrderParams — an order as registered on-chain.

    Used for placing (pool) orders and for both sides of a ``Match``; the
    contract checks every field against the registered order.
    """

    order_id: str  # UUID or 0x-hex
    created_by: str  # off-chain actor id (mapped on encoding)
    market_id: str  # UUID or 0x-hex
    time_slot: int  # unix seconds
    creation_time: int  # unix seconds
    energy_kwh: float
    energy_rate: float  # EUR/kWh
    is_bid: bool
    energy_source_preference: str | None = None
    energy_type: str | None = None
    preferred_trading_partner: str | None = None  # off-chain actor id
    preferred_energy_rate: float | None = None  # EUR/kWh

    def residual(self, residual_order_id: str, energy_kwh: float) -> "OrderParams":
        """The order the registry creates for the unfilled rest of this one."""
        return replace(self, order_id=residual_order_id, energy_kwh=energy_kwh)

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
            self.is_bid,
            (
                actor_onchain_id(self.preferred_trading_partner)
                if self.preferred_trading_partner
                else ZERO_BYTES16
            ),
            scale(self.preferred_energy_rate) if self.preferred_energy_rate else 0,
        )


@dataclass(frozen=True)
class Match:
    """TradeSettlement.Match — a settleable bid/offer pairing."""

    trade_id: str  # UUID
    bid: OrderParams
    offer: OrderParams
    selected_energy_kwh: float
    clearing_price: float  # EUR/kWh
    residual_bid_id: str | None = None
    residual_offer_id: str | None = None
    match_type: int = MATCH_TYPE_STANDARD

    def to_tuple(self) -> tuple:
        return (
            uuid_to_bytes16(self.trade_id),
            self.bid.to_tuple(),
            self.offer.to_tuple(),
            uuid_to_bytes16(self.residual_bid_id) if self.residual_bid_id else ZERO_BYTES16,
            uuid_to_bytes16(self.residual_offer_id) if self.residual_offer_id else ZERO_BYTES16,
            scale(self.selected_energy_kwh),
            scale(self.clearing_price),
            self.match_type,
        )


@dataclass(frozen=True)
class ClearingResult:
    """TradeSettlement.ClearingResult — the market's summary, emitted on-chain."""

    market_id: str
    clearing_status: str  # final | partial | rejected | no_bid
    clearing_price: float  # EUR/kWh
    total_supply_kwh: float
    total_demand_kwh: float
    traded_quantity_kwh: float
    num_trades: int

    def to_tuple(self) -> tuple:
        return (
            uuid_to_bytes16(self.market_id),
            CLEARING_STATUS_CODES[self.clearing_status],
            scale(self.clearing_price),
            scale(self.total_supply_kwh),
            scale(self.total_demand_kwh),
            scale(self.traded_quantity_kwh),
            self.num_trades,
        )


@dataclass(frozen=True)
class MarketSettlement:
    """TradeSettlement.MarketSettlement — one market's matches and its result.

    The contract requires the selected energy of all matches to equal the
    clearing result's traded quantity.
    """

    market_id: str
    matches: tuple[Match, ...]
    clearing_result: ClearingResult

    def to_tuple(self) -> tuple:
        return ([m.to_tuple() for m in self.matches], self.clearing_result.to_tuple())
