# AGENTS.md — amm-clearing-node

> Component-specific onboarding. See the [repo-root AGENTS.md](../AGENTS.md)
> for the big picture first.

## What this service does

Runs the clearing pipeline when a market slot closes:

0. Idempotency check (skip if the market already has trades)
1. Fetch open orders, translate `int:Order` → internal, validate inbound
2. Aggregate supply / demand
3. Compute the uniform clearing price via the sigmoid
4. Record on-chain via `clearMarket()` (optional; deferred for the MVP)
5. Pro-rata allocation
6. Preference matching (mutual preferred pairs)
7. Generate `int:Trade` objects (direct preference pairs, Buyer→Pool, Pool→Seller)
8. POST `int:Trade` list + the `int:ClearingResult` back to the off-chain DB

The AMM pool is a virtual counterparty: participants trade with the pool at the
uniform price, except preference-matched mutual pairs who trade directly. Pool
half-trades serialize to the bilateral `int:Trade` schema via a configured pool
actor UUID and deterministic pool standing orders (see `adapters.py`).

## File map

```
src/
├── main.py            # FastAPI app, POST /trigger-clearing, GET /health
├── clearing.py        # ★ run_clearing() — the pipeline orchestrator
├── adapters.py        # ★ int.* ↔ internal translation; int:Trade / int:ClearingResult builders
├── ontology.py        # loads schemas/intelligent/*, dependency-free validator
├── sigmoid.py         # sigmoid_price(), to_node_int(), from_node_int()
├── preferences.py     # mutual preferred-pair matching
├── offchain_db.py     # async httpx client for the off-chain DB REST API
├── contract.py        # web3.py wrapper for AMMContract (optional/deferred)
└── config.py          # YAML + env-var settings, Pydantic models
schemas/intelligent/   # vendored GSY DEX int.* JSON Schemas (the wire contract)
sim/                   # local off-chain DB simulator for end-to-end tests (dev only)
tests/
└── test_*.py          # incl. conftest.py (schema-validating fake DB), 55 tests total
```

Start at `clearing.py` for an algorithmic change (numbered step sections) or
`adapters.py` for anything touching the wire format.

## Public API

| Endpoint | Method | Body | Returns |
|---|---|---|---|
| `/trigger-clearing` | POST | `{market_id, community_uuid, time_slot}` | clearing summary |
| `/health` | GET | — | `{status: "ok"}` |

## Configuration

`configuration.yaml` holds community params; env vars override. Required env:

| Var | Required when | Default |
|---|---|---|
| `OFFCHAIN_DB_URL` | always | `http://offchain-db:8080` |
| `RPC_URL` | submitting on-chain | `https://volta-rpc.energyweb.org` |
| `CONTRACT_ADDRESS` | submitting on-chain | — |
| `CLEARING_NODE_PRIVATE_KEY` | submitting on-chain | — |
| `TIME_SLOT_SEC` | always | `900` |

If `CONTRACT_ADDRESS` or `CLEARING_NODE_PRIVATE_KEY` is unset, clearing runs
**off-chain only** (step 4 is skipped). Useful for local testing.

## Dev loop

```bash
uv sync --extra dev                              # install (incl. pytest)
uv run pytest -v                                 # 55 tests
uv run pytest tests/test_clearing.py -v          # subset
uv run uvicorn src.main:app --port 8081 --reload # local server
uv run uvicorn sim.offchain_sim:app --port 8080  # local off-chain DB simulator
```

See [`sim/README.md`](sim/README.md) for the full local end-to-end flow.

## Patterns

- **Async everywhere.** `httpx.AsyncClient`, `async def` endpoints, `await`
  every I/O call. `pytest-asyncio` in `auto` mode handles tests.
- **Pure functions for algorithms.** `sigmoid_price`, `pro_rata_allocate`,
  `apply_priority_allocation`, `apply_energy_type_multipliers` all take data
  in and return data out — no side effects, easy to test with concrete numbers.
- **Side effects only in `clearing.py`.** It's the only module that does I/O
  (DB + chain). Keeps the rest unit-testable in isolation.
- **Pydantic for boundaries**, dataclasses or plain dicts internally. Don't
  push Pydantic models through every internal function — it adds noise.
- **The wire is `int.*`; the inside is internal.** Only `adapters.py` knows
  both. The algorithm modules (`clearing.py` minus its edges, `preferences.py`,
  `sigmoid.py`) never see ontology field names.
- **Validate at the boundary.** `clearing.py` validates inbound orders and every
  outbound trade / clearing result via `ontology.py`; the test fake and the
  simulator do the same, so format drift fails the test.

## Conventions to preserve

1. Step numbering (0–8) in `clearing.py`. If you add a step, renumber and
   update the docstring.
2. **Wire objects conform to `schemas/intelligent/*`.** Build them only via the
   `adapters.py` helpers; don't hand-assemble `int:Trade` / `int:ClearingResult`
   dicts elsewhere.
3. **Trade IDs are deterministic `uuid5`** (`adapters.trade_uuid`) so a re-run is
   reproducible. Pool order/actor UUIDs are likewise derived in `adapters.py`.
4. **Price units:** internal is ct/kWh (sigmoid bounds); the wire is EUR/kWh.
   Convert only via `CT_PER_EUR` in `adapters.py`.
5. **`pool_actor_uuid`** (per community in `config.py`) is the pool's identity on
   the wire. The `int:Trade` representation of pool half-trades is provisional
   pending GSY's pool-registration decision.

## Common change recipes

- **New clearing parameter**: add to `CommunityConfig` in `config.py`, thread
  it into `run_clearing()`, document it in `configuration.yaml`.
- **New preference rule**: implement in `preferences.py` as a pure function,
  call it from the relevant step in `clearing.py`, add `test_preferences.py`
  cases.
- **New wire field / trade type**: update the relevant schema in
  `schemas/intelligent/`, add/extend a builder in `adapters.py`, and assert it
  validates in `test_adapters.py`.
- **New off-chain DB endpoint**: add an async method to
  `offchain_db.py:OffchainDBClient` and a matching route in `sim/offchain_sim.py`.

## Don'ts

- Don't call `web3.py` synchronously from a request handler. Wrap it with
  `asyncio.to_thread` if you must.
- Don't store the contract ABI inline — it's loaded from
  `../amm-smart-contract/artifacts/...` so it stays in sync with the deployed
  contract.
- Don't change `NODE_FLOAT_SCALING_FACTOR = 10000`. It is shared with the
  Solidity contract.
- Don't leak internal field names (`energy`, `energy_rate`, `status`, nested
  `requirements`/`attributes`) onto the wire — `additionalProperties: false`
  in the schemas will reject them, and the tests will catch it.
