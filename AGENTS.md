# AGENTS.md — LLM Onboarding for AMMBA

> This file is the **canonical context for any AI coding assistant** working on
> this repo (Claude Code, Cursor, Aider, Codex, Copilot Chat, etc.). Read it
> first. The tool-specific files (`CLAUDE.md`, `.cursor/rules/*`,
> `.github/copilot-instructions.md`) all defer to this document.

If you're a human reader, you can use this file too — it's a 5-minute primer
that gets you from zero to making changes safely.

---

## TL;DR (read this even if you read nothing else)

AMMBA is a **P2P energy market** and an alternative matching engine for the GSY
Decentralized Exchange: every 15 minutes, buyers and sellers submit orders, a
**sigmoid-based clearing price** is computed from supply/demand, quantities are
**pro-rata allocated**, and trades go through an **AMM pool**. It consumes and
produces the GSY DEX `int.*` ontology objects (orders in, trades + clearing
result out). Clearing results can be anchored on the **Energy Web Chain**.

The **v1 MVP is the clearing node**. The execution node (post-delivery
VCG-style penalties) is **deferred** and not in the active stack.

| Path | Stack | Role |
|---|---|---|
| `amm-clearing-node/`  | Python 3.12+, FastAPI, uv | **(v1)** The clearing pipeline; speaks the `int.*` ontology |
| `amm-calibration/`    | Python 3.11+, uv (no heavy deps) | Offline optimization of per-community sigmoid params from history |
| `amm-smart-contract/` | Solidity 0.8.24, Hardhat 2, Node 20 | On-chain audit anchor (optional for v1) |
| `amm-execution-node/` | Python 3.12+, web3.py, uv | **(v2 skeleton)** settlement engine: matches → `settleBatch`; penalties dormant |

For the full system reference (algorithms, data flow, schemas, decision log),
see [ARCHITECTURE.md](ARCHITECTURE.md). For every provisional integration
decision and where to change it, see [INTEGRATION_NOTES.md](INTEGRATION_NOTES.md).

---

## Where the code lives

```
ammba_uoc/
├── AGENTS.md                        # ← you are here
├── CLAUDE.md                        # thin shim → AGENTS.md
├── ARCHITECTURE.md                  # full system reference
├── README.md                        # user-facing intro
├── CONTRIBUTING.md                  # workflow, commit format
├── docker-compose.yml               # clearing node + optional simulator (--profile dev)
│
├── amm-smart-contract/
│   ├── AGENTS.md                    # component-specific onboarding
│   ├── contracts/AMMContract.sol    # the on-chain contract
│   ├── test/AMMContract.test.js     # 17 hardhat tests
│   └── scripts/deploy.js
│
├── amm-clearing-node/              # ← v1 MVP
│   ├── AGENTS.md                    # component-specific onboarding
│   ├── src/
│   │   ├── main.py                  # FastAPI app + routes
│   │   ├── clearing.py              # ★ the clearing pipeline
│   │   ├── adapters.py             # ★ int.* ↔ internal; int:Trade / int:ClearingResult builders
│   │   ├── ontology.py             # schema loader + dependency-free validator
│   │   ├── sigmoid.py               # price function
│   │   ├── preferences.py           # mutual preferred-pair matching
│   │   ├── offchain_db.py           # httpx client for the off-chain DB
│   │   ├── contract.py              # web3.py client for AMMContract (optional)
│   │   └── config.py                # YAML + env-var settings
│   ├── schemas/intelligent/         # vendored GSY DEX int.* schemas (wire contract)
│   ├── sim/                         # local off-chain DB simulator (dev only)
│   └── tests/                       # 55 pytest tests (incl. conftest fake DB + e2e)
│
├── amm-calibration/                # offline sigmoid-param optimization (a job, not a service)
│   ├── AGENTS.md
│   ├── src/                         # pricing.py, optimizer.py, measurements.py, calibrate.py
│   └── tests/
│
├── INTEGRATION_NOTES.md            # provisional decisions + where to change each (read before integration work)
│
└── amm-execution-node/             # ← v2 settlement engine (skeleton)
    ├── AGENTS.md                    # component-specific onboarding
    ├── src/                         # engine.py, match_builder.py, validator.py, structs.py, chain.py
    └── tests/                       # settlement skeleton + dormant penalty math
```

The `★` files are the algorithmic heart of each service — start there when
investigating any clearing/penalty behaviour.

---

## How to run things (cheat sheet)

```bash
# Smart contract
cd amm-smart-contract && npm ci && npx hardhat test           # 17 tests
cd amm-smart-contract && npx hardhat compile

# Clearing node (v1)
cd amm-clearing-node && uv sync --extra dev && uv run pytest -v
cd amm-clearing-node && uv run uvicorn src.main:app --port 8081

# Local off-chain DB simulator (dev; serves/validates int.* objects)
cd amm-clearing-node && uv run uvicorn sim.offchain_sim:app --port 8080

# Local stack: clearing node + simulator, wired together
docker compose --profile dev up --build

# Execution node (deferred — kept for later work)
cd amm-execution-node && uv sync --extra dev && uv run pytest -v
```

Health check: `curl localhost:8081/health`. See
[`amm-clearing-node/sim/README.md`](amm-clearing-node/sim/README.md) for the full
local end-to-end flow.

---

## Critical conventions (don't break these)

1. **Integer scaling**: all on-chain `uint256` values use
   `NODE_FLOAT_SCALING_FACTOR = 10000`. Example: 28.5 ct/kWh → `285000`.
   Helpers live in `sigmoid.py` (`to_node_int`, `from_node_int`).

2. **The wire contract is the `int.*` ontology** in
   [`amm-clearing-node/schemas/intelligent/`](amm-clearing-node/schemas/intelligent).
   Orders in (`int:Order`), trades out (`int:Trade`), and the per-slot summary
   (`int:ClearingResult`) follow these flat, camelCase, EUR/kWh, ISO-8601, UUID
   schemas. Translate at the `adapters.py` boundary; never leak internal field
   names onto the wire. The old nested `bid_component`/`offer_component` shape and
   `trade_builder.py` are retired.

3. **Trade IDs are deterministic `uuid5`** (`adapters.trade_uuid`); pool actor and
   pool order UUIDs are likewise derived in `adapters.py`. (Replaces the previous
   blake2b `_id` convention.)

4. **Pool-mediated trades**: every participant trades with the pool, not with
   each other. Two trades per allocation: Buyer→Pool and Pool→Seller. The **only
   exception** is preference-matched mutual pairs (direct buyer↔seller trade). On
   the wire, the pool is a configured actor (`pool_actor_uuid` per community) with
   deterministic standing orders — provisional, tracked in ARCHITECTURE.md open
   items.

5. **Price units**: internal computation is ct/kWh (the sigmoid bounds); the wire
   is EUR/kWh. The `CT_PER_EUR` conversion lives only in `adapters.py`.

6. **Validation is dependency-free** (`ontology.py`). Don't add `jsonschema`;
   extend the small validator if a schema feature is missing. `sigmoid.py` is
   still duplicated in the (deferred) execution node — keep them in sync if it is
   revived.

7. **Async everywhere** in the Python services: `httpx.AsyncClient`, FastAPI
   async endpoints, pytest-asyncio in `auto` mode. Don't introduce blocking
   I/O in request paths.

8. **Configuration**: each service has `configuration.yaml` for static
   parameters and reads env vars for secrets / per-environment overrides.
   Env vars **always win** over YAML. See `src/config.py` in each service.

---

## How to make changes safely

### Adding a feature to the clearing algorithm
1. Read [`amm-clearing-node/src/clearing.py`](amm-clearing-node/src/clearing.py)
   end-to-end — it orchestrates the whole flow; each numbered step (0–8) is a
   clear seam.
2. Most feature work goes in `preferences.py` or `sigmoid.py`; anything touching
   the wire format goes in `adapters.py` (+ the schema in `schemas/intelligent/`).
   `clearing.py` itself is just the pipeline.
3. Add tests in `amm-clearing-node/tests/`. Use `conftest.py:make_int_order` for
   schema-valid `int:Order` fixtures and `FakeDBClient` (it validates every
   posted trade / clearing result against the ontology).
4. Run `uv sync --extra dev && uv run pytest -v`. Don't introduce new
   dependencies without updating `pyproject.toml` and re-running `uv sync`.

### Touching the smart contract
1. Read [`amm-smart-contract/contracts/AMMContract.sol`](amm-smart-contract/contracts/AMMContract.sol)
   in full (205 lines, well-commented).
2. **Never deploy to EWC mainnet** from CI or scripts. Volta testnet only.
   See `hardhat.config.js` for network definitions.
3. After ABI changes, regenerate artifacts (`npx hardhat compile`). The Python
   clearing node reads the ABI from
   `amm-smart-contract/artifacts/contracts/AMMContract.sol/AMMContract.json`
   at runtime.
4. Run `npx hardhat test` — all 17 must pass. Add a new test for any new
   function or modifier.

### Touching the penalty logic
1. Read [`amm-execution-node/src/penalties.py`](amm-execution-node/src/penalties.py).
2. Three formulas live there: seller shortfall, seller VCG externality, buyer
   VCG externality. Each is a pure function — test with concrete numbers.
3. VCG formulas depend on the sigmoid; counterfactual prices come from
   `src/sigmoid.py` (the local copy, not the clearing node's).

### Adding a new HTTP endpoint
1. Endpoint definition: `src/main.py`.
2. Pydantic request/response models inline with the endpoint.
3. Business logic in a dedicated module — keep `main.py` thin.
4. Mirror the existing `POST /trigger-clearing` pattern: validate → call
   business logic → return summary dict.

---

## How to verify your change

| What you changed | Minimum verification |
|---|---|
| Sigmoid / pricing | `pytest tests/test_sigmoid.py` + property test with random ratios |
| Wire format / adapter | `pytest tests/test_adapters.py tests/test_ontology.py` |
| Trade construction | `pytest tests/test_adapters.py` — built trades must validate against `int:Trade` |
| Preferences | `pytest tests/test_preferences.py` |
| Clearing pipeline | `pytest tests/test_clearing.py` |
| End-to-end (node ↔ off-chain DB) | `pytest tests/test_e2e.py` (runs against the simulator) |
| Smart contract | `npx hardhat test` |
| Anything in CI | Push to a branch and watch the GitHub Actions run |

For manual smoke tests, `docker compose --profile dev up` then exercise the
endpoints with the example payloads in [README.md](README.md) /
[`sim/README.md`](amm-clearing-node/sim/README.md).

---

## Things to never do

- **Don't deploy to EWC mainnet** unless explicitly instructed in a PR.
  Default network is Volta testnet.
- **Don't put secrets in code or YAML.** Use env vars; `.env.example` lists
  what's required.
- **Don't leak internal field names onto the wire** — orders/trades/clearing
  results must conform to the `int.*` schemas (`additionalProperties: false`).
  Build wire objects only via `adapters.py`.
- **Don't add blocking I/O in request paths** — the service is fully async.
- **Don't merge if CI is red.** Branch protection enforces this on `main`.
- **Don't write to `IMPLEMENTATION_GUIDE.md`** (if present locally) — it's the
  immutable original spec. Update `ARCHITECTURE.md` instead.

---

## When you're stuck

- Algorithmic detail you can't infer from the code? → [ARCHITECTURE.md](ARCHITECTURE.md)
  has formulas, decision log, glossary.
- "Where is X done?" → grep the relevant `src/` first; if it's a constant
  (e.g. `NODE_FLOAT_SCALING_FACTOR`), it's defined in `sigmoid.py`.
- "What should this return?" → the existing tests are the most reliable spec.
- Open question / external blocker? → see ARCHITECTURE.md §13 "Open Items".

---

## Project workflow expectations

- **Branching**: trunk-based. Feature branches → PR into `main`. CI must pass.
- **Commits / PR titles**: [Conventional Commits](https://www.conventionalcommits.org/) — see [CONTRIBUTING.md](CONTRIBUTING.md) for the type table.
- **Versioning**: handled automatically by `release-please`. Don't bump version
  numbers manually; the bot opens a "Release PR" when there are unreleased
  commits.
- **Dependencies**: Dependabot opens weekly PRs. Major bumps may need manual
  migration work — see [CONTRIBUTING.md](CONTRIBUTING.md) and the per-component
  `AGENTS.md` files.

---

## License

GPL-3.0-or-later. By submitting code you agree your contribution is under the
same license. See [LICENSE](LICENSE).
