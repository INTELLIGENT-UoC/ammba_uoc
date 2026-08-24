"""Tests for the settlement engine skeleton: structs, builder, validator, engine."""

import uuid

import pytest
from eth_abi import encode as abi_encode
from src.engine import SettlementEngine, SettlementLedger
from src.ids import bytes16_to_uuid, uuid_to_bytes16
from src.match_builder import build_matches, pool_settle_order_uuid
from src.structs import MATCH_ABI, OrderData, energy_type_code, scale
from src.validator import validate_match

POOL = str(uuid.uuid4())
MARKET = str(uuid.uuid4())
SLOT = 1787580000


def u() -> str:
    return str(uuid.uuid4())


def int_order(order_id, actor, otype, kwh, limit, energy_type=None):
    order = {
        "orderId": order_id,
        "marketId": MARKET,
        "orderType": otype,
        "orderStatus": "Submitted",
        "timeSlot": SLOT,
        "quantity": kwh,
        "priceLimit": limit,
        "createdBy": actor,
        "createdAt": SLOT - 300,
    }
    if energy_type:
        order["energyType"] = energy_type
    return order


def pool_trade(trade_id, bid_id, buyer, qty, price, seller_is_pool=True):
    return {
        "tradeId": trade_id,
        "marketId": MARKET,
        "bidId": bid_id if seller_is_pool else pool_settle_order_uuid(trade_id),
        "buyerId": buyer if seller_is_pool else POOL,
        "offerId": pool_settle_order_uuid(trade_id) if seller_is_pool else bid_id,
        "sellerId": POOL if seller_is_pool else buyer,
        "tradeStatus": "settled",
        "tradeQuantity": qty,
        "tradePrice": price,
        "tradedAt": "2026-08-24T14:00:00Z",
    }


class TestIds:
    def test_roundtrip(self):
        value = u()
        assert bytes16_to_uuid(uuid_to_bytes16(value)) == value

    def test_bytes16_is_16_bytes(self):
        assert len(uuid_to_bytes16(u())) == 16


class TestStructs:
    def test_energy_type_codes_include_grey(self):
        assert energy_type_code("GREY") == 6
        assert energy_type_code("PV") == 2
        assert energy_type_code(None) == 0

    def test_unknown_energy_type_raises(self):
        with pytest.raises(ValueError):
            energy_type_code("FUSION")

    def test_scaling(self):
        assert scale(19.5246) == 195246
        assert scale(0.285) == 2850

    def test_match_abi_encodes(self):
        """The Match tuple must be encodable with the declared ABI signature."""
        order = OrderData(u(), u(), MARKET, SLOT, SLOT - 300, 5.0, 0.09, None, "PV")
        from src.structs import Match

        match = Match(
            trade_id=u(),
            bid=OrderData(u(), u(), MARKET, SLOT, SLOT - 300, 5.0, 0.28),
            offer=order,
            selected_energy_kwh=5.0,
            clearing_price=0.195,
        )
        encoded = abi_encode([MATCH_ABI], [match.to_tuple()])
        assert isinstance(encoded, bytes) and len(encoded) > 0


class TestMatchBuilder:
    def test_buyer_pool_trade_synthesizes_floor_priced_pool_offer(self):
        buyer, bid_id, trade_id = u(), u(), u()
        orders = {bid_id: int_order(bid_id, buyer, "Bid", 6.0, 0.27)}
        trades = [pool_trade(trade_id, bid_id, buyer, 5.4, 0.195)]

        result = build_matches(trades, orders, POOL, k_upper=0.285, k_lower=0.08, time_slot=SLOT)

        assert len(result.matches) == 1
        match = result.matches[0]
        assert match.bid.order_id == bid_id
        assert match.offer.created_by == POOL
        assert match.offer.energy_rate == 0.08  # floor ⇒ never a PriceMismatch
        assert match.offer.order_id == pool_settle_order_uuid(trade_id)
        assert len(result.pool_orders) == 1
        assert result.pool_orders[0].is_bid is False

    def test_pool_seller_trade_synthesizes_ceiling_priced_pool_bid(self):
        seller, offer_id, trade_id = u(), u(), u()
        orders = {offer_id: int_order(offer_id, seller, "Offer", 5.0, 0.09, "PV")}
        trades = [pool_trade(trade_id, offer_id, seller, 5.0, 0.195, seller_is_pool=False)]

        result = build_matches(trades, orders, POOL, k_upper=0.285, k_lower=0.08, time_slot=SLOT)

        match = result.matches[0]
        assert match.offer.order_id == offer_id
        assert match.bid.created_by == POOL
        assert match.bid.energy_rate == 0.285  # ceiling
        assert result.pool_orders[0].is_bid is True

    def test_direct_pair_uses_two_real_orders_and_no_pool_orders(self):
        buyer, seller, bid_id, offer_id = u(), u(), u(), u()
        orders = {
            bid_id: int_order(bid_id, buyer, "Bid", 5.0, 0.27),
            offer_id: int_order(offer_id, seller, "Offer", 5.0, 0.09),
        }
        trades = [
            {
                "tradeId": u(),
                "marketId": MARKET,
                "bidId": bid_id,
                "buyerId": buyer,
                "offerId": offer_id,
                "sellerId": seller,
                "tradeStatus": "settled",
                "tradeQuantity": 5.0,
                "tradePrice": 0.195,
                "tradedAt": "2026-08-24T14:00:00Z",
            }
        ]
        result = build_matches(trades, orders, POOL, k_upper=0.285, k_lower=0.08, time_slot=SLOT)
        assert result.pool_orders == []
        assert result.matches[0].bid.order_id == bid_id
        assert result.matches[0].offer.order_id == offer_id


class TestValidator:
    def _match(self, bid_limit=0.28, offer_limit=0.09, price=0.195, qty=5.0):
        from src.structs import Match

        return Match(
            trade_id=u(),
            bid=OrderData(u(), u(), MARKET, SLOT, SLOT - 300, 5.0, bid_limit),
            offer=OrderData(u(), u(), MARKET, SLOT, SLOT - 300, 5.0, offer_limit),
            selected_energy_kwh=qty,
            clearing_price=price,
        )

    def test_valid_match_passes(self):
        assert validate_match(self._match()) == []

    def test_buyer_limit_below_clearing_is_flagged(self):
        """The AMM-vs-contract limit-price conflict must be visible pre-flight."""
        violations = validate_match(self._match(bid_limit=0.10, price=0.195))
        assert any(v.code == "PriceMismatch" for v in violations)

    def test_energy_over_allocation_is_flagged(self):
        violations = validate_match(self._match(qty=9.0))
        assert any(v.code == "EnergyMismatch" for v in violations)

    def test_timeslot_mismatch_is_flagged(self):
        from src.structs import Match

        match = Match(
            trade_id=u(),
            bid=OrderData(u(), u(), MARKET, SLOT, SLOT - 300, 5.0, 0.28),
            offer=OrderData(u(), u(), MARKET, SLOT + 900, SLOT - 300, 5.0, 0.09),
            selected_energy_kwh=5.0,
            clearing_price=0.195,
        )
        assert any(v.code == "InvalidOrderParams" for v in validate_match(match))


class FakeChain:
    def __init__(self):
        self.placed: list[tuple] = []
        self.batches: list[list[tuple]] = []

    async def place_order(self, params_tuple):
        self.placed.append(params_tuple)
        return f"0xplace{len(self.placed)}"

    async def settle_batch(self, match_tuples):
        self.batches.append(match_tuples)
        return f"0xsettle{len(self.batches)}"


class TestEngine:
    def _build(self):
        buyer, bid_id, trade_id = u(), u(), u()
        orders = {bid_id: int_order(bid_id, buyer, "Bid", 6.0, 0.27)}
        trades = [pool_trade(trade_id, bid_id, buyer, 5.4, 0.195)]
        return build_matches(trades, orders, POOL, k_upper=0.285, k_lower=0.08, time_slot=SLOT)

    @pytest.mark.asyncio
    async def test_happy_path_places_pool_orders_then_settles(self):
        chain = FakeChain()
        engine = SettlementEngine(chain)
        build = self._build()

        report = await engine.settle(build)

        assert len(chain.placed) == 1
        assert len(chain.batches) == 1
        assert len(report.settled) == 1
        assert report.rejected == {}

    @pytest.mark.asyncio
    async def test_idempotent_rerun_settles_nothing(self):
        chain = FakeChain()
        ledger = SettlementLedger()
        engine = SettlementEngine(chain, ledger)
        build = self._build()

        await engine.settle(build)
        report2 = await engine.settle(build)

        assert report2.settled == {}
        assert len(report2.skipped_already_settled) == 1
        assert len(chain.batches) == 1  # no second transaction

    @pytest.mark.asyncio
    async def test_invalid_match_is_rejected_without_burning_gas(self):
        chain = FakeChain()
        engine = SettlementEngine(chain)
        buyer, bid_id, trade_id = u(), u(), u()
        # Buyer limit below clearing price → contract would revert; we reject.
        orders = {bid_id: int_order(bid_id, buyer, "Bid", 6.0, 0.10)}
        trades = [pool_trade(trade_id, bid_id, buyer, 5.4, 0.195)]
        build = build_matches(trades, orders, POOL, k_upper=0.285, k_lower=0.08, time_slot=SLOT)

        report = await engine.settle(build)

        assert trade_id in report.rejected
        assert chain.batches == []
        assert chain.placed == []

    @pytest.mark.asyncio
    async def test_batching_splits_large_sets(self):
        chain = FakeChain()
        engine = SettlementEngine(chain, batch_size=2)
        builds = [self._build() for _ in range(3)]
        from src.match_builder import BuildResult

        merged = BuildResult(
            matches=[m for b in builds for m in b.matches],
            pool_orders=[p for b in builds for p in b.pool_orders],
        )
        report = await engine.settle(merged)
        assert len(report.settled) == 3
        assert len(chain.batches) == 2  # 2 + 1
