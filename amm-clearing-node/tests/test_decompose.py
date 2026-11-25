"""Unit tests for integer apportionment and the sequential fill (src/decompose.py)."""

import random
from collections import defaultdict

import pytest
from src.decompose import apportion, sequential_fill


def order(actor: str, order_id: str) -> dict:
    return {"created_by": actor, "order_id": order_id}


def per_order(matches, side: int) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for match in matches:
        totals[match[side]["order_id"]] += match[2]
    return dict(totals)


def random_sides(rng: random.Random, n: int, m: int, shared_actors: bool = False):
    """Two sides with the same integer total; optionally with prosumers on both."""
    offer_units = [rng.randint(1, 50_000) for _ in range(n)]
    bid_weights = [rng.randint(1, 50_000) for _ in range(m)]
    bid_units = apportion(bid_weights, sum(offer_units))
    actors = [f"actor-{k}" for k in range(max(n, m))]

    def actor(k: int, prefix: str) -> str:
        return rng.choice(actors) if shared_actors else f"{prefix}-{k}"

    offers = [(order(actor(k, "seller"), f"offer-{k}"), q) for k, q in enumerate(offer_units)]
    bids = [(order(actor(k, "buyer"), f"bid-{k}"), q) for k, q in enumerate(bid_units)]
    return offers, bids


class TestApportion:
    def test_exact_quotas_need_no_rounding(self):
        assert apportion([30_000, 70_000], 50_000) == [15_000, 35_000]

    def test_largest_remainder_takes_the_leftover_unit(self):
        # Quotas 0.6, 0.6, 0.8 units of 2: floors 0, 0, 0; leftover 2 to the
        # largest remainders (index 2, then index 0 by tie order).
        assert apportion([3, 3, 4], 2) == [1, 0, 1]

    def test_equal_weights_tie_break_by_index(self):
        assert apportion([1, 1, 1], 10_000) == [3_334, 3_333, 3_333]

    def test_short_side_receives_its_full_weights(self):
        weights = [12_345, 6_789, 1]
        assert apportion(weights, sum(weights)) == weights

    def test_zero_total_and_zero_weights(self):
        assert apportion([0, 0], 0) == [0, 0]
        assert apportion([5, 0], 0) == [0, 0]
        assert apportion([], 0) == []

    def test_positive_total_over_zero_weights_raises(self):
        with pytest.raises(ValueError):
            apportion([0, 0], 1)

    def test_negative_input_raises(self):
        with pytest.raises(ValueError):
            apportion([1, -1], 0)

    def test_properties_on_random_inputs(self):
        rng = random.Random(1)
        for _ in range(500):
            weights = [rng.randint(0, 100_000) for _ in range(rng.randint(1, 12))]
            if not sum(weights):
                continue
            total = rng.randint(0, sum(weights))
            shares = apportion(weights, total)
            assert sum(shares) == total
            for weight, share in zip(weights, shares, strict=True):
                exact = weight * total / sum(weights)
                assert share <= weight
                assert abs(share - exact) < 1


class TestSequentialFill:
    def test_cuts_at_every_boundary(self):
        offers = [(order("s1", "o1"), 6), (order("s2", "o2"), 4)]
        bids = [(order("b1", "d1"), 5), (order("b2", "d2"), 5)]

        matches = sequential_fill(offers, bids)

        assert [(o["order_id"], b["order_id"], q) for o, b, q in matches] == [
            ("o1", "d1", 5),
            ("o1", "d2", 1),
            ("o2", "d2", 4),
        ]

    def test_sorts_by_actor_then_order_id(self):
        offers = [(order("s2", "o0"), 2), (order("s1", "o9"), 1), (order("s1", "o3"), 1)]
        bids = [(order("b1", "d1"), 4)]

        matches = sequential_fill(offers, bids)

        assert [o["order_id"] for o, _, _ in matches] == ["o3", "o9", "o0"]

    def test_properties_on_random_inputs(self):
        rng = random.Random(2)
        for _ in range(300):
            n, m = rng.randint(1, 8), rng.randint(1, 8)
            offers, bids = random_sides(rng, n, m)

            matches = sequential_fill(offers, bids)

            assert len(matches) <= n + m - 1
            assert all(q > 0 for _, _, q in matches)
            assert per_order(matches, 0) == {o["order_id"]: q for o, q in offers if q}
            assert per_order(matches, 1) == {b["order_id"]: q for b, q in bids if q}
            assert len({(o["order_id"], b["order_id"]) for o, b, _ in matches}) == len(matches)

    def test_deterministic_under_input_reordering(self):
        rng = random.Random(3)
        offers, bids = random_sides(rng, 6, 5)
        expected = [(o["order_id"], b["order_id"], q) for o, b, q in sequential_fill(offers, bids)]
        for _ in range(20):
            rng.shuffle(offers)
            rng.shuffle(bids)
            got = [(o["order_id"], b["order_id"], q) for o, b, q in sequential_fill(offers, bids)]
            assert got == expected

    def test_zero_quantities_are_ignored(self):
        offers = [(order("s1", "o1"), 0), (order("s2", "o2"), 3)]
        bids = [(order("b1", "d1"), 3), (order("b2", "d2"), 0)]

        matches = sequential_fill(offers, bids)

        assert [(o["order_id"], b["order_id"], q) for o, b, q in matches] == [("o2", "d1", 3)]

    def test_empty_sides_give_no_matches(self):
        assert sequential_fill([], []) == []
        assert sequential_fill([(order("s1", "o1"), 0)], []) == []

    def test_unequal_sides_raise(self):
        with pytest.raises(ValueError, match="sides differ"):
            sequential_fill([(order("s1", "o1"), 3)], [(order("b1", "d1"), 2)])

    def test_non_integer_quantities_raise(self):
        with pytest.raises(ValueError, match="integers"):
            sequential_fill([(order("s1", "o1"), 2.5)], [(order("b1", "d1"), 2.5)])

    def test_self_match_avoided_on_the_bid_side(self):
        # p sorts first on both sides; its bid is moved behind b1's.
        offers = [(order("p", "o1"), 4), (order("s", "o2"), 4)]
        bids = [(order("p", "d1"), 4), (order("q", "d2"), 4)]

        matches = sequential_fill(offers, bids)

        assert [(o["created_by"], b["created_by"], q) for o, b, q in matches] == [
            ("p", "q", 4),
            ("s", "p", 4),
        ]

    def test_self_match_when_only_own_bids_remain(self):
        # p's bid is the last one left when p's offer comes up: the fill emits
        # the self-match, although a pairing without one exists.
        offers = [(order("a", "o1"), 1), (order("p", "o2"), 1), (order("s", "o3"), 2)]
        bids = [(order("b", "d1"), 1), (order("p", "d2"), 3)]

        matches = sequential_fill(offers, bids)

        assert ("p", "p", 1) in [(o["created_by"], b["created_by"], q) for o, b, q in matches]
        assert per_order(matches, 1) == {"d1": 1, "d2": 3}

    def test_unavoidable_self_match_is_emitted(self):
        # p is the only seller and also buys: 2 kWh of its own offer must meet its bid.
        offers = [(order("p", "o1"), 5)]
        bids = [(order("p", "d1"), 2), (order("q", "d2"), 3)]

        matches = sequential_fill(offers, bids)

        assert [(o["created_by"], b["created_by"], q) for o, b, q in matches] == [
            ("p", "q", 3),
            ("p", "p", 2),
        ]

    def test_self_matches_only_when_no_other_bid_remains_on_random_inputs(self):
        rng = random.Random(4)
        for _ in range(300):
            n, m = rng.randint(1, 6), rng.randint(1, 6)
            offers, bids = random_sides(rng, n, m, shared_actors=True)

            matches = sequential_fill(offers, bids)

            assert len(matches) <= n + m - 1
            assert per_order(matches, 0) == {o["order_id"]: q for o, q in offers if q}
            assert per_order(matches, 1) == {b["order_id"]: q for b, q in bids if q}
            for k, (offer, bid, _) in enumerate(matches):
                if offer["created_by"] == bid["created_by"]:
                    # Only that actor's bids are left from here on.
                    actor = offer["created_by"]
                    assert all(b["created_by"] == actor for _, b, _ in matches[k:])
