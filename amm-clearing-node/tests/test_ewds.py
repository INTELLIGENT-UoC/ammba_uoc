"""Tests for the EWDS/CGW transport: DTO normalizer, client, end-to-end run."""

import json

import httpx
import pytest
from sim.offchain_sim import create_app
from src.adapters import ewds_order_to_int_order, int_order_to_internal
from src.clearing import run_clearing
from src.ewds_client import (
    EwdsConfig,
    EwdsError,
    EwdsOffchainClient,
    EwdsTimeout,
    client_id_for_suffix,
)
from src.ontology import validate_order

from tests.conftest import TIME_SLOT_UNIX, actor_uuid, make_int_order

SEED_MARKET = "33333333-3333-4333-8333-333333333333"


def _ewds_client(app, **config_overrides) -> EwdsOffchainClient:
    """EWDS client wired to the simulator via in-memory ASGI transport."""
    config_kwargs = {"gateway_url": "http://sim", "poll_interval_ms": 5, "timeout_ms": 2000}
    config_kwargs.update(config_overrides)
    config = EwdsConfig(**config_kwargs)
    client = EwdsOffchainClient(config)
    client._client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://sim"
    )
    return client


class TestClientIdHelper:
    def test_alnum_concat(self):
        assert (
            client_id_for_suffix("ammclearingnode", "ordersQueryResponse")
            == "ammclearingnodeordersQueryResponse"
        )

    def test_strips_non_alnum(self):
        assert client_id_for_suffix("amm-node", "orders.Response") == "ammnodeordersResponse"


class TestEwdsOrderNormalizer:
    """One canonical output from all three wire dialects."""

    def _expected_internal(self):
        order = make_int_order("B1", "Bid", 4.5, price_limit=0.12)
        return int_order_to_internal(order)

    def test_current_handler_dialect(self):
        """Today's staging shape: status 'open', nested prefs, unix times."""
        canonical = make_int_order(
            "B1",
            "Bid",
            4.5,
            price_limit=0.12,
            partner=actor_uuid("S1"),
            energy_source="GREEN",
        )
        dto = {
            "orderId": canonical["orderId"],
            "marketId": canonical["marketId"],
            "orderType": "bid",
            "status": "open",
            "areaUuid": canonical["createdBy"],
            "nonce": 7,
            "timeSlot": TIME_SLOT_UNIX,
            "creationTime": TIME_SLOT_UNIX - 900,
            "quantity": 4.5,
            "priceLimit": 0.12,
            "createdBy": canonical["createdBy"],
            "requirements": {
                "tradingPartnerId": actor_uuid("S1"),
                "energyType": "GREEN",
            },
        }
        normalized = ewds_order_to_int_order(dto)
        validate_order(normalized)  # canonical output is schema-valid
        internal = int_order_to_internal(normalized)
        assert internal["status"] == "Open"
        assert internal["order_type"] == "Bid"
        assert internal["time_slot"] == TIME_SLOT_UNIX
        assert internal["energy"] == 4.5
        assert internal["requirements"]["trading_partner_id"] == [actor_uuid("S1")]
        assert internal["requirements"]["energy_source"] == ["GREEN"]

    def test_announced_target_dialect(self):
        """The guide's target DTO: flat fields, lowercase enums, unix times."""
        canonical = make_int_order("S1", "Offer", 3.0, energy_type="PV")
        dto = {
            "orderId": canonical["orderId"],
            "marketId": canonical["marketId"],
            "orderType": "offer",
            "orderStatus": "submitted",
            "timeSlot": TIME_SLOT_UNIX,
            "quantity": 3.0,
            "priceLimit": 0.08,
            "energySourcePreference": None,
            "energyType": "PV",
            "createdBy": canonical["createdBy"],
            "creationTime": TIME_SLOT_UNIX - 900,
            "updatedAt": TIME_SLOT_UNIX - 900,
            "rejectReason": None,
            "preferredTradingPartner": None,
        }
        normalized = ewds_order_to_int_order(dto)
        validate_order(normalized)
        internal = int_order_to_internal(normalized)
        assert internal["status"] == "Open"
        assert internal["order_type"] == "Offer"
        assert internal["attributes"]["energy_type"] == ["PV"]

    def test_final_ontology_passthrough(self):
        """A fully int:Order-shaped payload survives normalization unchanged."""
        canonical = make_int_order("B2", "Bid", 5.0)
        normalized = ewds_order_to_int_order(canonical)
        validate_order(normalized)
        assert int_order_to_internal(normalized) == int_order_to_internal(canonical)

    def test_status_mapping_table(self):
        base = make_int_order("B1", "Bid", 1.0)
        for raw, expected in [
            ("open", "Submitted"),
            ("submitted", "Submitted"),
            ("partially_filled", "PartiallyFilled"),
            ("executed", "Executed"),
            ("deleted", "Cancelled"),
            ("Cancelled", "Cancelled"),
        ]:
            dto = {**base, "orderStatus": raw}
            assert ewds_order_to_int_order(dto)["orderStatus"] == expected


@pytest.mark.asyncio
class TestEwdsClientAgainstSim:
    async def test_orders_roundtrip_normalized(self):
        app = create_app()  # seeds sim/seed_orders.json
        client = _ewds_client(app)
        orders = await client.get_orders(SEED_MARKET, TIME_SLOT_UNIX, TIME_SLOT_UNIX + 900)
        assert len(orders) == 4  # all four seeds are in the slot
        for order in orders:
            validate_order(order)  # normalizer restored the ontology shape
        assert {o["orderType"] for o in orders} == {"Bid", "Offer"}
        assert all(o["orderStatus"] == "Submitted" for o in orders)
        await client.close()

    async def test_inclusive_end_corrected_to_right_open_window(self):
        """An order at exactly slot+900 must NOT appear in [slot, slot+900)."""
        app = create_app()
        store = app.state.store
        boundary = make_int_order(
            "BX", "Bid", 9.9, time_slot="2026-07-01T10:15:00Z"
        )  # == TIME_SLOT_UNIX + 900
        store.orders.append(boundary)

        client = _ewds_client(app)
        orders = await client.get_orders(SEED_MARKET, TIME_SLOT_UNIX, TIME_SLOT_UNIX + 900)
        assert boundary["orderId"] not in {o["orderId"] for o in orders}
        await client.close()

    async def test_stray_messages_are_skipped(self):
        """Garbage + foreign responses on the topic don't break correlation."""
        app = create_app()
        store = app.state.store
        store.publish("ordersQueryResponse", "not-json{")
        store.publish(
            "ordersQueryResponse",
            json.dumps({"requestId": "someone-elses", "success": True, "data": []}),
        )
        client = _ewds_client(app)
        orders = await client.get_orders(SEED_MARKET, TIME_SLOT_UNIX, TIME_SLOT_UNIX + 900)
        assert len(orders) == 4
        await client.close()

    async def test_error_envelope_raises(self):
        app = create_app()
        store = app.state.store
        request_id = "orders-query-test-1"
        store.publish(
            "ordersQueryResponse",
            json.dumps(
                {
                    "requestId": request_id,
                    "success": False,
                    "data": None,
                    "error": {"code": "DB_DOWN", "message": "mongo unavailable"},
                }
            ),
        )
        client = _ewds_client(app)
        with pytest.raises(EwdsError, match="DB_DOWN"):
            await client._poll("orders.query", request_id, "ordersQueryResponse")
        await client.close()

    async def test_timeout_when_no_response(self):
        app = create_app()
        client = _ewds_client(
            app,
            timeout_ms=100,
            topics={"orders.query": ("unhandledTopic", "unhandledResponse")},
        )
        with pytest.raises(EwdsTimeout):
            await client.get_orders(SEED_MARKET, 0, 900)
        await client.close()


@pytest.mark.asyncio
async def test_clearing_end_to_end_over_ewds(community):
    """Full clearing cycle with the EWDS transport against the sim gateway.

    The sim serves the CURRENT (pre-ontology) DTO dialect, so this proves
    normalizer + strict validation + clearing all hold against what the
    staging handler emits today.
    """
    app = create_app()
    client = _ewds_client(app)

    result = await run_clearing(
        market_id=SEED_MARKET,
        community_uuid="11111111-1111-4111-8111-111111111111",
        time_slot=TIME_SLOT_UNIX,
        community_config=community,
        db_client=client,
        contract_client=None,
        time_slot_sec=900,
    )

    assert result["status"] == "cleared"
    assert result["num_trades"] == 4  # direct pref pair + pool trades
    # Writes are a documented no-op on the EWDS transport (settlement is v2).
    assert app.state.store.trades == []
    assert app.state.store.clearing_results == []
    await client.close()


class TestEnergyTypeSentinel:
    """GSY serializes an absent energy type as the string "None" (was GREY)."""

    def _dto(self, **extra):
        dto = {
            "order_id": "aaaaaaaa-0001-4001-8001-000000000001",
            "market_id": "33333333-3333-4333-8333-333333333333",
            "order_type": "offer",
            "order_status": "submitted",
            "time_slot": 1782900000,
            "creation_time": 1782899100,
            "quantity": 5.0,
            "price_limit": 0.12,
            "created_by": "cccccccc-0001-4001-8001-000000000001",
        }
        dto.update(extra)
        return dto

    def test_none_sentinel_becomes_absent(self):
        from src.adapters import ewds_order_to_int_order
        from src.ontology import validate_order

        for sentinel in ("None", "NONE", "null", ""):
            order = ewds_order_to_int_order(self._dto(energy_type=sentinel))
            assert "energyType" not in order
            validate_order(order)  # must not fail the enum

    def test_lowercase_enum_values_are_upcased(self):
        from src.adapters import ewds_order_to_int_order
        from src.ontology import validate_order

        order = ewds_order_to_int_order(self._dto(energy_type="pv"))
        assert order["energyType"] == "PV"
        validate_order(order)

    def test_unknown_value_passes_through_for_loud_validation(self):
        from src.adapters import ewds_order_to_int_order

        order = ewds_order_to_int_order(self._dto(energy_type="FUSION"))
        assert order["energyType"] == "FUSION"  # validation will flag it

    def test_source_preference_gets_same_treatment(self):
        from src.adapters import ewds_order_to_int_order

        order = ewds_order_to_int_order(
            self._dto(order_type="bid", energy_source_preference="None")
        )
        assert "energySourcePreference" not in order


@pytest.mark.asyncio
class TestIdsQuery:
    """Actor id mapping (GSY id-mapping convention, upstream commit 648b346)."""

    async def test_ids_query_roundtrip_matches_blake2b_128(self):
        import hashlib

        app = create_app()
        client = _ewds_client(app)
        actor = "11111111-1111-4111-8111-111111111111"
        record = await client.get_or_create_onchain_id(actor)
        await client.close()
        assert record["offchain_id"] == actor
        expected = "0x" + hashlib.blake2b(actor.encode(), digest_size=16).hexdigest()
        assert record["onchain_id"] == expected == "0x36b3fc2cf928ee46278171375a2903b3"

    async def test_rest_parity_route(self):
        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://sim"
        ) as c:
            first = (await c.post("/ids", params={"offchain_id": "actor-123"})).json()
            second = (await c.post("/ids", params={"offchain_id": "actor-123"})).json()
        assert first["onchain_id"] == second["onchain_id"] == "0xcebf5331e6b4e617eb4e30298d890eec"
