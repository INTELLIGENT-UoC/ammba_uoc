"""Integration tests for the clearing pipeline against the int.* contract."""

import logging
import random
from collections import defaultdict

import pytest
from src.adapters import trade_uuid
from src.clearing import run_clearing
from src.sigmoid import to_node_int

from tests.conftest import (
    MARKET_ID,
    TIME_SLOT_UNIX,
    FakeDBClient,
    actor_uuid,
    make_int_order,
)


async def _clear(orders, community, existing_trades=None, strict_validation=True):
    db = FakeDBClient(orders, existing_trades=existing_trades)
    result = await run_clearing(
        market_id=MARKET_ID,
        community_uuid="11111111-1111-4111-8111-111111111111",
        time_slot=TIME_SLOT_UNIX,
        community_config=community,
        db_client=db,
        contract_client=None,
        time_slot_sec=900,
        strict_validation=strict_validation,
    )
    return result, db


def _sums(trades) -> tuple[dict[str, float], dict[str, float]]:
    """Traded quantity per buyer and per seller, in kWh (exact to the wire precision)."""
    bought: dict[str, int] = defaultdict(int)
    sold: dict[str, int] = defaultdict(int)
    for trade in trades:
        bought[trade["buyerId"]] += to_node_int(trade["tradeQuantity"])
        sold[trade["sellerId"]] += to_node_int(trade["tradeQuantity"])
    return (
        {k: v / 10_000 for k, v in bought.items()},
        {k: v / 10_000 for k, v in sold.items()},
    )


def _is_pref(trade) -> bool:
    return trade["tradeId"] == trade_uuid(
        trade["marketId"], "pref", f"{trade['bidId']}:{trade['offerId']}"
    )


@pytest.mark.asyncio
async def test_basic_clearing(community):
    orders = [
        make_int_order("B1", "Bid", 5.0),
        make_int_order("B2", "Bid", 5.0),
        make_int_order("S1", "Offer", 6.0),
        make_int_order("S2", "Offer", 4.0),
    ]
    result, db = await _clear(orders, community)

    assert result["status"] == "cleared"
    assert result["total_supply_kwh"] == 10.0
    assert result["total_demand_kwh"] == 10.0
    assert result["traded_quantity_kwh"] == 10.0
    # Bilateral matches only: at most n + m − 1 = 3.
    assert 2 <= result["num_trades"] <= 3
    assert len(db.posted_trades) == result["num_trades"]

    buyers = {actor_uuid("B1"), actor_uuid("B2")}
    sellers = {actor_uuid("S1"), actor_uuid("S2")}
    for trade in db.posted_trades:
        assert trade["tradeStatus"] == "matched"
        assert trade["marketId"] == MARKET_ID
        assert trade["buyerId"] in buyers
        assert trade["sellerId"] in sellers
        assert trade["tradePrice"] == result["clearing_price_eur_per_kwh"]

    bought, sold = _sums(db.posted_trades)
    assert bought == {actor_uuid("B1"): 5.0, actor_uuid("B2"): 5.0}
    assert sold == {actor_uuid("S1"): 6.0, actor_uuid("S2"): 4.0}

    # A final clearing result was posted.
    assert len(db.posted_clearing_results) == 1
    cr = db.posted_clearing_results[0]
    assert cr["clearingStatus"] == "final"
    assert cr["numTrades"] == result["num_trades"]
    assert cr["tradeQuantity"] == 10.0


@pytest.mark.asyncio
async def test_supply_exceeds_demand(community):
    orders = [
        make_int_order("B1", "Bid", 5.0),
        make_int_order("S1", "Offer", 8.0),
    ]
    result, db = await _clear(orders, community)

    assert result["status"] == "cleared"
    assert result["traded_quantity_kwh"] == 5.0  # min(8, 5)
    assert len(db.posted_trades) == 1
    trade = db.posted_trades[0]
    assert (trade["buyerId"], trade["sellerId"]) == (actor_uuid("B1"), actor_uuid("S1"))
    assert trade["tradeQuantity"] == 5.0


@pytest.mark.asyncio
async def test_demand_exceeds_supply(community):
    orders = [
        make_int_order("B1", "Bid", 10.0),
        make_int_order("S1", "Offer", 3.0),
    ]
    result, db = await _clear(orders, community)

    assert result["status"] == "cleared"
    assert result["traded_quantity_kwh"] == 3.0
    assert [t["tradeQuantity"] for t in db.posted_trades] == [3.0]


@pytest.mark.asyncio
async def test_no_bids(community):
    orders = [make_int_order("S1", "Offer", 5.0)]
    result, db = await _clear(orders, community)

    assert result["status"] == "no_trade"
    assert len(db.posted_trades) == 0
    # A no_bid clearing result is still recorded.
    assert db.posted_clearing_results[0]["clearingStatus"] == "no_bid"


@pytest.mark.asyncio
async def test_no_offers(community):
    orders = [make_int_order("B1", "Bid", 5.0)]
    result, db = await _clear(orders, community)
    assert result["status"] == "no_trade"


@pytest.mark.asyncio
async def test_idempotency_skips_if_trades_exist(community):
    orders = [make_int_order("B1", "Bid", 5.0), make_int_order("S1", "Offer", 5.0)]
    existing = [{"tradeId": "existing"}]
    result, db = await _clear(orders, community, existing_trades=existing)

    assert result["status"] == "skipped"
    assert len(db.posted_trades) == 0


@pytest.mark.asyncio
async def test_filters_non_matchable_orders(community):
    orders = [
        make_int_order("B1", "Bid", 5.0),
        make_int_order("S1", "Offer", 5.0),
        make_int_order("B2", "Bid", 10.0, status="executed"),
        make_int_order("S2", "Offer", 10.0, status="cancelled"),
    ]
    result, db = await _clear(orders, community)

    assert result["status"] == "cleared"
    assert result["total_supply_kwh"] == 5.0  # only S1
    assert result["total_demand_kwh"] == 5.0  # only B1
    assert result["num_trades"] == 1


@pytest.mark.asyncio
async def test_clears_orders_expired_at_slot_start(community):
    """The storage expires orders once the slot starts; the AMM still clears them."""
    orders = [
        make_int_order("B1", "Bid", 5.0, status="expired"),
        make_int_order("S1", "Offer", 5.0, status="expired"),
        make_int_order("S2", "Offer", 10.0, status="cancelled"),
    ]
    result, db = await _clear(orders, community)

    assert result["status"] == "cleared"
    assert result["total_supply_kwh"] == 5.0  # S1, not the cancelled S2
    assert result["total_demand_kwh"] == 5.0
    assert result["num_trades"] == 1


@pytest.mark.asyncio
async def test_clearing_price_within_bounds(community):
    orders = [make_int_order("B1", "Bid", 5.0), make_int_order("S1", "Offer", 5.0)]
    result, db = await _clear(orders, community)

    price = result["clearing_price_ct_per_kwh"]
    assert community.k_lower_ct_per_kwh <= price <= community.k_upper_ct_per_kwh
    # The wire price is the same value in EUR/kWh, at 4 decimals.
    assert result["clearing_price_eur_per_kwh"] == round(price / 100.0, 4)
    assert db.posted_clearing_results[0]["clearingPrice"] == result["clearing_price_eur_per_kwh"]


@pytest.mark.asyncio
async def test_pro_rata_allocation_multiple_participants(community):
    orders = [
        make_int_order("B1", "Bid", 3.0),
        make_int_order("B2", "Bid", 7.0),
        make_int_order("S1", "Offer", 4.0),
        make_int_order("S2", "Offer", 6.0),
    ]
    result, db = await _clear(orders, community)

    assert result["num_trades"] <= 3
    bought, sold = _sums(db.posted_trades)
    assert bought == {actor_uuid("B1"): 3.0, actor_uuid("B2"): 7.0}
    assert sold == {actor_uuid("S1"): 4.0, actor_uuid("S2"): 6.0}


@pytest.mark.asyncio
async def test_preference_matched_pair_trades_directly(community):
    """Mutual preferred partners trade with each other; the rest is filled bilaterally."""
    orders = [
        make_int_order("B1", "Bid", 5.0, partner=actor_uuid("S1")),
        make_int_order("S1", "Offer", 5.0, partner=actor_uuid("B1")),
        make_int_order("B2", "Bid", 5.0),
        make_int_order("S2", "Offer", 5.0),
    ]
    result, db = await _clear(orders, community)

    assert result["status"] == "cleared"
    assert result["num_trades"] == 2
    direct = [t for t in db.posted_trades if _is_pref(t)]
    assert len(direct) == 1
    assert direct[0]["buyerId"] == actor_uuid("B1")
    assert direct[0]["sellerId"] == actor_uuid("S1")
    assert direct[0]["tradeQuantity"] == 5.0
    (filled,) = [t for t in db.posted_trades if not _is_pref(t)]
    assert (filled["buyerId"], filled["sellerId"]) == (actor_uuid("B2"), actor_uuid("S2"))


@pytest.mark.asyncio
async def test_preference_pair_with_remaining_volume(community):
    """The volume a mutual pair leaves joins the sequential fill."""
    orders = [
        make_int_order("B1", "Bid", 8.0, partner=actor_uuid("S1")),
        make_int_order("S1", "Offer", 3.0, partner=actor_uuid("B1")),
        make_int_order("S2", "Offer", 5.0),
    ]
    result, db = await _clear(orders, community)

    assert result["traded_quantity_kwh"] == 8.0
    direct = [t for t in db.posted_trades if _is_pref(t)]
    assert [(t["sellerId"], t["tradeQuantity"]) for t in direct] == [(actor_uuid("S1"), 3.0)]
    filled = [t for t in db.posted_trades if not _is_pref(t)]
    assert [(t["sellerId"], t["tradeQuantity"]) for t in filled] == [(actor_uuid("S2"), 5.0)]
    assert filled[0]["bidId"] == direct[0]["bidId"]  # the same bid, two trades


@pytest.mark.asyncio
async def test_direct_trades_emitted_once_per_matched_bid(community):
    """A buyer with two bids gets one direct trade per matched bid, not per bid × match."""
    buyer = actor_uuid("B1")
    orders = [
        make_int_order("B1a", "Bid", 3.0, created_by=buyer, partner=actor_uuid("S1")),
        make_int_order("B1b", "Bid", 3.0, created_by=buyer, partner=actor_uuid("S1")),
        make_int_order("S1", "Offer", 5.0, partner=buyer),
    ]
    result, db = await _clear(orders, community)

    assert result["status"] == "cleared"
    trade_ids = [t["tradeId"] for t in db.posted_trades]
    assert len(trade_ids) == len(set(trade_ids))
    direct = [t for t in db.posted_trades if _is_pref(t)]
    assert len(direct) == 2
    assert {t["bidId"] for t in direct} == {orders[0]["orderId"], orders[1]["orderId"]}
    assert sum(t["tradeQuantity"] for t in direct) == 5.0


@pytest.mark.asyncio
async def test_quantities_and_prices_are_rounded_to_four_decimals(community):
    """Bids of 6 and 4 kWh against 9 kWh: B1 gets 5.4, not 5.3999999999999995."""
    orders = [
        make_int_order("B1", "Bid", 6.0),
        make_int_order("B2", "Bid", 4.0),
        make_int_order("S1", "Offer", 9.0),
    ]
    result, db = await _clear(orders, community)

    by_buyer = {t["buyerId"]: t["tradeQuantity"] for t in db.posted_trades}
    assert by_buyer == {actor_uuid("B1"): 5.4, actor_uuid("B2"): 3.6}
    cr = db.posted_clearing_results[0]
    assert cr["clearingPrice"] == round(cr["clearingPrice"], 4)
    for trade in db.posted_trades:
        assert trade["tradePrice"] == cr["clearingPrice"]
    assert cr["tradeQuantity"] == 9.0


@pytest.mark.asyncio
async def test_largest_remainder_keeps_both_sides_equal(community):
    """Three equal bids share 1 kWh: 0.3333 + 0.3333 + 0.3334, summing to exactly 1."""
    orders = [
        make_int_order("B1", "Bid", 1.0),
        make_int_order("B2", "Bid", 1.0),
        make_int_order("B3", "Bid", 1.0),
        make_int_order("S1", "Offer", 1.0),
    ]
    result, db = await _clear(orders, community)

    bought, sold = _sums(db.posted_trades)
    assert sorted(bought.values()) == [0.3333, 0.3333, 0.3334]
    assert sold == {actor_uuid("S1"): 1.0}
    assert db.posted_clearing_results[0]["tradeQuantity"] == 1.0
    assert result["traded_quantity_kwh"] == 1.0


@pytest.mark.asyncio
async def test_clearing_result_states_what_the_trades_carry(community):
    """Uneven quantities: the trades of every side sum to the clearing result's quantity."""
    rng = random.Random(7)
    orders = [make_int_order(f"B{i}", "Bid", round(rng.uniform(0.1, 3.0), 3)) for i in range(5)]
    orders += [make_int_order(f"S{i}", "Offer", round(rng.uniform(0.1, 3.0), 3)) for i in range(4)]
    result, db = await _clear(orders, community)

    traded = to_node_int(db.posted_clearing_results[0]["tradeQuantity"])
    assert sum(to_node_int(t["tradeQuantity"]) for t in db.posted_trades) == traded
    assert result["num_trades"] <= 5 + 4 - 1
    bought, sold = _sums(db.posted_trades)
    short_side = sold if result["total_supply_kwh"] < result["total_demand_kwh"] else bought
    by_actor = {o["createdBy"]: o["quantity"] for o in orders}
    for actor, quantity in short_side.items():
        assert quantity == by_actor[actor]  # the short side trades its full quantity


@pytest.mark.asyncio
async def test_trades_are_deterministic_under_input_order(community):
    orders = [
        make_int_order("B1", "Bid", 2.5),
        make_int_order("B2", "Bid", 1.5),
        make_int_order("B3", "Bid", 4.0),
        make_int_order("S1", "Offer", 3.0),
        make_int_order("S2", "Offer", 3.5),
    ]
    _, first = await _clear(orders, community)
    _, second = await _clear(list(reversed(orders)), community)

    def key(trades):
        return sorted((t["tradeId"], t["tradeQuantity"]) for t in trades)

    assert key(first.posted_trades) == key(second.posted_trades)


@pytest.mark.asyncio
async def test_prosumer_is_not_matched_with_itself(community):
    """An actor with an offer and a bid in the slot trades with others where possible."""
    prosumer = actor_uuid("P")
    orders = [
        make_int_order("P-offer", "Offer", 4.0, created_by=prosumer),
        make_int_order("P-bid", "Bid", 4.0, created_by=prosumer),
        make_int_order("S1", "Offer", 4.0),
        make_int_order("B1", "Bid", 4.0),
    ]
    _, db = await _clear(orders, community)

    assert all(t["buyerId"] != t["sellerId"] for t in db.posted_trades)
    bought, sold = _sums(db.posted_trades)
    assert bought == {prosumer: 4.0, actor_uuid("B1"): 4.0}
    assert sold == {prosumer: 4.0, actor_uuid("S1"): 4.0}


@pytest.mark.asyncio
async def test_differential_pricing_inactive_without_grey_label(community):
    """The ontology has no grey energy type (#85), so no levy can fund a subsidy.

    The levy and subsidy arithmetic itself is covered in test_preferences.py.
    """
    community = community.model_copy(update={"green_subsidy_rate": 0.10, "grey_levy_rate": 0.10})
    orders = [
        make_int_order("B1", "Bid", 10.0),
        make_int_order("GreenS", "Offer", 5.0, energy_type="PV"),
        make_int_order("PlainS", "Offer", 5.0),  # unlabelled
    ]
    result, db = await _clear(orders, community)

    assert result["status"] == "cleared"
    assert result["price_adjustments"] is None
    for trade in db.posted_trades:
        assert trade["tradePrice"] == result["clearing_price_eur_per_kwh"]


@pytest.mark.asyncio
async def test_differential_pricing_is_reported_but_not_priced_into_trades(community, caplog):
    """A match has one price for both sides: adjustments stay in the summary."""
    community = community.model_copy(update={"green_subsidy_rate": 0.10, "grey_levy_rate": 0.10})
    grey = make_int_order("GreyS", "Offer", 5.0)
    grey["energyType"] = "GREY"  # no longer in the ontology: lenient validation only
    orders = [
        make_int_order("B1", "Bid", 10.0),
        make_int_order("GreenS", "Offer", 5.0, energy_type="PV"),
        grey,
    ]
    with caplog.at_level(logging.WARNING, logger="src.clearing"):
        result, db = await _clear(orders, community, strict_validation=False)

    adjustments = result["price_adjustments"]
    assert adjustments is not None
    assert {a["classification"] for a in adjustments["adjustments"]} == {"GREEN", "GREY"}
    for trade in db.posted_trades:
        assert trade["tradePrice"] == result["clearing_price_eur_per_kwh"]
    assert any("differential pricing is configured" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_differential_pricing_off_by_default(community, caplog):
    """With zero rates, every trade settles at the uniform clearing price."""
    orders = [
        make_int_order("B1", "Bid", 5.0),
        make_int_order("S1", "Offer", 5.0, energy_type="PV"),
    ]
    with caplog.at_level(logging.WARNING, logger="src.clearing"):
        result, db = await _clear(orders, community)

    assert result["price_adjustments"] is None
    for trade in db.posted_trades:
        assert trade["tradePrice"] == result["clearing_price_eur_per_kwh"]
    assert not any("differential pricing" in r.message for r in caplog.records)
