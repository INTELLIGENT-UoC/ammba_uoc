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
SEED_MARKETS_PATH = Path(__file__).parent / "seed_markets.json"


class Store:
    def __init__(self) -> None:
        self.orders: list[dict] = []
        self.markets: list[dict] = []
        self.trades: list[dict] = []
        self.clearing_results: list[dict] = []
        # EWDS gateway emulation: per-topic message queues and per-(topic,
        # clientId) consumer offsets, mimicking the CGW's consumer groups.
        self.topics: dict[str, list[dict]] = {}
        self.offsets: dict[tuple[str, str], int] = {}

    def publish(self, topic: str, payload: str) -> None:
        self.topics.setdefault(topic, []).append({"payload": payload})

    def consume(self, topic: str, client_id: str, amount: int) -> list[dict]:
        queue = self.topics.get(topic, [])
        cursor = self.offsets.get((topic, client_id), 0)
        batch = queue[cursor : cursor + amount]
        self.offsets[(topic, client_id)] = cursor + len(batch)
        return batch

    def seed_from_file(self, path: Path = SEED_PATH) -> None:
        if not path.exists():
            return
        with open(path) as f:
            orders = json.load(f)
        for order in orders:
            validate_order(order)
        self.orders = orders
        logger.info("Seeded %d orders from %s", len(orders), path)
        if SEED_MARKETS_PATH.exists():
            with open(SEED_MARKETS_PATH) as f:
                self.markets = json.load(f)
            logger.info("Seeded %d markets", len(self.markets))


def _int_order_to_current_dto(order: dict) -> dict:
    """Render an int:Order seed in the CURRENT EWDS handler DTO dialect.

    The live GSY handler still emits the pre-ontology shape (lowercase
    ``status: "open"``, lowercase order type, unix timestamps, nested
    requirements/attributes). The simulator serves that shape on the gateway
    path on purpose, so the clearing node's tolerant normalizer is exercised
    against exactly what staging returns today.
    """
    dto = {
        "orderId": order["orderId"],
        "marketId": order["marketId"],
        "orderType": order["orderType"].lower(),
        "status": "open" if order["orderStatus"] == "Submitted" else order["orderStatus"].lower(),
        "areaUuid": order["createdBy"],
        "nonce": 1,
        "timeSlot": iso_to_unix(order["timeSlot"]),
        "creationTime": iso_to_unix(order["createdAt"]),
        "quantity": order["quantity"],
        "priceLimit": order["priceLimit"],
        "createdBy": order["createdBy"],
    }
    requirements = {}
    if order.get("preferredTradingPartner"):
        requirements["tradingPartnerId"] = order["preferredTradingPartner"]
    if order.get("energySourcePreference"):
        requirements["energyType"] = order["energySourcePreference"]
    if requirements:
        dto["requirements"] = requirements
    if order.get("energyType"):
        dto["attributes"] = {"energyType": order["energyType"]}
    return dto


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

    @app.get("/markets")
    async def get_markets():
        return list(store.markets)

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
        store.topics.clear()
        store.offsets.clear()
        store.seed_from_file()
        return {"status": "reset"}

    # ── EWDS gateway emulation (publish/poll request-response) ────────
    # Mimics the EW CGW surface the GSY off-chain storage request handler
    # sits behind: POST publishes a message; the sim handles request topics
    # inline and publishes the response envelope onto the paired response
    # topic; GET consumes messages per (topic, clientId).

    REQUEST_TO_RESPONSE = {
        "ordersQuery": "ordersQueryResponse",
        "tradesQuery": "tradesQueryResponse",
        "marketsQuery": "marketsQueryResponse",
    }

    def _handle_request(topic: str, envelope: dict) -> None:
        request_id = envelope.get("requestId") or envelope.get("request_id")
        payload = envelope.get("payload") or {}
        response_topic = REQUEST_TO_RESPONSE[topic]

        if topic == "ordersQuery":
            market_id = payload.get("marketId") or payload.get("market_id")
            start = payload.get("startTime", payload.get("start_time"))
            end = payload.get("endTime", payload.get("end_time"))
            results = []
            for order in store.orders:
                if market_id is not None and order["marketId"] != market_id:
                    continue
                ts = iso_to_unix(order["timeSlot"])
                # Real handler semantics: inclusive on BOTH ends.
                if start is not None and ts < start:
                    continue
                if end is not None and ts > end:
                    continue
                results.append(_int_order_to_current_dto(order))
        elif topic == "marketsQuery":
            # MarketSchema dialect: snake_case keys, ISO times — served as-is.
            results = list(store.markets)
        else:  # tradesQuery — no server-side market filter, like the real handler
            results = list(store.trades)

        response = {
            "requestId": request_id,
            "success": True,
            "data": results,
            "error": None,
        }
        store.publish(response_topic, json.dumps(response))

    @app.post("/api/v2/messages")
    async def gateway_publish(message: dict = Body(...)):
        topic = message.get("topicName", "")
        try:
            envelope = json.loads(message.get("payload", ""))
        except (TypeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="payload must be a JSON string") from exc
        if topic in REQUEST_TO_RESPONSE:
            _handle_request(topic, envelope)
        else:
            # Unknown topic: store the raw message (lets tests seed noise).
            store.publish(topic, message.get("payload", ""))
        return {"status": "accepted"}

    @app.get("/api/v2/messages")
    async def gateway_consume(
        topicName: str = "",
        clientId: str = "",
        amount: int = 100,
        fqcn: str = "",
        topicOwner: str = "",
    ):
        return store.consume(topicName, clientId, amount)

    return app


app = create_app()
