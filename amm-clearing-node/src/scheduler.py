"""Periodic self-trigger: discover closed AMM markets and clear them.

GSY confirmed there is no market-close event — the AMM must self-trigger. The
scheduler polls the market list (markets.query over EWDS, or GET /markets on
the REST/simulator transport), selects markets whose order window has closed,
whose matching_algorithm is "amm", and whose community this node is configured
for, and runs the clearing pipeline for each. The DB-level idempotency check in
run_clearing() remains the authoritative re-clear guard; the in-memory
processed set only avoids re-querying markets already handled this process
lifetime.

Disabled by default (SCHEDULER_ENABLED=false): manual POST /trigger-clearing
stays the primary path for tests and pilots until markets.query is live
upstream.
"""

import asyncio
import logging
import time

from src.clearing import run_clearing
from src.config import Settings

logger = logging.getLogger(__name__)

AMM_ALGORITHM = "amm"
# Bound the processed-set so a long-lived node cannot grow it unbounded.
MAX_PROCESSED = 10_000


def select_due_markets(
    markets: list[dict],
    known_communities: set[str],
    now: int,
    processed: set[str],
) -> list[dict]:
    """Markets that are ready to clear right now.

    Due = order window closed (closing_time <= now), AMM-matched, belonging to
    a configured community, and not already handled this process lifetime.
    """
    due = []
    for market in markets:
        market_id = market.get("market_id")
        closing = market.get("closing_time")
        if not market_id or closing is None or market_id in processed:
            continue
        if market.get("matching_algorithm") != AMM_ALGORITHM:
            continue
        if market.get("community_id") not in known_communities:
            continue
        if closing > now:
            continue
        due.append(market)
    return due


async def run_scheduler_tick(
    settings: Settings,
    db_client,
    contract_client,
    processed: set[str],
    now: int | None = None,
) -> list[dict]:
    """One discovery-and-clear pass. Returns the clearing summaries."""
    now = int(time.time()) if now is None else now
    markets = await db_client.get_markets()
    due = select_due_markets(markets, set(settings.communities), now, processed)
    if due:
        logger.info("Scheduler: %d market(s) due for clearing", len(due))

    results = []
    for market in due:
        community_id = market["community_id"]
        try:
            result = await run_clearing(
                market_id=market["market_id"],
                community_uuid=community_id,
                time_slot=market["delivery_start_time"],
                community_config=settings.communities[community_id],
                db_client=db_client,
                contract_client=contract_client,
                time_slot_sec=settings.time_slot_sec,
                strict_validation=settings.strict_order_validation,
            )
        except Exception:
            logger.exception("Scheduled clearing failed for market_id=%s", market["market_id"])
            continue  # not marked processed — retried next tick
        if len(processed) < MAX_PROCESSED:
            processed.add(market["market_id"])
        results.append({"market_id": market["market_id"], **result})
    return results


TICK_BACKOFF_FACTOR = 2.0
TICK_BACKOFF_MAX_MULTIPLE = 10  # never sleep longer than 10× the configured interval


def next_tick_interval_sec(current_sec: float, base_sec: float, tick_failed: bool) -> float:
    """Sleep before the next scheduler tick.

    A failed tick (typically the storage behind the gateway not answering)
    doubles the interval up to ``TICK_BACKOFF_MAX_MULTIPLE × base``; a
    successful tick snaps back to ``base``. Keeps a dead upstream from being
    hammered at full rate through a shared gateway.
    """
    if not tick_failed:
        return base_sec
    return min(current_sec * TICK_BACKOFF_FACTOR, base_sec * TICK_BACKOFF_MAX_MULTIPLE)


async def run_scheduler_loop(settings: Settings, db_client, contract_client) -> None:
    """Poll forever; each tick discovers and clears due markets."""
    processed: set[str] = set()
    base = float(settings.scheduler_poll_interval_sec)
    interval = base
    logger.info(
        "Self-trigger scheduler started (interval %ds)", settings.scheduler_poll_interval_sec
    )
    while True:
        failed = False
        try:
            await run_scheduler_tick(settings, db_client, contract_client, processed)
        except asyncio.CancelledError:
            raise
        except Exception:
            failed = True
            logger.exception("Scheduler tick failed; backing off")
        interval = next_tick_interval_sec(interval, base, failed)
        if failed:
            logger.warning("Next scheduler tick in %.0fs", interval)
        await asyncio.sleep(interval)
