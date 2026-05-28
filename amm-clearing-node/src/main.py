"""FastAPI application — AMM Clearing Node.

Endpoints:
  POST /trigger-clearing  — triggered by Market Orchestrator when a market slot closes
  GET  /health            — health check
"""

import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.clearing import run_clearing
from src.config import Settings, load_settings
from src.contract import AMMContractClient
from src.offchain_db import OffchainDBClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


class TriggerRequest(BaseModel):
    market_id: str
    community_uuid: str
    time_slot: int


class ClearingResponse(BaseModel):
    status: str
    detail: dict | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if settings is None:
        settings = load_settings()

    app = FastAPI(title="AMM Clearing Node", version="0.1.0")

    # Shared clients stored on app state
    app.state.settings = settings
    app.state.db_client = OffchainDBClient(settings.offchain_db_url)

    # Contract client (optional — may not have credentials in dev)
    app.state.contract_client = None
    if settings.clearing_node_private_key and settings.contract_address:
        try:
            app.state.contract_client = AMMContractClient(
                rpc_url=settings.rpc_url,
                contract_address=settings.contract_address,
                private_key=settings.clearing_node_private_key,
            )
            logger.info("Contract client initialized for %s", settings.contract_address)
        except Exception:
            logger.warning("Failed to initialize contract client", exc_info=True)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/trigger-clearing", status_code=202)
    async def trigger_clearing(req: TriggerRequest) -> ClearingResponse:
        """Trigger market clearing for a specific market slot.

        Called by the Market Orchestrator when a market window closes.
        """
        settings: Settings = app.state.settings

        # Validate community exists in config
        community_config = settings.communities.get(req.community_uuid)
        if community_config is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown community_uuid: {req.community_uuid}",
            )

        try:
            result = await run_clearing(
                market_id=req.market_id,
                community_uuid=req.community_uuid,
                time_slot=req.time_slot,
                community_config=community_config,
                db_client=app.state.db_client,
                contract_client=app.state.contract_client,
                time_slot_sec=settings.time_slot_sec,
            )
        except Exception:
            logger.exception("Clearing failed for market_id=%s", req.market_id)
            raise HTTPException(status_code=500, detail="Clearing failed")

        return ClearingResponse(status=result["status"], detail=result)

    return app


# Default app instance for uvicorn
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = load_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
