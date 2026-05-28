"""HTTP client for the GSY DEX off-chain DB API (Execution Node)."""

import logging

import httpx

logger = logging.getLogger(__name__)


class OffchainDBClient:
    """Async HTTP client for the off-chain DB, tailored for execution node needs."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get("/health_check")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def get_trades(self, market_id: str) -> list[dict]:
        """Fetch settled trades for a market."""
        resp = await self._client.get(
            "/trades", params={"market_id": market_id}
        )
        resp.raise_for_status()
        return resp.json()

    async def get_community_markets(self, community_uuid: str) -> list[dict]:
        """Fetch markets for a community."""
        resp = await self._client.get(
            "/community-market", params={"community_uuid": community_uuid}
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else [data]

    async def get_asset_measurements(
        self, community_uuid: str, area_uuid: str
    ) -> list[dict]:
        """Fetch post-delivery measurements for an area."""
        resp = await self._client.get(
            "/asset_measurements",
            params={
                "community_uuid": community_uuid,
                "area_uuid": area_uuid,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def post_trades(self, trades: list[dict]) -> None:
        """Write updated trade objects (with penalties) back to the off-chain DB."""
        resp = await self._client.post("/trades-normalized", json=trades)
        resp.raise_for_status()
        logger.info("Posted %d updated trades to off-chain DB", len(trades))

    async def close(self) -> None:
        await self._client.aclose()
