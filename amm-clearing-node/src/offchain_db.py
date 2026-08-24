"""HTTP client for the GSY DEX off-chain DB API."""

import logging

import httpx

from src.adapters import ewds_market_to_internal
from src.retry import request_with_retries

logger = logging.getLogger(__name__)


class OffchainDBClient:
    """Async HTTP client wrapping the off-chain DB REST API."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get("/health_check")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def get_orders(self, market_id: str, start_time: int, end_time: int) -> list[dict]:
        """Fetch orders for a market slot.

        GET /orders?market_id={id}&start_time={ts}&end_time={ts}
        """
        resp = await request_with_retries(
            self._client,
            "GET",
            "/orders",
            params={
                "market_id": market_id,
                "start_time": start_time,
                "end_time": end_time,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def get_trades(self, market_id: str) -> list[dict]:
        """Fetch trades for a market.

        GET /trades?market_id={id}
        """
        resp = await request_with_retries(
            self._client, "GET", "/trades", params={"market_id": market_id}
        )
        resp.raise_for_status()
        return resp.json()

    async def get_markets(self) -> list[dict]:
        """Fetch all markets (internal dict shape), for the scheduler.

        GET /markets — served by the local simulator; the real GSY path is
        markets.query over EWDS.
        """
        resp = await request_with_retries(self._client, "GET", "/markets")
        resp.raise_for_status()
        return [ewds_market_to_internal(m) for m in resp.json()]

    async def post_trades(self, trades: list[dict]) -> None:
        """Write int:Trade objects to the off-chain DB.

        POST /trades-normalized
        """
        resp = await request_with_retries(self._client, "POST", "/trades-normalized", json=trades)
        resp.raise_for_status()
        logger.info("Posted %d trades to off-chain DB", len(trades))

    async def post_clearing_result(self, result: dict) -> None:
        """Write the int:ClearingResult for a market slot to the off-chain DB.

        POST /clearing-results
        """
        resp = await request_with_retries(self._client, "POST", "/clearing-results", json=result)
        resp.raise_for_status()
        logger.info("Posted clearing result for market_id=%s", result.get("marketId"))

    async def close(self) -> None:
        await self._client.aclose()
