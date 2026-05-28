"""FastAPI application — AMM Execution Node.

Runs as a polling loop checking for completed delivery slots,
or can be triggered via HTTP endpoint.

Endpoints:
  POST /trigger-execution  — manually trigger execution for a specific slot
  GET  /health             — health check
"""

import asyncio
import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.config import Settings, load_settings
from src.execution import compute_previous_timeslot, run_execution_cycle
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


class ExecutionResponse(BaseModel):
    status: str
    detail: dict | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = load_settings()

    app = FastAPI(title="AMM Execution Node", version="0.1.0")
    app.state.settings = settings
    app.state.db_client = OffchainDBClient(settings.offchain_db_url)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/trigger-execution", status_code=202)
    async def trigger_execution(req: TriggerRequest) -> ExecutionResponse:
        """Manually trigger execution for a specific market slot."""
        community_config = settings.communities.get(req.community_uuid)
        if community_config is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown community_uuid: {req.community_uuid}",
            )

        try:
            result = await run_execution_cycle(
                community_uuid=req.community_uuid,
                market_id=req.market_id,
                time_slot=req.time_slot,
                community_config=community_config,
                penalty_config=settings.penalties,
                db_client=app.state.db_client,
            )
        except Exception:
            logger.exception("Execution failed for market_id=%s", req.market_id)
            raise HTTPException(status_code=500, detail="Execution failed")

        return ExecutionResponse(status=result["status"], detail=result)

    return app


async def polling_loop(settings: Settings) -> None:
    """Continuously poll for completed delivery slots and run execution.

    Same pattern as the GSY DEX execution engine.
    """
    db_client = OffchainDBClient(settings.offchain_db_url)

    while True:
        try:
            previous_slot = compute_previous_timeslot(
                settings.time_slot_sec, settings.execution_offset_min
            )

            for community_uuid, community_config in settings.communities.items():
                # Fetch markets for this community to find the market_id
                try:
                    markets = await db_client.get_community_markets(community_uuid)
                    for market in markets:
                        if market.get("time_slot") == previous_slot:
                            await run_execution_cycle(
                                community_uuid=community_uuid,
                                market_id=market["market_id"],
                                time_slot=previous_slot,
                                community_config=community_config,
                                penalty_config=settings.penalties,
                                db_client=db_client,
                            )
                except Exception:
                    logger.exception(
                        "Execution cycle failed for community=%s slot=%d",
                        community_uuid,
                        previous_slot,
                    )

        except Exception:
            logger.exception("Polling loop error")

        await asyncio.sleep(settings.polling_interval_sec)


# Default app instance for uvicorn
app = create_app()


if __name__ == "__main__":
    import sys
    import uvicorn

    settings = load_settings()

    if "--poll" in sys.argv:
        # Run as polling loop
        asyncio.run(polling_loop(settings))
    else:
        # Run as HTTP server
        uvicorn.run(
            "src.main:app",
            host=settings.host,
            port=settings.port,
            reload=True,
        )
