"""Tests for the dependency-free int.* schema validator."""

import pytest
from src.ontology import SchemaValidationError, validate_order, validate_trade

from tests.conftest import make_int_order


def _valid_trade():
    return {
        "tradeId": "44444444-4444-4444-8444-444444444444",
        "marketId": "33333333-3333-4333-8333-333333333333",
        "bidId": "aaaaaaaa-0001-4001-8001-000000000001",
        "buyerId": "bbbbbbbb-0001-4001-8001-000000000001",
        "offerId": "aaaaaaaa-0002-4002-8002-000000000002",
        "sellerId": "cccccccc-0001-4001-8001-000000000001",
        "tradeStatus": "matched",
        "tradeQuantity": 5.0,
        "tradePrice": 0.1825,
        "timestamp": "2026-07-01T10:00:00Z",
    }


def test_valid_order_passes():
    validate_order(make_int_order("B1", "Bid", 5.0))


def test_valid_trade_passes():
    validate_trade(_valid_trade())


def test_missing_required_field_fails():
    order = make_int_order("B1", "Bid", 5.0)
    del order["quantity"]
    with pytest.raises(SchemaValidationError, match="quantity"):
        validate_order(order)


def test_bad_enum_fails():
    order = make_int_order("B1", "Bid", 5.0)
    order["orderType"] = "Swap"
    with pytest.raises(SchemaValidationError, match="enum"):
        validate_order(order)


def test_additional_property_fails():
    order = make_int_order("B1", "Bid", 5.0)
    order["energy"] = 5.0  # AMM-internal name leaking onto the wire
    with pytest.raises(SchemaValidationError, match="additional property"):
        validate_order(order)


def test_bad_datetime_fails():
    trade = _valid_trade()
    trade["timestamp"] = "yesterday"
    with pytest.raises(SchemaValidationError, match="date-time"):
        validate_trade(trade)


def test_max_length_fails():
    from src.ontology import validate_clearing_result

    result = {
        "marketId": "33333333-3333-4333-8333-333333333333",
        "clearingStatus": "final",
        "clearingPrice": 0.1825,
        "totalSupply": 1.0,
        "totalDemand": 1.0,
        "tradeQuantity": 1.0,
        "numTrades": 2,
        "txHash": "0x" + "a" * 200,
        "createdAt": "2026-07-01T10:00:00Z",
    }
    with pytest.raises(SchemaValidationError, match="maxLength"):
        validate_clearing_result(result)


def test_non_positive_quantity_fails():
    trade = _valid_trade()
    trade["tradeQuantity"] = 0
    with pytest.raises(SchemaValidationError, match="exclusiveMinimum"):
        validate_trade(trade)
