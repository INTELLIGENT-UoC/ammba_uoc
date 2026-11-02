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

It serves both transports: the plain REST surface (``rest``) and an emulation
of the EWDS Client Gateway's publish/poll request-response channels (``ewds``),
including ``measurementsQuery`` for the calibration fetch step.
"""

import hashlib
import json
import logging
import os
import time
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from src.adapters import iso_to_unix, storage_market_id
from src.ontology import (
    SchemaValidationError,
    validate,
    validate_clearing_result,
    validate_order,
    validate_trade,
)

logger = logging.getLogger(__name__)

SEED_DIR = Path(__file__).parent  # override with SIM_SEED_DIR (e.g. a sim.staging_seed set)
MEASUREMENT_SCHEMA = "int.measurement.schema.v1.json"


class Store:
    def __init__(self) -> None:
        self.orders: list[dict] = []
        self.markets: list[dict] = []
        self.measurements: list[dict] = []
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

    def seed_from_file(self, seed_dir: Path | None = None) -> None:
        seed_dir = seed_dir or Path(os.environ.get("SIM_SEED_DIR") or SEED_DIR)
        path = seed_dir / "seed_orders.json"
        if not path.exists():
            return
        with open(path) as f:
            orders = json.load(f)
        for order in orders:
            validate_order(order)
        self.orders = orders
        logger.info("Seeded %d orders from %s", len(orders), path)
        if (seed_dir / "seed_markets.json").exists():
            with open(seed_dir / "seed_markets.json") as f:
                self.markets = json.load(f)
            logger.info("Seeded %d markets", len(self.markets))
        if (seed_dir / "seed_measurements.json").exists():
            with open(seed_dir / "seed_measurements.json") as f:
                measurements = json.load(f)
            for measurement in measurements:
                validate(measurement, MEASUREMENT_SCHEMA)
            self.measurements = measurements
            logger.info("Seeded %d measurements", len(measurements))


def _int_order_to_ewds_dto(order: dict) -> dict:
    """Render an int:Order seed as the storage's EWDS order DTO.

    The storage keeps order and market IDs in ``0x``-hex form and returns them
    that way; everything else follows int:Order (camelCase, lower-case enums,
    RFC 3339 times). Serving the stored ID form exercises the clearing node's
    UUID-to-hex conversion in its queries.
    """
    dto = dict(order)
    dto["orderId"] = storage_market_id(order["orderId"])
    dto["marketId"] = storage_market_id(order["marketId"])
    return dto


def _rfc3339_to_unix(value) -> int | None:
    if value is None:
        return None
    return iso_to_unix(value) if isinstance(value, str) else int(value)


def create_app(store: Store | None = None) -> FastAPI:
    store = store or Store()
    store.seed_from_file()

    app = FastAPI(title="AMMBA off-chain DB simulator", version="0.1.0")
    app.state.store = store

    def _filter_markets(community_id, start, end) -> list[dict]:
        """markets.query semantics: community and opening-time bounds (inclusive)."""
        out = []
        for market in store.markets:
            if community_id is not None and market["communityId"] != community_id:
                continue
            opening = iso_to_unix(market["openingTime"])
            if start is not None and opening < start:
                continue
            if end is not None and opening > end:
                continue
            out.append(market)
        return out

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
    async def get_markets(
        community_id: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ):
        return _filter_markets(community_id, start_time, end_time)

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
        "measurementsQuery": "measurementsQueryResponse",
        "idsQuery": "idsQueryResponse",
    }

    def _id_mapping(offchain_id: str) -> dict:
        """GSY id-mapping record: onchain_id = 0x + blake2b-128(offchain_id)."""
        digest = hashlib.blake2b(offchain_id.encode("utf-8"), digest_size=16).hexdigest()
        return {
            "offchain_id": offchain_id,
            "onchain_id": "0x" + digest,
            "creation_time": int(time.time()),
        }

    def _handle_request(topic: str, envelope: dict) -> None:
        request_id = envelope.get("requestId") or envelope.get("request_id")
        payload = envelope.get("payload") or {}
        response_topic = REQUEST_TO_RESPONSE[topic]

        if topic == "ordersQuery":
            # Real handler semantics: the market ID is matched literally against
            # the stored 0x-hex form; times are RFC 3339, window [start, end).
            market_id = payload.get("marketId") or payload.get("market_id")
            start = _rfc3339_to_unix(payload.get("startTime", payload.get("start_time")))
            end = _rfc3339_to_unix(payload.get("endTime", payload.get("end_time")))
            results = []
            for order in store.orders:
                if market_id is not None and storage_market_id(order["marketId"]) != market_id:
                    continue
                ts = iso_to_unix(order["timeSlot"])
                if start is not None and ts < start:
                    continue
                if end is not None and ts >= end:
                    continue
                results.append(_int_order_to_ewds_dto(order))
        elif topic == "measurementsQuery":
            # Real handler semantics: RFC 3339 bounds (inclusive), optional
            # facility_id; no community filter.
            facility = payload.get("facility_id") or payload.get("areaUuid")
            start = _rfc3339_to_unix(payload.get("startTime", payload.get("start_time")))
            end = _rfc3339_to_unix(payload.get("endTime", payload.get("end_time")))
            results = []
            for measurement in store.measurements:
                if facility is not None and measurement["facilityId"] != facility:
                    continue
                ts = iso_to_unix(measurement["timeSlot"])
                if start is not None and ts < start:
                    continue
                if end is not None and ts > end:
                    continue
                results.append(measurement)
        elif topic == "marketsQuery":
            results = _filter_markets(
                payload.get("communityId") or payload.get("community_id"),
                _rfc3339_to_unix(payload.get("startTime", payload.get("start_time"))),
                _rfc3339_to_unix(payload.get("endTime", payload.get("end_time"))),
            )
        elif topic == "idsQuery":
            offchain_id = payload.get("offchainId") or payload.get("offchain_id")
            results = [_id_mapping(offchain_id)]
        else:  # tradesQuery — filtered by the stored 0x-hex market ID
            market_id = payload.get("marketId") or payload.get("market_id")
            results = [
                trade
                for trade in store.trades
                if market_id is None or storage_market_id(trade["marketId"]) == market_id
            ]

        response = {
            "requestId": request_id,
            "success": True,
            "data": results,
            "error": None,
        }
        store.publish(response_topic, json.dumps(response))

    @app.post("/ids")
    async def get_or_create_ids(offchain_id: str):
        """REST parity with the real storage: POST /ids?offchain_id=… (idempotent)."""
        return _id_mapping(offchain_id)

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
