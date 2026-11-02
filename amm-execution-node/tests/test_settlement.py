"""Tests for the settlement engine skeleton: structs, builder, validator, engine."""

import uuid

import pytest
from eth_abi import encode as abi_encode
from src.engine import SettlementEngine, SettlementLedger
from src.ids import ZERO_BYTES16, actor_onchain_id, bytes16_to_uuid, uuid_to_bytes16
from src.match_builder import (
    BuildResult,
    build_settlements,
    pool_settle_order_uuid,
    residual_order_uuid,
)
from src.structs import (
    MARKET_SETTLEMENT_ABI,
    MATCH_TYPE_PREFERRED,
    MATCH_TYPE_STANDARD,
    ClearingResult,
    MarketSettlement,
    Match,
    OrderParams,
    energy_type_code,
    scale,
)
from src.validator import validate_match, validate_settlement

POOL = str(uuid.uuid4())
MARKET = str(uuid.uuid4())
SLOT = 1787580000
K_UPPER, K_LOWER = 0.285, 0.08


def u() -> str:
    return str(uuid.uuid4())


def int_order(order_id, actor, otype, kwh, limit, energy_type=None, partner=None, market=MARKET):
    order = {
        "orderId": order_id,
        "marketId": market,
        "orderType": otype,
        "orderStatus": "submitted",
        "timeSlot": SLOT,
        "quantity": kwh,
        "priceLimit": limit,
        "createdBy": actor,
        "creationTime": SLOT - 300,
    }
    if energy_type:
        order["energyType"] = energy_type
    if partner:
        order["preferredTradingPartner"] = partner
    return order


def pool_trade(trade_id, order_id, actor, qty, price, seller_is_pool=True, market=MARKET):
    pool_order = pool_settle_order_uuid(trade_id)
    return {
        "tradeId": trade_id,
        "marketId": market,
        "bidId": order_id if seller_is_pool else pool_order,
        "buyerId": actor if seller_is_pool else POOL,
        "offerId": pool_order if seller_is_pool else order_id,
        "sellerId": POOL if seller_is_pool else actor,
        "tradeStatus": "matched",
        "tradeQuantity": qty,
        "tradePrice": price,
        "timestamp": "2026-08-24T14:00:00Z",
    }


def direct_trade(trade_id, bid_id, buyer, offer_id, seller, qty, price):
    return {
        "tradeId": trade_id,
        "marketId": MARKET,
        "bidId": bid_id,
        "buyerId": buyer,
        "offerId": offer_id,
        "sellerId": seller,
        "tradeStatus": "matched",
        "tradeQuantity": qty,
        "tradePrice": price,
        "timestamp": "2026-08-24T14:00:00Z",
    }


def clearing_result(traded, market=MARKET, price=0.195, supply=None, demand=None):
    return {
        "marketId": market,
        "clearingStatus": "final",
        "clearingPrice": price,
        "totalSupply": traded if supply is None else supply,
        "totalDemand": traded if demand is None else demand,
        "tradeQuantity": traded,
        "numTrades": 0,
        "createdAt": "2026-08-24T14:00:00Z",
    }


def order_params(is_bid, rate, kwh=5.0, actor=None, slot=SLOT, **kwargs):
    return OrderParams(
        order_id=u(),
        created_by=actor or u(),
        market_id=MARKET,
        time_slot=slot,
        creation_time=SLOT - 300,
        energy_kwh=kwh,
        energy_rate=rate,
        is_bid=is_bid,
        **kwargs,
    )


def build(trades, orders, results):
    return build_settlements(trades, orders, results, POOL, k_upper=K_UPPER, k_lower=K_LOWER)


class TestIds:
    def test_roundtrip(self):
        value = u()
        assert bytes16_to_uuid(uuid_to_bytes16(value)) == value

    def test_bytes16_is_16_bytes(self):
        assert len(uuid_to_bytes16(u())) == 16


class TestStructs:
    def test_energy_type_codes(self):
        assert energy_type_code("PV") == 2
        assert energy_type_code("battery") == 5
        assert energy_type_code(None) == 0

    def test_grey_is_no_longer_an_energy_type(self):
        with pytest.raises(ValueError):
            energy_type_code("GREY")

    def test_unknown_energy_type_raises(self):
        with pytest.raises(ValueError):
            energy_type_code("FUSION")

    def test_scaling(self):
        assert scale(19.5246) == 195246
        assert scale(0.285) == 2850

    def test_order_params_tuple_carries_preference_fields(self):
        partner = u()
        params = order_params(
            True,
            0.27,
            energy_type="PV",
            preferred_trading_partner=partner,
            preferred_energy_rate=0.2,
        )
        encoded = params.to_tuple()
        assert len(encoded) == 12
        assert encoded[8] == 2  # energyType PV
        assert encoded[9] is True  # isBid
        assert encoded[10] == actor_onchain_id(partner)
        assert encoded[11] == 2000

    def test_order_params_without_preferences_encode_zero(self):
        encoded = order_params(False, 0.09).to_tuple()
        assert encoded[10] == ZERO_BYTES16
        assert encoded[11] == 0

    def test_clearing_result_status_code(self):
        result = ClearingResult(MARKET, "no_bid", 0.195, 0.0, 0.0, 0.0, 0)
        assert result.to_tuple()[1] == 4

    def test_market_settlement_abi_encodes(self):
        """The MarketSettlement tuple must be encodable with the declared signature."""
        match = Match(
            trade_id=u(),
            bid=order_params(True, 0.28),
            offer=order_params(False, 0.09, energy_type="PV"),
            selected_energy_kwh=5.0,
            clearing_price=0.195,
        )
        settlement = MarketSettlement(
            MARKET, (match,), ClearingResult(MARKET, "final", 0.195, 5.0, 5.0, 5.0, 1)
        )
        encoded = abi_encode([MARKET_SETTLEMENT_ABI], [settlement.to_tuple()])
        assert isinstance(encoded, bytes) and len(encoded) > 0

    def test_chain_client_components_match_struct_signatures(self):
        """chain.py's hand-declared ABI components describe the structs.py encodings."""
        from src import chain, structs

        def signature(components):
            parts = []
            for c in components:
                if c["type"].startswith("tuple"):
                    parts.append(signature(c["components"]) + c["type"][len("tuple") :])
                else:
                    parts.append(c["type"])
            return "(" + ",".join(parts) + ")"

        assert signature(chain._ORDER_PARAMS) == structs.ORDER_PARAMS_ABI
        assert signature(chain._MATCH) == structs.MATCH_ABI
        assert signature(chain._CLEARING_RESULT) == structs.CLEARING_RESULT_ABI
        assert signature(chain._MARKET_SETTLEMENT) == structs.MARKET_SETTLEMENT_ABI

    def test_chain_client_abi_fragments_encode_engine_structs(self):
        """The hand-declared ABI fragments in chain.py accept the engine's tuples."""
        from src.chain import SettlementChainClient

        client = SettlementChainClient(
            rpc_url="http://localhost:8545",
            order_registry_address="0x" + "11" * 20,
            trade_settlement_address="0x" + "22" * 20,
            private_key="0x" + "33" * 32,
        )
        offer = order_params(False, 0.09, energy_type="PV")
        match = Match(
            trade_id=u(),
            bid=order_params(True, 0.28),
            offer=offer,
            selected_energy_kwh=5.0,
            clearing_price=0.195,
        )
        settlement = MarketSettlement(
            MARKET, (match,), ClearingResult(MARKET, "final", 0.195, 5.0, 5.0, 5.0, 1)
        )
        place = client.registry.functions.placeOrder(offer.to_tuple())
        settle = client.settlement.functions.settleBatch([settlement.to_tuple()])
        assert place._encode_transaction_data().startswith("0x")
        assert settle._encode_transaction_data().startswith("0x")


class TestMatchBuilder:
    def test_buyer_pool_trade_synthesizes_floor_priced_pool_offer(self):
        buyer, bid_id, trade_id = u(), u(), u()
        orders = {bid_id: int_order(bid_id, buyer, "bid", 5.4, 0.27)}
        trades = [pool_trade(trade_id, bid_id, buyer, 5.4, 0.195)]

        result = build(trades, orders, [clearing_result(5.4)])

        assert len(result.matches) == 1
        match = result.matches[0]
        assert match.match_type == MATCH_TYPE_STANDARD
        assert match.bid.order_id == bid_id
        assert match.bid.is_bid is True
        assert match.offer.created_by == POOL
        assert match.offer.energy_rate == K_LOWER  # floor ⇒ never a PriceMismatch
        assert match.offer.order_id == pool_settle_order_uuid(trade_id)
        assert result.pool_orders == [match.offer]
        assert result.pool_orders[0].is_bid is False

    def test_pool_seller_trade_synthesizes_ceiling_priced_pool_bid(self):
        seller, offer_id, trade_id = u(), u(), u()
        orders = {offer_id: int_order(offer_id, seller, "offer", 5.0, 0.09, "PV")}
        trades = [pool_trade(trade_id, offer_id, seller, 5.0, 0.195, seller_is_pool=False)]

        result = build(trades, orders, [clearing_result(5.0)])

        match = result.matches[0]
        assert match.offer.order_id == offer_id
        assert match.offer.energy_type == "PV"
        assert match.bid.created_by == POOL
        assert match.bid.energy_rate == K_UPPER  # ceiling
        assert result.pool_orders[0].is_bid is True

    def test_direct_pair_is_a_preferred_match_without_pool_orders(self):
        buyer, seller, bid_id, offer_id = u(), u(), u(), u()
        orders = {
            bid_id: int_order(bid_id, buyer, "bid", 5.0, 0.27, partner=seller),
            offer_id: int_order(offer_id, seller, "offer", 5.0, 0.09, partner=buyer),
        }
        trades = [direct_trade(u(), bid_id, buyer, offer_id, seller, 5.0, 0.195)]

        result = build(trades, orders, [clearing_result(5.0)])

        assert result.pool_orders == []
        match = result.matches[0]
        assert match.match_type == MATCH_TYPE_PREFERRED
        assert (match.bid.order_id, match.offer.order_id) == (bid_id, offer_id)
        assert match.bid.preferred_trading_partner == seller
        assert validate_settlement(result.settlements[0]) == []

    def test_partial_fill_leaves_a_residual_the_next_match_consumes(self):
        """A bid filled first by a direct trade, then by the pool, chains through its residual."""
        buyer, seller, bid_id, offer_id = u(), u(), u(), u()
        direct_id, pool_id = u(), u()
        orders = {
            bid_id: int_order(bid_id, buyer, "bid", 6.0, 0.27, partner=seller),
            offer_id: int_order(offer_id, seller, "offer", 2.0, 0.09, partner=buyer),
        }
        trades = [
            direct_trade(direct_id, bid_id, buyer, offer_id, seller, 2.0, 0.195),
            pool_trade(pool_id, bid_id, buyer, 4.0, 0.195),
        ]

        result = build(trades, orders, [clearing_result(6.0)])

        first, second = result.matches
        residual = residual_order_uuid(bid_id, direct_id)
        assert first.residual_bid_id == residual
        assert first.residual_offer_id is None  # offer fully filled
        assert second.bid.order_id == residual
        assert second.bid.energy_kwh == 4.0
        assert second.residual_bid_id is None
        assert validate_match(second) == []

    def test_matches_are_grouped_per_market_with_their_clearing_result(self):
        other = u()
        b1, b2, a1, a2 = u(), u(), u(), u()
        orders = {
            b1: int_order(b1, a1, "bid", 3.0, 0.27),
            b2: int_order(b2, a2, "bid", 2.0, 0.27, market=other),
        }
        trades = [
            pool_trade(u(), b1, a1, 3.0, 0.195),
            pool_trade(u(), b2, a2, 2.0, 0.195, market=other),
        ]
        # The storage may hand back the market id in its 0x-hex form.
        results = [clearing_result(3.0), clearing_result(2.0, market="0x" + other.replace("-", ""))]

        result = build(trades, orders, results)

        assert len(result.settlements) == 2
        by_market = {uuid_to_bytes16(s.market_id): s for s in result.settlements}
        assert by_market[uuid_to_bytes16(other)].clearing_result.traded_quantity_kwh == 2.0
        assert all(s.clearing_result.num_trades == 1 for s in result.settlements)

    def test_missing_clearing_result_raises(self):
        buyer, bid_id = u(), u()
        orders = {bid_id: int_order(bid_id, buyer, "bid", 5.0, 0.27)}
        with pytest.raises(ValueError, match="no clearing result"):
            build([pool_trade(u(), bid_id, buyer, 5.0, 0.195)], orders, [])

    def test_pool_on_both_sides_raises(self):
        trade = pool_trade(u(), u(), POOL, 5.0, 0.195)
        with pytest.raises(ValueError, match="pool on both sides"):
            build([trade], {}, [clearing_result(5.0)])


class TestValidator:
    def _match(self, bid_limit=0.28, offer_limit=0.09, price=0.195, qty=5.0, **kwargs):
        return Match(
            trade_id=u(),
            bid=order_params(True, bid_limit),
            offer=order_params(False, offer_limit),
            selected_energy_kwh=qty,
            clearing_price=price,
            **kwargs,
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
        match = Match(
            trade_id=u(),
            bid=order_params(True, 0.28),
            offer=order_params(False, 0.09, slot=SLOT + 900),
            selected_energy_kwh=5.0,
            clearing_price=0.195,
        )
        assert any(v.code == "InvalidOrderParams" for v in validate_match(match))

    def test_self_trade_is_flagged(self):
        actor = u()
        match = Match(
            trade_id=u(),
            bid=order_params(True, 0.28, actor=actor),
            offer=order_params(False, 0.09, actor=actor),
            selected_energy_kwh=5.0,
            clearing_price=0.195,
        )
        assert any(v.code == "InvalidOrderParams" for v in validate_match(match))

    def test_wrong_side_flag_is_flagged(self):
        match = Match(
            trade_id=u(),
            bid=order_params(False, 0.28),
            offer=order_params(False, 0.09),
            selected_energy_kwh=5.0,
            clearing_price=0.195,
        )
        assert any(v.code == "InvalidOrderParams" for v in validate_match(match))

    def test_preferred_match_needs_a_declared_partner(self):
        violations = validate_match(self._match(match_type=MATCH_TYPE_PREFERRED))
        assert any(v.code == "InvalidPreferredPartner" for v in violations)

    def test_preferred_partner_must_be_the_counterparty(self):
        match = Match(
            trade_id=u(),
            bid=order_params(True, 0.28, preferred_trading_partner=u()),
            offer=order_params(False, 0.09),
            selected_energy_kwh=5.0,
            clearing_price=0.195,
            match_type=MATCH_TYPE_PREFERRED,
        )
        assert any(v.code == "InvalidPreferredPartner" for v in validate_match(match))

    def test_preferred_match_prices_against_the_preferred_rate(self):
        seller = u()
        bid = order_params(True, 0.28, preferred_trading_partner=seller, preferred_energy_rate=0.15)
        match = Match(
            trade_id=u(),
            bid=bid,
            offer=order_params(False, 0.09, actor=seller),
            selected_energy_kwh=5.0,
            clearing_price=0.195,  # within the limit 0.28, above the preferred 0.15
            match_type=MATCH_TYPE_PREFERRED,
        )
        assert any(v.code == "PriceMismatch" for v in validate_match(match))

    def test_two_leg_pool_market_fails_the_traded_quantity_check(self):
        """A pool allocation is two matches; the contract sums them against tradedQuantity."""
        buyer, seller, bid_id, offer_id = u(), u(), u(), u()
        orders = {
            bid_id: int_order(bid_id, buyer, "bid", 5.0, 0.27),
            offer_id: int_order(offer_id, seller, "offer", 5.0, 0.09),
        }
        trades = [
            pool_trade(u(), bid_id, buyer, 5.0, 0.195),
            pool_trade(u(), offer_id, seller, 5.0, 0.195, seller_is_pool=False),
        ]
        settlement = build(trades, orders, [clearing_result(5.0)]).settlements[0]

        violations = validate_settlement(settlement)

        assert [v.code for v in violations] == ["TradedQuantityMismatch"]
        assert violations[0].subject == MARKET


class FakeChain:
    def __init__(self):
        self.placed: list[tuple] = []
        self.batches: list[list[tuple]] = []

    async def place_order(self, params_tuple):
        self.placed.append(params_tuple)
        return f"0xplace{len(self.placed)}"

    async def settle_batch(self, settlement_tuples):
        self.batches.append(settlement_tuples)
        return f"0xsettle{len(self.batches)}"


def one_leg_build(market=MARKET, limit=0.27):
    """One buyer→pool match whose clearing result reports that leg, so the market
    passes the quantity check and the tests exercise the engine's mechanics."""
    buyer, bid_id = u(), u()
    orders = {bid_id: int_order(bid_id, buyer, "bid", 5.4, limit, market=market)}
    trades = [pool_trade(u(), bid_id, buyer, 5.4, 0.195, market=market)]
    return build(trades, orders, [clearing_result(5.4, market=market)])


def merge(builds):
    return BuildResult(
        settlements=[s for b in builds for s in b.settlements],
        pool_orders=[p for b in builds for p in b.pool_orders],
    )


class TestEngine:
    @pytest.mark.asyncio
    async def test_happy_path_places_pool_orders_then_settles(self):
        chain = FakeChain()
        report = await SettlementEngine(chain).settle(one_leg_build())

        assert len(chain.placed) == 1
        assert len(chain.batches) == 1
        assert report.settled == {MARKET: "0xsettle1"}
        assert report.rejected == {}

    @pytest.mark.asyncio
    async def test_idempotent_rerun_settles_nothing(self):
        chain = FakeChain()
        engine = SettlementEngine(chain, SettlementLedger())
        result = one_leg_build()

        await engine.settle(result)
        report2 = await engine.settle(result)

        assert report2.settled == {}
        assert report2.skipped_already_settled == [MARKET]
        assert len(chain.batches) == 1  # no second transaction

    @pytest.mark.asyncio
    async def test_invalid_market_is_held_back_without_burning_gas(self):
        chain = FakeChain()
        # Buyer limit below clearing price → the contract would revert; we hold back.
        report = await SettlementEngine(chain).settle(one_leg_build(limit=0.10))

        assert MARKET in report.rejected
        assert chain.batches == []
        assert chain.placed == []

    @pytest.mark.asyncio
    async def test_one_bad_market_does_not_block_the_others(self):
        chain = FakeChain()
        good, bad = u(), u()
        result = merge([one_leg_build(market=good), one_leg_build(market=bad, limit=0.10)])

        report = await SettlementEngine(chain).settle(result)

        assert set(report.settled) == {good}
        assert set(report.rejected) == {bad}
        assert len(chain.placed) == 1  # only the good market's pool order

    @pytest.mark.asyncio
    async def test_transactions_pack_whole_markets(self):
        chain = FakeChain()
        result = merge([one_leg_build(market=u()) for _ in range(3)])

        report = await SettlementEngine(chain, batch_size=2).settle(result)

        assert len(report.settled) == 3
        assert [len(batch) for batch in chain.batches] == [2, 1]

    @pytest.mark.asyncio
    async def test_market_larger_than_batch_size_is_sent_alone(self):
        chain = FakeChain()
        buyers = [(u(), u()) for _ in range(3)]
        orders = {b: int_order(b, a, "bid", 1.0, 0.27) for a, b in buyers}
        trades = [pool_trade(u(), b, a, 1.0, 0.195) for a, b in buyers]
        big = build(trades, orders, [clearing_result(3.0)])
        small = one_leg_build(market=u())

        await SettlementEngine(chain, batch_size=2).settle(merge([big, small]))

        assert [len(batch) for batch in chain.batches] == [1, 1]
        assert len(chain.batches[0][0][0]) == 3  # the big market's three matches together


class TestGsyIdConventions:
    """Parity with primitives/src/utils/mod.rs (upstream commit 648b346)."""

    def test_uuid_and_hex_forms_agree(self):
        from src.ids import parse_uuid_or_hex_bytes16

        value = u()
        as_hex = "0x" + value.replace("-", "")
        assert parse_uuid_or_hex_bytes16(value) == parse_uuid_or_hex_bytes16(as_hex)
        assert parse_uuid_or_hex_bytes16(value) == uuid.UUID(value).bytes

    def test_malformed_id_raises(self):
        from src.ids import parse_uuid_or_hex_bytes16

        with pytest.raises(ValueError):
            parse_uuid_or_hex_bytes16("actor-17")

    def test_actor_id_is_blake2b_128_of_the_string(self):
        """Golden vectors: blake2b digest_size=16 over the exact off-chain string."""
        from src.ids import bytes16_to_hex

        assert bytes16_to_hex(actor_onchain_id("actor-123")) == "0xcebf5331e6b4e617eb4e30298d890eec"
        assert (
            bytes16_to_hex(actor_onchain_id("11111111-1111-4111-8111-111111111111"))
            == "0x36b3fc2cf928ee46278171375a2903b3"
        )

    def test_order_params_encode_actor_via_mapping_not_uuid_bytes(self):
        actor = u()
        params = order_params(False, 0.09, actor=actor)
        encoded = params.to_tuple()
        assert encoded[1] == actor_onchain_id(actor)
        assert encoded[1] != uuid.UUID(actor).bytes
        assert encoded[0] == uuid.UUID(params.order_id).bytes  # order id stays raw UUID bytes


class RecordingRegistrar:
    def __init__(self):
        self.calls: list[list[str]] = []

    async def ensure_mapped(self, offchain_ids):
        self.calls.append(list(offchain_ids))


class TestActorRegistration:
    @pytest.mark.asyncio
    async def test_all_actors_including_pool_are_registered_before_settling(self):
        registrar = RecordingRegistrar()
        result = one_leg_build()
        buyer = result.matches[0].bid.created_by

        await SettlementEngine(FakeChain(), registrar=registrar).settle(result)

        assert len(registrar.calls) == 1
        assert set(registrar.calls[0]) == {buyer, POOL}

    @pytest.mark.asyncio
    async def test_preferred_partners_are_registered(self):
        registrar = RecordingRegistrar()
        buyer, seller, bid_id, offer_id = u(), u(), u(), u()
        orders = {
            bid_id: int_order(bid_id, buyer, "bid", 5.0, 0.27, partner=seller),
            offer_id: int_order(offer_id, seller, "offer", 5.0, 0.09, partner=buyer),
        }
        trades = [direct_trade(u(), bid_id, buyer, offer_id, seller, 5.0, 0.195)]

        await SettlementEngine(FakeChain(), registrar=registrar).settle(
            build(trades, orders, [clearing_result(5.0)])
        )

        assert set(registrar.calls[0]) == {buyer, seller}

    @pytest.mark.asyncio
    async def test_nothing_registered_when_nothing_fresh(self):
        registrar = RecordingRegistrar()
        engine = SettlementEngine(FakeChain(), SettlementLedger(), registrar=registrar)
        result = one_leg_build()

        await engine.settle(result)
        await engine.settle(result)  # everything already settled

        assert len(registrar.calls) == 1
