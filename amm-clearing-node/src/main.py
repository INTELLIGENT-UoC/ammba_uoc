"""FastAPI application — AMM Clearing Node.

Endpoints:
  POST /trigger-clearing  — triggered by Market Orchestrator when a market slot closes
  GET  /health            — health check
"""

import asyncio
import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.clearing import run_clearing
from src.config import Settings, load_settings
from src.contract import AMMContractClient
from src.ewds_client import EwdsConfig, EwdsOffchainClient
from src.offchain_db import OffchainDBClient
from src.scheduler import run_scheduler_loop

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

    # Shared clients stored on app state. Transport-selectable: direct REST to
    # the off-chain DB (default / local simulator) or publish/poll via the EW
    # CGW gateway (the GSY-confirmed integration path).
    app.state.settings = settings
    if settings.offchain_transport == "ewds":
        app.state.db_client = EwdsOffchainClient(
            EwdsConfig(
                gateway_url=settings.ewds_gateway_url,
                request_fqcn=settings.ewds_request_fqcn,
                response_fqcn=settings.ewds_response_fqcn,
                topic_owner=settings.ewds_topic_owner,
                topic_version=settings.ewds_topic_version,
                client_id=settings.ewds_client_id,
                timeout_ms=settings.ewds_response_timeout_ms,
                poll_interval_ms=settings.ewds_poll_interval_ms,
            )
        )
        logger.info(
            "Off-chain transport: EWDS gateway at %s (clientId base %s)",
            settings.ewds_gateway_url,
            settings.ewds_client_id,
        )
    else:
        app.state.db_client = OffchainDBClient(settings.offchain_db_url)
        logger.info("Off-chain transport: REST at %s", settings.offchain_db_url)

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

    # Self-trigger scheduler (opt-in): discovers closed AMM markets and clears
    # them without an external trigger. /trigger-clearing keeps working too.
    app.state.scheduler_task = None
    if settings.scheduler_enabled:

        @app.on_event("startup")
        async def start_scheduler():
            app.state.scheduler_task = asyncio.create_task(
                run_scheduler_loop(settings, app.state.db_client, app.state.contract_client)
            )
            logger.info("Self-trigger scheduler enabled")

        @app.on_event("shutdown")
        async def stop_scheduler():
            task = app.state.scheduler_task
            if task is not None:
                task.cancel()

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
                strict_validation=settings.strict_order_validation,
            )
        except Exception as exc:
            logger.exception("Clearing failed for market_id=%s", req.market_id)
            raise HTTPException(status_code=500, detail="Clearing failed") from exc

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
