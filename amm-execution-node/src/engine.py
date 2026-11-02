"""Settlement engine orchestration: validate → map actors → place pool orders → settleBatch.

``settleBatch`` takes one ``MarketSettlement`` per market and reverts the whole
transaction on any invalid match, so the market is the unit of everything
here: validation holds back a whole market, idempotency is per market, and a
transaction packs whole markets (never splits one). A ledger records settled
markets so a crash or re-run cannot double-settle (the contract would also
reject re-settling because the orders flip to Executed, but we avoid burning
gas to find out).

⚠ Known open constraint (raised with GSY): ``OrderRegistry.placeOrder``
requires the market to be open (``openingTime ≤ now < closingTime``) and the
pool actor to be authorized for our signer in ActorRegistry. AMM matches are
only known after the market closes, so pool standing orders cannot be placed
post-clearing under current contract rules. Resolution options are with GSY
(a settlement-role exemption from the open check, or bilateral matches without
pool orders). The engine keeps placement as an explicit separate phase so
either resolution slots in.
"""

import logging
from dataclasses import dataclass, field
from typing import Protocol

from src.match_builder import BuildResult
from src.structs import MarketSettlement
from src.validator import Violation, validate_batch

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 50  # matches per transaction; a larger market goes alone


class ChainClient(Protocol):
    async def place_order(self, params_tuple: tuple) -> str: ...

    async def settle_batch(self, settlement_tuples: list[tuple]) -> str: ...


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
    """Tracks settled markets. In-memory for the skeleton; swap for a
    persistent store before production so restarts keep idempotency."""

    def __init__(self) -> None:
        self._settled: dict[str, str] = {}  # market_id -> tx hash
        self._placed_orders: set[str] = set()

    def is_settled(self, market_id: str) -> bool:
        return market_id in self._settled

    def mark_settled(self, market_ids: list[str], tx_hash: str) -> None:
        for market_id in market_ids:
            self._settled[market_id] = tx_hash

    def is_placed(self, order_id: str) -> bool:
        return order_id in self._placed_orders

    def mark_placed(self, order_id: str) -> None:
        self._placed_orders.add(order_id)


@dataclass
class SettlementReport:
    settled: dict[str, str] = field(default_factory=dict)  # market_id -> tx
    skipped_already_settled: list[str] = field(default_factory=list)  # market ids
    rejected: dict[str, list[Violation]] = field(default_factory=dict)  # market_id -> why
    pool_orders_placed: list[str] = field(default_factory=list)


def _pack(settlements: list[MarketSettlement], max_matches: int) -> list[list[MarketSettlement]]:
    """Group whole markets into transactions of at most ``max_matches`` matches."""
    chunks: list[list[MarketSettlement]] = []
    current: list[MarketSettlement] = []
    size = 0
    for settlement in settlements:
        n = len(settlement.matches)
        if current and size + n > max_matches:
            chunks.append(current)
            current, size = [], 0
        current.append(settlement)
        size += n
    if current:
        chunks.append(current)
    return chunks


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

        # 1. Pre-flight validation — hold back any market with a violation.
        report.rejected = validate_batch(build.settlements)
        candidates = [s for s in build.settlements if s.market_id not in report.rejected]
        for market_id, violations in report.rejected.items():
            logger.warning(
                "Market %s held back pre-flight: %s",
                market_id,
                "; ".join(f"{v.subject} {v.code} {v.detail}" for v in violations),
            )

        # 2. Idempotency — skip markets already settled.
        fresh = []
        for settlement in candidates:
            if self.ledger.is_settled(settlement.market_id):
                report.skipped_already_settled.append(settlement.market_id)
            else:
                fresh.append(settlement)
        if not fresh:
            return report
        fresh_matches = [m for s in fresh for m in s.matches]

        # 3. Register actor id mappings so on-chain events stay attributable.
        actors = sorted(
            {
                actor
                for m in fresh_matches
                for order in (m.bid, m.offer)
                for actor in (order.created_by, order.preferred_trading_partner)
                if actor
            }
        )
        if self.registrar is None:
            logger.warning(
                "No id registrar configured: %d actor mapping(s) not registered with "
                "the storage; settlement events may not be attributable off-chain",
                len(actors),
            )
        else:
            await self.registrar.ensure_mapped(actors)

        # 4. Place the pool standing orders backing the fresh matches.
        used_orders = {o.order_id for m in fresh_matches for o in (m.bid, m.offer)}
        for params in build.pool_orders:
            if params.order_id in used_orders and not self.ledger.is_placed(params.order_id):
                await self.chain.place_order(params.to_tuple())
                self.ledger.mark_placed(params.order_id)
                report.pool_orders_placed.append(params.order_id)

        # 5. Settle whole markets in bounded transactions.
        for chunk in _pack(fresh, self.batch_size):
            tx_hash = await self.chain.settle_batch([s.to_tuple() for s in chunk])
            market_ids = [s.market_id for s in chunk]
            self.ledger.mark_settled(market_ids, tx_hash)
            for market_id in market_ids:
                report.settled[market_id] = tx_hash
            logger.info(
                "Settled %d market(s), %d matches in %s",
                len(chunk),
                sum(len(s.matches) for s in chunk),
                tx_hash,
            )

        return report
