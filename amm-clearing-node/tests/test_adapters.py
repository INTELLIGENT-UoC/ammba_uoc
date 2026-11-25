"""Unit tests for the int.* <-> internal adapter."""

from src import adapters
from src.ontology import validate_trade

from tests.conftest import TIME_SLOT_UNIX, make_int_order


class TestTimeConversion:
    def test_iso_unix_roundtrip(self):
        ts = adapters.iso_to_unix("2026-07-01T10:00:00Z")
        assert ts == TIME_SLOT_UNIX
        assert adapters.unix_to_iso(ts) == "2026-07-01T10:00:00Z"

    def test_iso_with_offset(self):
        # 12:00+02:00 is the same instant as 10:00Z
        assert adapters.iso_to_unix("2026-07-01T12:00:00+02:00") == TIME_SLOT_UNIX


class TestPriceUnits:
    def test_ct_to_eur(self):
        assert adapters.ct_to_eur(18.25) == 0.1825


class TestWirePrecision:
    def test_quantities_and_prices_round_to_four_decimals(self):
        assert adapters.wire_value(5.3999999999999995) == 5.4
        assert adapters.wire_value(0.1952461826815886) == 0.1952

    def test_wire_value_matches_the_on_chain_scaling(self):
        from src.sigmoid import to_node_int

        for value in (0.1952461826815886, 5.3999999999999995, 1 / 3, 12.34565):
            assert to_node_int(adapters.wire_value(value)) == to_node_int(value)


class TestTradeUuids:
    def test_trade_uuid_stable_and_unique(self):
        t1 = adapters.trade_uuid("m-1", "pair", "bid-a:offer-a")
        t2 = adapters.trade_uuid("m-1", "pair", "bid-a:offer-a")
        t3 = adapters.trade_uuid("m-1", "pair", "bid-b:offer-a")
        assert t1 == t2
        assert t1 != t3

    def test_pair_and_pref_kinds_differ(self):
        key = "bid-a:offer-a"
        assert adapters.trade_uuid("m-1", "pair", key) != adapters.trade_uuid("m-1", "pref", key)


class TestIntOrderToInternal:
    def test_field_mapping(self):
        order = make_int_order("B1", "Bid", 5.0, price_limit=0.28)
        internal = adapters.int_order_to_internal(order)
        assert internal["order_id"] == order["orderId"]
        assert internal["created_by"] == order["createdBy"]
        assert internal["energy"] == 5.0
        assert internal["energy_rate"] == 0.28
        assert internal["status"] == "Open"  # submitted -> Open
        assert internal["time_slot"] == TIME_SLOT_UNIX

    def test_non_matchable_status_passthrough(self):
        order = make_int_order("B1", "Bid", 5.0, status="cancelled")
        internal = adapters.int_order_to_internal(order)
        assert internal["status"] == "cancelled"  # not mapped to Open

    def test_expired_is_matchable(self):
        # The storage expires orders at slot start, before the AMM clears.
        order = make_int_order("B1", "Bid", 5.0, status="expired")
        assert adapters.int_order_to_internal(order)["status"] == "Open"

    def test_flat_preferences_become_nested(self):
        order = make_int_order(
            "B1",
            "Bid",
            5.0,
            partner="cccccccc-0001-4001-8001-000000000001",
            energy_source="GREEN",
        )
        internal = adapters.int_order_to_internal(order)
        assert internal["requirements"]["trading_partner_id"] == [
            "cccccccc-0001-4001-8001-000000000001"
        ]
        assert internal["requirements"]["energy_source"] == ["GREEN"]

    def test_energy_type_becomes_attributes(self):
        order = make_int_order("S1", "Offer", 5.0, energy_type="PV")
        internal = adapters.int_order_to_internal(order)
        assert internal["attributes"]["energy_type"] == ["PV"]


class TestBuildIntTrades:
    MARKET = "33333333-3333-4333-8333-333333333333"

    def test_bilateral_trade_is_schema_valid(self):
        bid = adapters.int_order_to_internal(make_int_order("B1", "Bid", 5.0))
        offer = adapters.int_order_to_internal(make_int_order("S1", "Offer", 5.0))
        trade = adapters.build_bilateral_int_trade(
            bid, offer, 5.0, self.MARKET, 0.1825, "2026-07-01T10:00:00Z"
        )
        validate_trade(trade)
        assert (trade["bidId"], trade["buyerId"]) == (bid["order_id"], bid["created_by"])
        assert (trade["offerId"], trade["sellerId"]) == (offer["order_id"], offer["created_by"])
        assert trade["tradeId"] == adapters.trade_uuid(
            self.MARKET, "pair", f"{bid['order_id']}:{offer['order_id']}"
        )

    def test_trade_values_are_at_wire_precision(self):
        bid = adapters.int_order_to_internal(make_int_order("B1", "Bid", 6.0))
        offer = adapters.int_order_to_internal(make_int_order("S1", "Offer", 9.0))
        trade = adapters.build_bilateral_int_trade(
            bid, offer, 5.3999999999999995, self.MARKET, 0.1952461826815886, "2026-07-01T10:00:00Z"
        )
        assert trade["tradeQuantity"] == 5.4
        assert trade["tradePrice"] == 0.1952

    def test_direct_and_bilateral_trades_of_one_pair_have_distinct_ids(self):
        bid = adapters.int_order_to_internal(make_int_order("B1", "Bid", 5.0))
        offer = adapters.int_order_to_internal(make_int_order("S1", "Offer", 5.0))
        match = {
            "bid_order_id": bid["order_id"],
            "offer_order_id": offer["order_id"],
            "buyer": bid["created_by"],
            "seller": offer["created_by"],
            "energy": 2.0,
        }
        direct = adapters.build_direct_int_trade(match, self.MARKET, 0.18, "2026-07-01T10:00:00Z")
        pair = adapters.build_bilateral_int_trade(
            bid, offer, 3.0, self.MARKET, 0.18, "2026-07-01T10:00:00Z"
        )
        assert direct["tradeId"] != pair["tradeId"]

    def test_clearing_result_is_schema_valid(self):
        from src.ontology import validate_clearing_result

        result = adapters.build_int_clearing_result(
            "33333333-3333-4333-8333-333333333333",
            "final",
            0.1825,
            10.0,
            10.0,
            10.0,
            4,
            "0x0",
            "2026-07-01T10:00:00Z",
        )
        validate_clearing_result(result)

    def test_clearing_result_values_are_at_wire_precision(self):
        result = adapters.build_int_clearing_result(
            "33333333-3333-4333-8333-333333333333",
            "final",
            0.1952461826815886,
            9.00001,
            10.0,
            8.999999999999998,
            2,
            "0x0",
            "2026-07-01T10:00:00Z",
        )
        assert result["clearingPrice"] == 0.1952
        assert result["totalSupply"] == 9.0
        assert result["tradeQuantity"] == 9.0


class TestStorageMarketId:
    def test_uuid_becomes_storage_hex(self):
        assert (
            adapters.storage_market_id("33333333-3333-4333-8333-333333333333")
            == "0x33333333333343338333333333333333"
        )

    def test_hex_forms_are_normalised(self):
        assert adapters.storage_market_id("0xABCDEF0123456789ABCDEF0123456789") == (
            "0xabcdef0123456789abcdef0123456789"
        )
        assert adapters.storage_market_id("abcdef0123456789abcdef0123456789") == (
            "0xabcdef0123456789abcdef0123456789"
        )

    def test_other_values_pass_through(self):
        assert adapters.storage_market_id("market-1") == "market-1"
