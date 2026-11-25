"""Integer apportionment and bilateral decomposition of a cleared slot.

Two pure functions on integer quantities (multiples of the on-chain resolution,
see ``sigmoid.NODE_FLOAT_SCALING_FACTOR``). Neither knows about the price
function or the pool: they only split quantities.

- ``apportion`` splits an integer total in proportion to integer weights
  (largest-remainder method). The clearing pipeline uses it for the pro-rata
  allocation, so both sides of a slot sum to exactly the same integer total.
- ``sequential_fill`` cuts the allocations of the sellers and the buyers into
  bilateral matches. Both sides are lined up along the traded quantity and cut
  at every boundary, which gives at most n + m − 1 matches and keeps every
  order's allocated quantity.
"""

from collections.abc import Iterable


def apportion(weights: list[int], total: int) -> list[int]:
    """Split ``total`` in proportion to ``weights`` (largest-remainder method).

    Every share is the floor of its exact quota ``weight × total / Σ weights``
    plus at most one unit; the leftover units go to the largest remainders
    (ties to the earlier index). The shares sum to ``total``, and no share
    exceeds its weight while ``total ≤ Σ weights``.
    """
    if total < 0 or any(w < 0 for w in weights):
        raise ValueError("weights and total must be non-negative")
    weight_sum = sum(weights)
    if weight_sum == 0:
        if total:
            raise ValueError("cannot apportion a positive total over zero weights")
        return [0] * len(weights)

    quotas = [divmod(w * total, weight_sum) for w in weights]
    shares = [q for q, _ in quotas]
    leftover = total - sum(shares)
    by_remainder = sorted(range(len(weights)), key=lambda i: (-quotas[i][1], i))
    for i in by_remainder[:leftover]:
        shares[i] += 1
    return shares


def order_key(order: dict) -> tuple[str, str]:
    """Deterministic order of a side: actor id, then order id.

    Sorting by actor first lines the same participants up in the same order
    every slot, so pairings repeat across slots.
    """
    return (str(order.get("created_by", "")), str(order.get("order_id", "")))


def _move_first_other(queue: list[list], start: int, actor: str) -> None:
    """Move the first entry after ``start`` whose actor differs to ``start``.

    The entries in between keep their order; nothing moves if there is none.
    """
    for k in range(start + 1, len(queue)):
        if queue[k][0].get("created_by") != actor:
            queue.insert(start, queue.pop(k))
            return


def sequential_fill(
    offers: Iterable[tuple[dict, int]],
    bids: Iterable[tuple[dict, int]],
) -> list[tuple[dict, dict, int]]:
    """Cut two equal-sized sides into bilateral ``(offer, bid, quantity)`` matches.

    ``offers`` and ``bids`` are ``(order, quantity)`` pairs with integer
    quantities; entries with quantity 0 are ignored. Each side is sorted by
    actor id (``created_by``), then order id, and the two sides are filled
    against each other front to back: every match takes the smaller of the two
    open quantities and exhausts at least one order. The result has at most
    n + m − 1 matches, every order's matched quantity equals its input
    quantity, and the output does not depend on the input order.

    A match would pair an actor with itself when the actor has both an offer
    and a bid in the slot. The fill then moves the next bid of another actor
    forward. If every remaining bid belongs to that actor, the self-match is
    emitted; the settlement validator flags it.

    Raises ``ValueError`` if the two sides do not sum to the same total.
    """
    offer_queue = [[o, q] for o, q in sorted(offers, key=lambda e: order_key(e[0])) if q]
    bid_queue = [[b, q] for b, q in sorted(bids, key=lambda e: order_key(e[0])) if q]
    for _, quantity in offer_queue + bid_queue:
        if not isinstance(quantity, int) or quantity < 0:
            raise ValueError(f"quantities must be non-negative integers, got {quantity!r}")
    offer_total = sum(q for _, q in offer_queue)
    bid_total = sum(q for _, q in bid_queue)
    if offer_total != bid_total:
        raise ValueError(f"sides differ: offers sum to {offer_total}, bids to {bid_total}")

    matches: list[tuple[dict, dict, int]] = []
    i = j = 0
    while i < len(offer_queue) and j < len(bid_queue):
        actor = offer_queue[i][0].get("created_by")
        if actor is not None and bid_queue[j][0].get("created_by") == actor:
            _move_first_other(bid_queue, j, actor)
        offer_entry, bid_entry = offer_queue[i], bid_queue[j]
        quantity = min(offer_entry[1], bid_entry[1])
        matches.append((offer_entry[0], bid_entry[0], quantity))
        offer_entry[1] -= quantity
        bid_entry[1] -= quantity
        if offer_entry[1] == 0:
            i += 1
        if bid_entry[1] == 0:
            j += 1
    return matches
