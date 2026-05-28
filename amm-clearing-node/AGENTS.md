# AGENTS.md — amm-clearing-node

> Component-specific onboarding. See the [repo-root AGENTS.md](../AGENTS.md)
> for the big picture first.

## What this service does

Runs the **8-step clearing algorithm** when a market slot closes:

1. Idempotency check (skip if already cleared)
2. Fetch open orders from off-chain DB
3. Aggregate supply / demand
4. Compute clearing price via sigmoid
5. Record on-chain via `clearMarket()` (optional)
6. Pro-rata allocation
7. Preference matching (mutual pairs + energy-type multipliers)
8. POST normalised trades back to off-chain DB

Returns a summary dict with totals, clearing price, and tx hash.

## File map

```
src/
├── main.py            # FastAPI app, POST /trigger-clearing, GET /health
├── clearing.py        # ★ run_clearing() — the 8-step pipeline orchestrator
├── sigmoid.py         # sigmoid_price(), to_node_int(), from_node_int()
├── trade_builder.py   # build_*_trade() helpers, blake2b_hash()
├── preferences.py     # mutual pairs + energy-type multipliers
├── offchain_db.py     # async httpx client for GSY DEX REST API
├── contract.py        # web3.py wrapper for AMMContract
└── config.py          # YAML + env-var settings, Pydantic models
tests/
└── test_*.py          # one file per src module, 43 tests total
```

Start at `clearing.py` for any algorithmic change — every step is a numbered
section with a comment header.

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
uv sync --extra dev                              # install
uv run pytest -v                                 # 43 tests
uv run pytest tests/test_clearing.py -v          # subset
uv run uvicorn src.main:app --port 8081 --reload # local server
```

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
- **Mock at the HTTP layer.** Tests use `respx` to mock `httpx` responses
  rather than mocking client methods. More realistic, catches schema drift.

## Conventions to preserve

1. Step numbering (0–8) in `clearing.py`. If you add a step, renumber and
   update the docstring.
2. `blake2b_hash(data)` returns `"0x" + 64 hex chars` for a 32-byte digest.
   Don't switch to SHA-256 — GSY DEX uses blake2b.
3. `pool_id = f"AMM_POOL_{community_uuid}"` (defined once; don't inline).
4. Trade `parameters` dict carries provenance:
   `{selected_energy, energy_rate, amm_tx_hash, theta, steepness,
   total_supply_kwh, total_demand_kwh, preference_matched}`. Adding a new
   field is fine; renaming an existing one is a breaking change for
   downstream consumers.
5. **`sigmoid.py` is duplicated** in `amm-execution-node/src/sigmoid.py`.
   If you change one, change the other and add a regression test in both.

## Common change recipes

- **New clearing parameter**: add to `CommunityConfig` in `config.py`, thread
  it into `run_clearing()`, document it in `configuration.yaml`.
- **New preference rule**: implement in `preferences.py` as a pure function,
  call it from the relevant step in `clearing.py`, add `test_preferences.py`
  cases.
- **New trade type**: add a `build_<x>_trade()` to `trade_builder.py`
  following the existing shape; add a hash determinism test.
- **New off-chain DB endpoint**: add an async method to
  `offchain_db.py:OffChainDBClient`; use `respx` in tests.

## Don'ts

- Don't call `web3.py` synchronously from a request handler. Wrap it with
  `asyncio.to_thread` if you must.
- Don't store the contract ABI inline — it's loaded from
  `../amm-smart-contract/artifacts/...` so it stays in sync with the deployed
  contract.
- Don't change `NODE_FLOAT_SCALING_FACTOR = 10000`. It is shared with the
  Solidity contract.
