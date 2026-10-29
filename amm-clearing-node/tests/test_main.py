"""Tests for the FastAPI app: health, trigger endpoint and lifespan."""

from fastapi.testclient import TestClient
from src.config import Settings
from src.main import create_app

from tests.conftest import MARKET_ID, TIME_SLOT_UNIX, FakeDBClient, make_int_order

COMMUNITY = "11111111-1111-4111-8111-111111111111"


class ClosableFakeDB(FakeDBClient):
    closed = False

    async def close(self):
        self.closed = True


def _trigger(client, community_uuid=COMMUNITY):
    return client.post(
        "/trigger-clearing",
        json={
            "market_id": MARKET_ID,
            "community_uuid": community_uuid,
            "time_slot": TIME_SLOT_UNIX,
        },
    )


def test_health_trigger_and_shutdown(community):
    app = create_app(Settings(communities={COMMUNITY: community}))
    assert app.state.contract_client is None  # no address configured → off-chain only
    db = ClosableFakeDB([make_int_order("B1", "Bid", 5.0), make_int_order("S1", "Offer", 4.0)])
    app.state.db_client = db

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}

        response = _trigger(client)
        assert response.status_code == 202
        assert response.json()["status"] == "cleared"
        assert len(db.posted_trades) == 2

        assert _trigger(client, community_uuid="unknown").status_code == 400

    assert db.closed  # the lifespan closes the transport client
