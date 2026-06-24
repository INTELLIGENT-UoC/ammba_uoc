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


class TestPoolUuids:
    def test_pool_order_uuid_deterministic(self):
        a = adapters.pool_order_uuid("m-1", "bid")
        b = adapters.pool_order_uuid("m-1", "bid")
        assert a == b

    def test_bid_and_offer_uuids_differ(self):
        assert adapters.pool_order_uuid("m-1", "bid") != adapters.pool_order_uuid("m-1", "offer")

    def test_trade_uuid_stable_and_unique(self):
        t1 = adapters.trade_uuid("m-1", "buyer-pool", "order-a")
        t2 = adapters.trade_uuid("m-1", "buyer-pool", "order-a")
        t3 = adapters.trade_uuid("m-1", "buyer-pool", "order-b")
        assert t1 == t2
        assert t1 != t3


class TestIntOrderToInternal:
    def test_field_mapping(self):
        order = make_int_order("B1", "Bid", 5.0, price_limit=0.28)
        internal = adapters.int_order_to_internal(order)
        assert internal["order_id"] == order["orderId"]
        assert internal["created_by"] == order["createdBy"]
        assert internal["energy"] == 5.0
        assert internal["energy_rate"] == 0.28
        assert internal["status"] == "Open"  # Submitted -> Open
        assert internal["time_slot"] == TIME_SLOT_UNIX

    def test_non_matchable_status_passthrough(self):
        order = make_int_order("B1", "Bid", 5.0, status="Cancelled")
        internal = adapters.int_order_to_internal(order)
        assert internal["status"] == "Cancelled"  # not mapped to Open

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
    def test_buyer_pool_trade_is_schema_valid(self):
        bid = adapters.int_order_to_internal(make_int_order("B1", "Bid", 5.0))
        bid["allocated_energy"] = 5.0
        trade = adapters.build_buyer_pool_int_trade(
            bid,
            "22222222-2222-4222-8222-222222222222",
            adapters.pool_order_uuid("m-1", "offer"),
            "33333333-3333-4333-8333-333333333333",
            0.1825,
            "2026-07-01T10:00:00Z",
        )
        validate_trade(trade)
        assert trade["buyerId"] == bid["created_by"]
        assert trade["sellerId"] == "22222222-2222-4222-8222-222222222222"

    def test_pool_seller_trade_is_schema_valid(self):
        offer = adapters.int_order_to_internal(make_int_order("S1", "Offer", 5.0))
        offer["allocated_energy"] = 5.0
        trade = adapters.build_pool_seller_int_trade(
            offer,
            "22222222-2222-4222-8222-222222222222",
            adapters.pool_order_uuid("m-1", "bid"),
            "33333333-3333-4333-8333-333333333333",
            0.1825,
            "2026-07-01T10:00:00Z",
        )
        validate_trade(trade)
        assert trade["sellerId"] == offer["created_by"]

    def test_clearing_result_is_schema_valid(self):
        from src.ontology import validate_clearing_result

        result = adapters.build_int_clearing_result(
            "33333333-3333-4333-8333-333333333333",
            "FINAL",
            0.1825,
            10.0,
            10.0,
            10.0,
            4,
            "0x0",
            "2026-07-01T10:00:00Z",
        )
        validate_clearing_result(result)
