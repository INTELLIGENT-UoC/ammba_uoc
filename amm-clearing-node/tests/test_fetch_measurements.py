"""Tests for the EWDS measurements query and the calibration fetch CLI."""

import json

import httpx
import pytest
from src.ewds_client import EwdsConfig, EwdsOffchainClient

MEASUREMENTS = [
    {
        "facilityId": "area-1",
        "communityUuid": "c1",
        "timeSlot": "2026-07-01T10:00:00Z",
        "creationTime": "2026-07-01T10:15:00Z",
        "energyKwh": 4.2,
    },
    {
        "facilityId": "area-2",
        "communityUuid": "c1",
        "timeSlot": "2026-07-01T10:00:00Z",
        "creationTime": "2026-07-01T10:15:01Z",
        "energyKwh": -1.5,
    },
    {
        "facilityId": "area-9",
        "communityUuid": "other",
        "timeSlot": "2026-07-01T10:00:00Z",
        "creationTime": "2026-07-01T10:15:02Z",
        "energyKwh": 1.0,
    },
]
C1 = MEASUREMENTS[:2]  # the handler has no community filter; the client drops "other"


def _gateway_transport(data, captured):
    """Fake CGW: capture the published envelope, answer the poll with data."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            dto = json.loads(request.content)
            captured["envelope"] = json.loads(dto["payload"])
            captured["topic"] = dto["topicName"]
            return httpx.Response(200, json={"sent": 1, "failed": 0})
        response_envelope = {
            "requestId": captured["envelope"]["requestId"],
            "success": True,
            "data": data,
            "error": None,
        }
        return httpx.Response(200, json=[{"payload": json.dumps(response_envelope)}])

    return httpx.MockTransport(handler)


def _client_with_transport(transport) -> EwdsOffchainClient:
    client = EwdsOffchainClient(EwdsConfig(gateway_url="http://gw", poll_interval_ms=1))
    client._client = httpx.AsyncClient(transport=transport)
    return client


@pytest.mark.asyncio
async def test_get_measurements_roundtrip():
    captured: dict = {}
    client = _client_with_transport(_gateway_transport(MEASUREMENTS, captured))

    data = await client.get_measurements(
        start_time=1782900000, end_time=1782903600, community_uuid="c1"
    )
    await client.close()

    assert data == C1
    assert captured["topic"] == "measurementsQuery"
    envelope = captured["envelope"]
    assert envelope["operation"] == "measurements.query"
    # RFC 3339 bounds; no community key (the handler has no such filter).
    assert envelope["payload"] == {
        "startTime": "2026-07-01T10:00:00Z",
        "endTime": "2026-07-01T11:00:00Z",
    }


def test_fetch_cli_writes_calibration_input(tmp_path, monkeypatch):
    """Sync on purpose: the CLI owns its own event loop via asyncio.run."""
    from src import fetch_measurements as cli

    captured: dict = {}
    transport = _gateway_transport(MEASUREMENTS, captured)

    real_init = EwdsOffchainClient.__init__

    def patched_init(self, config=None):
        real_init(self, config)
        self._client = httpx.AsyncClient(transport=transport)

    monkeypatch.setattr(EwdsOffchainClient, "__init__", patched_init)

    out = tmp_path / "measurements.json"
    rc = cli.main(
        [
            "--start",
            "2026-07-01T10:00:00Z",
            "--end",
            "1782903600",
            "--community",
            "c1",
            "--out",
            str(out),
        ]
    )

    assert rc == 0
    written = json.loads(out.read_text())
    assert written == C1
    # ISO and unix CLI inputs both go on the wire as RFC 3339.
    assert captured["envelope"]["payload"]["startTime"] == "2026-07-01T10:00:00Z"
    assert captured["envelope"]["payload"]["endTime"] == "2026-07-01T11:00:00Z"


@pytest.mark.asyncio
async def test_fetch_against_simulator(tmp_path, monkeypatch):
    """The fetch step runs end-to-end against the local simulator's gateway."""
    from sim.offchain_sim import create_app
    from src import fetch_measurements as cli
    from src.ontology import validate

    app = create_app()  # seeds sim/seed_measurements.json
    transport = httpx.ASGITransport(app=app)
    real_init = EwdsOffchainClient.__init__

    def patched_init(self, config=None):
        real_init(self, config)
        self._client = httpx.AsyncClient(transport=transport, base_url="http://sim")

    monkeypatch.setattr(EwdsOffchainClient, "__init__", patched_init)

    out = tmp_path / "measurements.json"
    args = cli.argparse.Namespace(
        start="2026-07-01T10:00:00Z",
        end="2026-07-01T10:15:00Z",  # inclusive: the first two slots
        community="11111111-1111-4111-8111-111111111111",
        facility=None,
        gateway_url="http://sim",
        out=str(out),
    )
    assert await cli.fetch(args) == 0

    written = json.loads(out.read_text())
    assert len(written) == 6  # three facilities × two slots; other community excluded
    for measurement in written:
        validate(measurement, "int.measurement.schema.v1.json")
    assert {m["timeSlot"] for m in written} == {"2026-07-01T10:00:00Z", "2026-07-01T10:15:00Z"}
