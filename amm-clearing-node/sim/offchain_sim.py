"""Local off-chain DB / CGW simulator for end-to-end testing.

A dev-only stand-in for the GSY DEX off-chain storage. It speaks the same REST
surface the clearing node uses today and, crucially, serves and accepts only
``int.*`` ontology objects, validating every payload against the vendored
schemas. This lets the clearing node run end-to-end against correct data
formats without the real GSY environment, and makes format drift fail loudly.

It is deliberately schema-driven (seeded from int:Order fixtures and validating
int:Trade / int:ClearingResult on write) rather than echoing whatever the AMM
happens to send — otherwise the harness would just re-encode the AMM's own
assumptions instead of the agreed contract.

Run:
    uv run uvicorn sim.offchain_sim:app --port 8080

The transport here is plain REST. When GSY's EW CGW request/response channels
are finalised, the same int.* payloads move to a publish/poll client behind the
adapter; this simulator and its fixtures stay the validation reference.
"""

import json
import logging
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from src.adapters import iso_to_unix
from src.ontology import (
    SchemaValidationError,
    validate_clearing_result,
    validate_order,
    validate_trade,
)

logger = logging.getLogger(__name__)

SEED_PATH = Path(__file__).parent / "seed_orders.json"


class Store:
    def __init__(self) -> None:
        self.orders: list[dict] = []
        self.trades: list[dict] = []
        self.clearing_results: list[dict] = []

    def seed_from_file(self, path: Path = SEED_PATH) -> None:
        if not path.exists():
            return
        with open(path) as f:
            orders = json.load(f)
        for order in orders:
            validate_order(order)
        self.orders = orders
        logger.info("Seeded %d orders from %s", len(orders), path)


def create_app(store: Store | None = None) -> FastAPI:
    store = store or Store()
    store.seed_from_file()

    app = FastAPI(title="AMMBA off-chain DB simulator", version="0.1.0")
    app.state.store = store

    @app.get("/health_check")
    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/orders")
    async def get_orders(
        market_id: str, start_time: int | None = None, end_time: int | None = None
    ):
        results = []
        for order in store.orders:
            if order.get("marketId") != market_id:
                continue
            if start_time is not None and end_time is not None:
                ts = iso_to_unix(order["timeSlot"])
                if not (start_time <= ts < end_time):
                    continue
            results.append(order)
        return results

    @app.get("/trades")
    async def get_trades(market_id: str):
        return [t for t in store.trades if t.get("marketId") == market_id]

    @app.post("/trades-normalized")
    async def post_trades(trades: list[dict] = Body(...)):
        for trade in trades:
            try:
                validate_trade(trade)
            except SchemaValidationError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        store.trades.extend(trades)
        return {"accepted": len(trades)}

    @app.post("/clearing-results")
    async def post_clearing_result(result: dict = Body(...)):
        try:
            validate_clearing_result(result)
        except SchemaValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        store.clearing_results.append(result)
        return {"accepted": 1}

    @app.get("/clearing-results")
    async def list_clearing_results(market_id: str):
        return [r for r in store.clearing_results if r.get("marketId") == market_id]

    @app.post("/_reset")
    async def reset():
        store.trades.clear()
        store.clearing_results.clear()
        store.seed_from_file()
        return {"status": "reset"}

    return app


app = create_app()
