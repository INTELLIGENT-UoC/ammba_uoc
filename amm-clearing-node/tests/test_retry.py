"""Tests for the transport retry helper and its wiring into the clients."""

import httpx
import pytest

from src.offchain_db import OffchainDBClient
from src.retry import request_with_retries


def _flaky_transport(outcomes):
    """MockTransport that pops one scripted outcome per request.

    An outcome is either an int (HTTP status to return) or an exception to
    raise. Records the number of requests seen on ``calls``.
    """
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(outcome, json=[])

    return httpx.MockTransport(handler), state


@pytest.mark.asyncio
async def test_retries_transport_errors_then_succeeds():
    transport, state = _flaky_transport(
        [httpx.ConnectError("boom"), httpx.ReadTimeout("slow"), 200]
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://x") as client:
        resp = await request_with_retries(client, "GET", "/orders", base_delay_s=0)
    assert resp.status_code == 200
    assert state["calls"] == 3


@pytest.mark.asyncio
async def test_retries_5xx_then_succeeds():
    transport, state = _flaky_transport([503, 200])
    async with httpx.AsyncClient(transport=transport, base_url="http://x") as client:
        resp = await request_with_retries(client, "GET", "/orders", base_delay_s=0)
    assert resp.status_code == 200
    assert state["calls"] == 2


@pytest.mark.asyncio
async def test_4xx_is_not_retried():
    transport, state = _flaky_transport([404])
    async with httpx.AsyncClient(transport=transport, base_url="http://x") as client:
        resp = await request_with_retries(client, "GET", "/orders", base_delay_s=0)
    assert resp.status_code == 404
    assert state["calls"] == 1


@pytest.mark.asyncio
async def test_exhaustion_raises_last_transport_error():
    transport, state = _flaky_transport(
        [httpx.ConnectError("a"), httpx.ConnectError("b"), httpx.ConnectError("c")]
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://x") as client:
        with pytest.raises(httpx.ConnectError):
            await request_with_retries(client, "GET", "/orders", base_delay_s=0)
    assert state["calls"] == 3


@pytest.mark.asyncio
async def test_exhaustion_returns_last_5xx_response():
    transport, state = _flaky_transport([503, 503, 503])
    async with httpx.AsyncClient(transport=transport, base_url="http://x") as client:
        resp = await request_with_retries(client, "GET", "/orders", base_delay_s=0)
    assert resp.status_code == 503
    assert state["calls"] == 3


@pytest.mark.asyncio
async def test_offchain_client_survives_transient_failure():
    """The REST client's get_orders recovers from one transport error."""
    transport, state = _flaky_transport([httpx.ConnectError("flap"), 200])
    db = OffchainDBClient("http://x")
    db._client = httpx.AsyncClient(transport=transport, base_url="http://x")

    orders = await db.get_orders("m1", 0, 900)
    assert orders == []
    assert state["calls"] == 2
    await db.close()
