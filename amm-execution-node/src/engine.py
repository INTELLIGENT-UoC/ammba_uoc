"""Settlement engine orchestration: validate → map actors → place pool orders → settleBatch.

Idempotent by trade id: a ledger records settled trades so a crash or re-run
cannot double-settle (the contract would also reject re-settling because the
orders flip to Executed, but we avoid burning gas to find out).

⚠ Known open constraint (raised with GSY): ``OrderRegistry.placeOrder``
requires the market to be OPEN and the pool actor to be authorized for our
signer in ActorRegistry. AMM matches are only known after the market closes —
so pool standing orders cannot be placed post-clearing under current contract
rules. Resolution options are with GSY (relax the market-open check for a
settlement role, or a pool-aware path). The engine keeps placement as an
explicit separate phase so either resolution slots in.
"""

import logging
from dataclasses import dataclass, field
from typing import Protocol

from src.match_builder import BuildResult
from src.validator import Violation, validate_batch

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 50


class ChainClient(Protocol):
    async def place_order(self, params_tuple: tuple) -> str: ...

    async def settle_batch(self, match_tuples: list[tuple]) -> str: ...


class IdRegistrar(Protocol):
    """Registers actor off-chain→on-chain id mappings with the GSY storage.

    The on-chain actor id is a deterministic hash we compute locally
    (ids.actor_onchain_id), but the storage must hold the mapping so it can
    attribute on-chain settlement events back to off-chain actors — the pool
    actor in particular is known to nobody else. Wire to the storage's
    ``ids.query`` (EWDS) or ``POST /ids`` (REST); idempotent upstream.
    """

    async def ensure_mapped(self, offchain_ids: list[str]) -> None: ...


class SettlementLedger:
    """Tracks settled trade ids. In-memory for the skeleton; swap for a
    persistent store before production so restarts keep idempotency."""

    def __init__(self) -> None:
        self._settled: dict[str, str] = {}  # trade_id -> tx hash
        self._placed_orders: set[str] = set()

    def is_settled(self, trade_id: str) -> bool:
        return trade_id in self._settled

    def mark_settled(self, trade_ids: list[str], tx_hash: str) -> None:
        for trade_id in trade_ids:
            self._settled[trade_id] = tx_hash

    def is_placed(self, order_id: str) -> bool:
        return order_id in self._placed_orders

    def mark_placed(self, order_id: str) -> None:
        self._placed_orders.add(order_id)


@dataclass
class SettlementReport:
    settled: dict[str, str] = field(default_factory=dict)  # trade_id -> tx
    skipped_already_settled: list[str] = field(default_factory=list)
    rejected: dict[str, list[Violation]] = field(default_factory=dict)
    pool_orders_placed: list[str] = field(default_factory=list)


class SettlementEngine:
    def __init__(
        self,
        chain: ChainClient,
        ledger: SettlementLedger | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        registrar: IdRegistrar | None = None,
    ):
        self.chain = chain
        self.ledger = ledger or SettlementLedger()
        self.batch_size = batch_size
        self.registrar = registrar

    async def settle(self, build: BuildResult) -> SettlementReport:
        report = SettlementReport()

        # 1. Pre-flight validation — drop invalid matches, keep the batch alive.
        report.rejected = validate_batch(build.matches)
        candidates = [m for m in build.matches if m.trade_id not in report.rejected]
        for trade_id, violations in report.rejected.items():
            logger.warning(
                "Match %s rejected pre-flight: %s",
                trade_id,
                "; ".join(f"{v.code} {v.detail}" for v in violations),
            )

        # 2. Idempotency — skip anything already settled.
        fresh = []
        for match in candidates:
            if self.ledger.is_settled(match.trade_id):
                report.skipped_already_settled.append(match.trade_id)
            else:
                fresh.append(match)
        if not fresh:
            return report

        # 3. Register actor id mappings so on-chain events stay attributable.
        actors = sorted({a for m in fresh for a in (m.bid.created_by, m.offer.created_by)})
        if self.registrar is None:
            logger.warning(
                "No id registrar configured: %d actor mapping(s) not registered with "
                "the storage; settlement events may not be attributable off-chain",
                len(actors),
            )
        else:
            await self.registrar.ensure_mapped(actors)

        # 4. Place the pool standing orders backing the fresh matches.
        fresh_ids = {m.trade_id for m in fresh}
        needed_pool_orders = [
            p
            for p in build.pool_orders
            if not self.ledger.is_placed(p.order.order_id)
            and any(p.order.order_id in (m.bid.order_id, m.offer.order_id) for m in fresh)
        ]
        for params in needed_pool_orders:
            await self.chain.place_order(params.to_tuple())
            self.ledger.mark_placed(params.order.order_id)
            report.pool_orders_placed.append(params.order.order_id)

        # 5. Settle in bounded batches.
        for start in range(0, len(fresh), self.batch_size):
            chunk = fresh[start : start + self.batch_size]
            tx_hash = await self.chain.settle_batch([m.to_tuple() for m in chunk])
            chunk_ids = [m.trade_id for m in chunk]
            self.ledger.mark_settled(chunk_ids, tx_hash)
            for trade_id in chunk_ids:
                report.settled[trade_id] = tx_hash
            logger.info("Settled %d matches in %s", len(chunk), tx_hash)

        del fresh_ids
        return report
