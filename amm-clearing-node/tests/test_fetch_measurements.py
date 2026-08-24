"""Tests for the EWDS measurements query and the calibration fetch CLI."""

import json

import httpx
import pytest
from src.ewds_client import EwdsConfig, EwdsOffchainClient

MEASUREMENTS = [
    {
        "facilityId": "area-1",
        "communityUuid": "c1",
        "timeSlot": 1782900000,
        "creationTime": 1782900900,
        "energyKwh": 4.2,
    },
    {
        "facilityId": "area-2",
        "communityUuid": "c1",
        "timeSlot": 1782900000,
        "creationTime": 1782900901,
        "energyKwh": -1.5,
    },
]


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

    assert data == MEASUREMENTS
    assert captured["topic"] == "measurementsQuery"
    envelope = captured["envelope"]
    assert envelope["operation"] == "measurements.query"
    assert envelope["payload"] == {
        "startTime": 1782900000,
        "endTime": 1782903600,
        "communityUuid": "c1",
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
    assert written == MEASUREMENTS
    # ISO start parsed to unix; numeric end passed through.
    assert captured["envelope"]["payload"]["startTime"] == 1782900000
    assert captured["envelope"]["payload"]["endTime"] == 1782903600
