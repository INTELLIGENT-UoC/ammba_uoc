# AGENTS.md — LLM Onboarding for AMMBA

> This file is the **canonical context for any AI coding assistant** working on
> this repo (Claude Code, Cursor, Aider, Codex, Copilot Chat, etc.). Read it
> first. The tool-specific files (`CLAUDE.md`, `.cursor/rules/*`,
> `.github/copilot-instructions.md`) all defer to this document.

If you're a human reader, you can use this file too — it's a 5-minute primer
that gets you from zero to making changes safely.

---

## TL;DR (read this even if you read nothing else)

AMMBA is a **P2P energy market**: every 15 minutes, buyers and sellers submit
orders, a **sigmoid-based clearing price** is computed from supply/demand,
quantities are **pro-rata allocated**, and trades go through an **AMM pool**.
Clearing results are anchored on the **Energy Web Chain** (a public PoA chain).
After delivery, an execution node computes **VCG-style penalties** for
deviations.

Three components, all independently testable and deployable:

| Path | Stack | Role |
|---|---|---|
| `amm-smart-contract/` | Solidity 0.8.24, Hardhat 2, Node 20 | On-chain audit anchor |
| `amm-clearing-node/`  | Python 3.13, FastAPI, uv | Runs the 8-step clearing algorithm |
| `amm-execution-node/` | Python 3.13, FastAPI, uv | Computes post-delivery penalties |

For the full system reference (algorithms, data flow, schemas, decision log),
see [ARCHITECTURE.md](ARCHITECTURE.md) — 800-line authoritative doc.

---

## Where the code lives

```
ammba_uoc/
├── AGENTS.md                        # ← you are here
├── CLAUDE.md                        # thin shim → AGENTS.md
├── ARCHITECTURE.md                  # full system reference
├── README.md                        # user-facing intro
├── CONTRIBUTING.md                  # workflow, commit format
├── docker-compose.yml               # both Python services
│
├── amm-smart-contract/
│   ├── AGENTS.md                    # component-specific onboarding
│   ├── contracts/AMMContract.sol    # the on-chain contract
│   ├── test/AMMContract.test.js     # 17 hardhat tests
│   └── scripts/deploy.js
│
├── amm-clearing-node/
│   ├── AGENTS.md                    # component-specific onboarding
│   ├── src/
│   │   ├── main.py                  # FastAPI app + routes
│   │   ├── clearing.py              # ★ the 8-step clearing pipeline
│   │   ├── sigmoid.py               # price function
│   │   ├── trade_builder.py         # Trade dict construction + blake2b
│   │   ├── preferences.py           # mutual pairs + energy-type multipliers
│   │   ├── offchain_db.py           # httpx client for GSY DEX
│   │   ├── contract.py              # web3.py client for AMMContract
│   │   └── config.py                # YAML + env-var settings
│   └── tests/                       # 43 pytest tests
│
└── amm-execution-node/
    ├── AGENTS.md                    # component-specific onboarding
    ├── src/
    │   ├── main.py                  # FastAPI app + --poll mode
    │   ├── execution.py             # cycle orchestration
    │   ├── penalties.py             # ★ shortfall + 2× VCG formulas
    │   ├── sigmoid.py               # copy of clearing-node's, for counterfactuals
    │   ├── offchain_db.py
    │   └── config.py
    └── tests/                       # 19 pytest tests
```

The `★` files are the algorithmic heart of each service — start there when
investigating any clearing/penalty behaviour.

---

## How to run things (cheat sheet)

```bash
# Smart contract
cd amm-smart-contract && npm ci && npx hardhat test           # 17 tests
cd amm-smart-contract && npx hardhat compile

# Clearing node
cd amm-clearing-node && uv sync --extra dev && uv run pytest -v
cd amm-clearing-node && uv run uvicorn src.main:app --port 8081

# Execution node
cd amm-execution-node && uv sync --extra dev && uv run pytest -v
cd amm-execution-node && uv run uvicorn src.main:app --port 8082

# Full stack (both Python services; the GSY DEX off-chain DB is not bundled)
docker compose up --build
```

Health checks: `curl localhost:8081/health` and `localhost:8082/health`.

---

## Critical conventions (don't break these)

1. **Integer scaling**: all on-chain `uint256` values use
   `NODE_FLOAT_SCALING_FACTOR = 10000`. Example: 28.5 ct/kWh → `285000`.
   Helpers live in `sigmoid.py` (`to_node_int`, `from_node_int`).

2. **Trade hashing**: `_id` of a trade is `"0x" + blake2b-256` of the
   `json.dumps(trade, sort_keys=True)` payload. See
   [`amm-clearing-node/src/trade_builder.py`](amm-clearing-node/src/trade_builder.py)
   `blake2b_hash()`. **Order of keys matters** — `sort_keys=True` is mandatory.

3. **Pool-mediated trades**: every participant trades with the pool, not with
   each other. Two trades per allocation: Buyer→Pool and Pool→Seller.
   The **only exception** is preference-matched mutual pairs (direct trade,
   `parameters.preference_matched = True`).

4. **Pool identifier**: `AMM_POOL_{community_uuid}` (provisional; tracked in
   ARCHITECTURE.md open items).

5. **Off-chain DB schema is fixed**: nested
   `bid.bid_component` / `offer.offer_component` structure, mirroring the GSY
   DEX Postman collection. Don't flatten it; downstream consumers depend on it.

6. **Sigmoid is duplicated** between clearing and execution nodes (see
   `sigmoid.py` in both). This is **intentional** — independent deployability
   beats DRY here. If you change one, change both, and add a regression test.

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
   end-to-end — it's ~300 lines and orchestrates the whole flow. Each numbered
   step (0–8) is a clear seam.
2. Most feature work goes in `preferences.py`, `trade_builder.py`, or
   `sigmoid.py` — `clearing.py` itself is just the pipeline.
3. Add tests in `amm-clearing-node/tests/`. Pattern: one file per source module,
   `test_<module>.py`. Use the existing test fixtures as templates — they
   already include sample orders, bids, and offers in the right schema.
4. Run `uv run pytest -v`. Don't introduce new dependencies without updating
   `pyproject.toml` and re-running `uv sync`.

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
| Trade construction | `pytest tests/test_trade_builder.py` — check hash determinism |
| Preferences | `pytest tests/test_preferences.py` — both mutual-pair and energy-type cases |
| Clearing pipeline | `pytest tests/test_clearing.py` end-to-end |
| Penalties | `pytest tests/test_penalties.py` — supply-limited and demand-limited rounds |
| Smart contract | `npx hardhat test` — all 17 |
| FastAPI surface | `pytest tests/test_main.py` + `curl localhost:808x/health` |
| Anything in CI | Push to a branch and watch the GitHub Actions run |

For UI/manual smoke tests, `docker compose up` then exercise the endpoints
with the example payloads in [README.md](README.md).

---

## Things to never do

- **Don't deploy to EWC mainnet** unless explicitly instructed in a PR.
  Default network is Volta testnet.
- **Don't put secrets in code or YAML.** Use env vars; `.env.example` lists
  what's required.
- **Don't break the trade hash determinism** — `sort_keys=True` and the
  blake2b digest size are load-bearing.
- **Don't add blocking I/O in request paths** — both services are fully async.
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
