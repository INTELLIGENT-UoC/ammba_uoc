"""EWDS / CGW client for the GSY DEX off-chain storage.

Implements the request/response-over-message-bus pattern from the GSY "EWDS
Request Handler" guide (mirroring their Rust ``EwdsClient``): publish a request
envelope to the request topic via ``POST {gateway}/api/v2/messages``, then poll
the paired response topic via ``GET`` until a message with the matching
``requestId`` arrives or the timeout elapses.

Two-layer message format: the transport DTO (camelCase, ``payload`` is a JSON
*string*) wraps the stringified inner envelope
``{requestId, operation, payload}``. Responses come back the same way —
``{requestId, success, data, error}`` stringified inside ``message.payload``.

Exposes the same interface as ``OffchainDBClient`` so ``run_clearing`` is
transport-agnostic. Reads (orders/trades) go over EWDS; writes are a no-op with
a warning — per GSY, matching engines emit matches settled on-chain (v2), so
there is no EWDS write path for trades or clearing results.

Order DTOs are normalized to canonical int:Order shape via
``adapters.ewds_order_to_int_order`` before being returned, because the
upstream DTOs are still being aligned with the ontology (three dialects
coexist — see INTEGRATION_NOTES.md).
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field

import httpx

from src.adapters import ewds_market_to_internal, ewds_order_to_int_order

logger = logging.getLogger(__name__)

DEFAULT_GATEWAY_URL = "http://ewds-gateway-api:3333"
DEFAULT_REQUEST_FQCN = "gsy.intelligent.requests.pub"
DEFAULT_RESPONSE_FQCN = "gsy.intelligent.responses.sub"
DEFAULT_TOPIC_OWNER = "integration.apps.intelligent.auth.ewc"
DEFAULT_TOPIC_VERSION = "1.0.0"
DEFAULT_CLIENT_ID = "ammclearingnode"
DEFAULT_TIMEOUT_MS = 60_000
DEFAULT_POLL_INTERVAL_MS = 400


class EwdsError(RuntimeError):
    """A gateway call failed or the handler returned an error envelope."""


class EwdsTimeout(EwdsError):
    """No matching response arrived within the configured timeout."""


def client_id_for_suffix(base: str, suffix: str) -> str:
    """Alphanumeric consumer id per (client, topic) — matches the Rust helper."""
    value = "".join(ch for ch in base + suffix if ch.isalnum())
    return value or base


@dataclass
class EwdsConfig:
    """Connection settings for the EWDS gateway (defaults match GSY's)."""

    gateway_url: str = DEFAULT_GATEWAY_URL
    request_fqcn: str = DEFAULT_REQUEST_FQCN
    response_fqcn: str = DEFAULT_RESPONSE_FQCN
    topic_owner: str = DEFAULT_TOPIC_OWNER
    topic_version: str = DEFAULT_TOPIC_VERSION
    client_id: str = DEFAULT_CLIENT_ID
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS
    topics: dict = field(
        default_factory=lambda: {
            "orders.query": ("ordersQuery", "ordersQueryResponse"),
            "trades.query": ("tradesQuery", "tradesQueryResponse"),
            "measurements.query": ("measurementsQuery", "measurementsQueryResponse"),
            # Announced by GSY ("modeled on orders.query"); topic names follow
            # the established convention and are configurable if they differ.
            "markets.query": ("marketsQuery", "marketsQueryResponse"),
        }
    )


class EwdsOffchainClient:
    """Off-chain data access over the EWDS gateway (same surface as the REST client)."""

    def __init__(self, config: EwdsConfig | None = None):
        self.config = config or EwdsConfig()
        base = self.config.gateway_url.rstrip("/")
        self._messages_url = f"{base}/api/v2/messages"
        self._client = httpx.AsyncClient(timeout=30.0)

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(self._messages_url, params={"amount": "1"})
            return resp.status_code < 500
        except httpx.HTTPError:
            return False

    async def get_orders(self, market_id: str, start_time: int, end_time: int) -> list[dict]:
        """Fetch orders for a market slot window, normalized to int:Order.

        The handler filters ``time_slot >= start AND time_slot <= end``
        (inclusive both ends); the AMM's window contract is right-open
        ``[start, end)``, so ``end - 1`` goes on the wire.
        """
        data = await self._query(
            "orders.query",
            {"marketId": market_id, "startTime": start_time, "endTime": end_time - 1},
        )
        orders = []
        for dto in data:
            try:
                orders.append(ewds_order_to_int_order(dto))
            except Exception:
                logger.warning(
                    "Skipping EWDS order DTO that failed normalization: %s",
                    dto.get("orderId", dto.get("order_id", "<no id>")),
                    exc_info=True,
                )
        return orders

    async def get_trades(self, market_id: str) -> list[dict]:
        """Fetch trades for a market (used by the idempotency check).

        trades.query has no server-side market filter, so the market filter is
        applied client-side.
        """
        data = await self._query("trades.query", {"marketId": market_id})
        return [t for t in data if (t.get("marketId") or t.get("market_id")) == market_id]

    async def get_markets(self) -> list[dict]:
        """Fetch all markets, normalized to the internal market dict.

        Used by the self-trigger scheduler to discover market slots whose
        window has closed (MarketSchema: closing_time, matching_algorithm).
        """
        data = await self._query("markets.query", {})
        markets = []
        for dto in data:
            try:
                markets.append(ewds_market_to_internal(dto))
            except Exception:
                logger.warning(
                    "Skipping market DTO that failed normalization: %s",
                    dto.get("marketId", dto.get("market_id", "<no id>")),
                    exc_info=True,
                )
        return markets

    async def post_trades(self, trades: list[dict]) -> None:
        """No EWDS write path — matches are settled on-chain (v2). No-op."""
        logger.warning(
            "EWDS transport has no trade write path (%d trades not persisted); "
            "settlement moves on-chain in v2",
            len(trades),
        )

    async def post_clearing_result(self, result: dict) -> None:
        """No EWDS write path for clearing results yet. No-op."""
        logger.warning(
            "EWDS transport has no clearing-result write path " "(marketId=%s not persisted)",
            result.get("marketId"),
        )

    async def close(self) -> None:
        await self._client.aclose()

    # ── request/response mechanics ───────────────────────────────────

    async def _query(self, operation: str, payload: dict) -> list[dict]:
        request_topic, response_topic = self.config.topics[operation]
        request_id = f"{operation.replace('.', '-')}-" f"{int(time.time() * 1000)}-{os.getpid()}"

        envelope = {
            "requestId": request_id,
            "operation": operation,
            "payload": payload,
        }
        transport_dto = {
            "fqcn": self.config.request_fqcn,
            "topicName": request_topic,
            "topicVersion": self.config.topic_version,
            "topicOwner": self.config.topic_owner,
            "transactionId": request_id,
            "payload": json.dumps(envelope),
            "anonymousRecipient": [],
        }

        resp = await self._client.post(self._messages_url, json=transport_dto)
        if resp.status_code >= 300:
            raise EwdsError(
                f"EWDS publish failed for {operation}: "
                f"HTTP {resp.status_code}: {resp.text[:500]}"
            )

        return await self._poll(operation, request_id, response_topic)

    async def _poll(self, operation: str, request_id: str, response_topic: str) -> list[dict]:
        poll_client_id = client_id_for_suffix(self.config.client_id, response_topic)
        deadline = time.monotonic() + self.config.timeout_ms / 1000.0

        while True:
            if time.monotonic() > deadline:
                raise EwdsTimeout(
                    f"EWDS timeout waiting for {operation} response " f"(request_id={request_id})"
                )

            resp = await self._client.get(
                self._messages_url,
                params={
                    "fqcn": self.config.response_fqcn,
                    "amount": "100",
                    "topicName": response_topic,
                    "topicOwner": self.config.topic_owner,
                    "clientId": poll_client_id,
                },
            )
            if resp.status_code >= 300:
                raise EwdsError(
                    f"EWDS response poll failed for {operation} "
                    f"(request_id={request_id}): "
                    f"HTTP {resp.status_code}: {resp.text[:500]}"
                )

            for message in resp.json():
                try:
                    parsed = json.loads(message["payload"])
                except (KeyError, TypeError, json.JSONDecodeError):
                    continue
                parsed_id = parsed.get("requestId") or parsed.get("request_id")
                if parsed_id != request_id:
                    continue  # another consumer's response; leave it alone
                if not parsed.get("success", False):
                    error = parsed.get("error") or {}
                    raise EwdsError(
                        f"EWDS {operation} returned error "
                        f"(request_id={request_id}): "
                        f"{error.get('code', '?')}: {error.get('message', '?')}"
                    )
                return parsed.get("data") or []

            await asyncio.sleep(self.config.poll_interval_ms / 1000.0)
