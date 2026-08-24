# AMMBA — Automated Market Maker for Batch Auctions

**A peer-to-peer energy market mechanism for the Energy Web Chain.**

AMMBA runs periodic batch auctions for community energy markets. Prosumers submit
buy/sell orders into an off-chain DB during a market window. When the window
closes, a sigmoid-based **uniform clearing price** is computed from the
supply/demand ratio, and all participants trade against a central AMM pool with
quantities allocated **pro-rata**. Clearing results can be anchored on the Energy
Web Chain for transparent audit.

AMMBA acts as an alternative matching engine for the
[GSY Decentralized Exchange](https://github.com/gridsingularity): it consumes and
produces the GSY DEX `int.*` ontology objects (orders in, trades and clearing
results out), so it is interchangeable with the other matching engines.

> Status: v1 MVP — the **clearing node** reads `int:Order`, clears, and emits
> `int:Trade` + `int:ClearingResult`, validated against the vendored ontology
> schemas and exercised end-to-end against a local off-chain DB simulator. The
> execution node (penalties) is deferred. Transport is REST today; the EW Client
> Gateway request/response channels will replace it once the channel conventions
> are finalised upstream.

---

## Why AMMBA?

Continuous order books are a poor fit for low-frequency, small-volume residential
energy markets: they fragment liquidity, expose users to gaming, and make pricing
opaque. AMMBA instead uses a **batch auction with a single clearing price per
slot**, computed by a sigmoid function bounded by the community retail price
(`K_upper`) and feed-in tariff (`K_lower`). This gives:

- **One price per slot**, the same for every participant (before preference adjustments)
- **Welfare-tunable** parameters (`θ`, steepness) that can be optimized from historical data
- **Pool-mediated trades** so no participant needs to be matched 1:1 with another
- **On-chain transparency** without putting the pricing computation on-chain

## Architecture

```
                Market Orchestrator
                  (external trigger)
                         |
                         v
+-----------------+   +---------------------+   +----------------------+
|  Off-chain DB   |<->|  AMM Clearing Node  |-->|   AMM Smart Contract |
|  (GSY DEX)      |   |   :8081  (Python)   |   |  (Energy Web Chain)  |
|  :8080          |   +---------------------+   +----------------------+
|                 |             |                          ^
|  - orders       |       trades-normalized          clearMarket()
|  - trades       |             |                          |
|  - measurements |   +---------------------+              |
|                 |<->|  AMM Execution Node |              |
|                 |   |   :8082  (Python)   |              |
+-----------------+   +---------------------+              |
                                                           |
                          (Phase 3) EW Digital Spine ------+
```

Three components, each independently deployable:

| Component | Stack | Purpose |
|---|---|---|
| [`amm-clearing-node/`](amm-clearing-node/) | Python 3.11+, FastAPI, web3.py | **(v1)** Runs the clearing pipeline: fetch `int:Order` → sigmoid price → pro-rata allocation → preference matching → build `int:Trade` → write trades + `int:ClearingResult` to the off-chain DB → optionally anchor on-chain. |
| [`amm-smart-contract/`](amm-smart-contract/) | Solidity 0.8.24, Hardhat | On-chain audit anchor. Stores cleared market results and emits `MarketCleared` events. Optional for v1. |
| [`amm-execution-node/`](amm-execution-node/) | Python 3.11+, FastAPI | **(deferred)** Post-delivery penalties (shortfall, VCG). Kept for later work; not part of the v1 MVP and not yet migrated to the `int.*` ontology. |

## Core algorithms

- **Sigmoid pricing** — clearing price is a smooth function of the supply/demand
  ratio, bounded between feed-in tariff and retail price.
- **Pro-rata allocation** — the short side is fully served; the long side is
  rationed in proportion to each participant's submitted quantity.
- **Preference matching** — mutual preferred-partner pairs are settled directly
  (priority allocation) before the remaining volume clears against the pool.
  (Energy-type differential pricing is implemented but not yet wired to the
  `int.*` trade output; VCG-style deviation penalties live in the deferred
  execution node.)

Full details and formulas: see [ARCHITECTURE.md](ARCHITECTURE.md). For
contributors and AI coding assistants, the canonical onboarding doc is
[AGENTS.md](AGENTS.md) (with per-component `AGENTS.md` files in each service
directory).

## Quick start

> Want to run the whole stack for your own community, without any external
> services? See [SELF_HOSTING.md](SELF_HOSTING.md).

Requires Docker + Docker Compose. The real GSY DEX off-chain DB is **not**
bundled. For local end-to-end testing, the `dev` compose profile starts a
schema-validating off-chain DB simulator (`amm-clearing-node/sim/`):

```bash
git clone https://github.com/INTELLIGENT-UoC/ammba_uoc.git
cd ammba_uoc
cp .env.example .env             # fill in RPC_URL / keys only if anchoring on-chain
docker compose --profile dev up --build
```

This starts the clearing node on `:8081` and the off-chain DB simulator on
`:8080` (seeded with a sample market). For a real deployment, drop `--profile dev`
and set `OFFCHAIN_DB_URL` to the GSY DEX off-chain DB. Health check:

```bash
curl http://localhost:8081/health
```

### Triggering a clearing

```bash
curl -X POST http://localhost:8081/trigger-clearing \
  -H 'Content-Type: application/json' \
  -d '{"market_id":"33333333-3333-4333-8333-333333333333",
       "community_uuid":"11111111-1111-4111-8111-111111111111",
       "time_slot":1782900000}'
```

Then inspect the trades the simulator received:

```bash
curl 'http://localhost:8080/trades?market_id=33333333-3333-4333-8333-333333333333'
```

### Deploying the smart contract

```bash
cd amm-smart-contract
npm install
npx hardhat compile
npx hardhat test                                   # 17 tests
npx hardhat run scripts/deploy.js --network volta  # needs DEPLOYER_PRIVATE_KEY
```

## Development

Each Python service uses [uv](https://docs.astral.sh/uv/):

```bash
cd amm-clearing-node
uv sync --extra dev
uv run pytest -v                                   # 55 tests (incl. an end-to-end run against the simulator)
```

The execution node is deferred (not part of the v1 MVP); its tests still live in
`amm-execution-node/` for later work.

## Configuration

Each service reads `configuration.yaml` for static parameters and environment
variables for secrets and deployment-specific values. See `.env.example` at the
repo root and the `configuration.yaml` inside each service directory.

| Variable | Used by | Notes |
|---|---|---|
| `RPC_URL` | clearing-node, contract | EWC mainnet or Volta testnet |
| `CONTRACT_ADDRESS` | clearing-node | Address of the deployed `AMMContract` |
| `CLEARING_NODE_PRIVATE_KEY` | clearing-node | Funded EOA that signs `clearMarket()` txs |
| `DEPLOYER_PRIVATE_KEY` | hardhat | One-time, for contract deployment |
| `OFFCHAIN_DB_URL` | clearing-node | GSY DEX off-chain DB endpoint (or the local simulator) |
| `TIME_SLOT_SEC` | clearing-node | Market slot length in seconds (default `900`) |

## Repository layout

```
ammba_uoc/
├── amm-smart-contract/    # Solidity contract + Hardhat tests
├── amm-clearing-node/     # FastAPI clearing service (v1)
│   ├── schemas/intelligent/   # vendored GSY DEX int.* ontology schemas (wire contract)
│   └── sim/                    # local off-chain DB simulator (dev only)
├── amm-execution-node/    # FastAPI penalty service (deferred)
├── docker-compose.yml     # Clearing node + optional simulator (--profile dev)
├── ARCHITECTURE.md        # Full system reference (algorithms, schemas, decisions)
├── AGENTS.md              # Canonical onboarding for contributors + AI assistants
├── CLAUDE.md              # Claude-Code-specific shim → AGENTS.md
├── CONTRIBUTING.md        # Workflow, commit format, branch protection
├── SECURITY.md            # Private vulnerability reporting policy
├── .env.example           # Required environment variables
├── LICENSE                # GPLv3
└── README.md
```

Each component directory also contains its own `AGENTS.md` with a tight,
code-pointer-dense guide to that service.

## Contributing

Issues and pull requests are welcome. Please:

1. Open an issue first to discuss non-trivial changes.
2. Run the test suite for every component you touch.
3. Keep PRs focused — one concern per PR.
4. By submitting a contribution you agree to license it under GPL-3.0-or-later.

## Citation

If you use AMMBA in academic work, please cite this repository. A `CITATION.cff`
file will be added once a companion paper is available.

## License

Copyright (C) 2026 INTELLIGENT-UoC and AMMBA contributors.

This program is free software: you can redistribute it and/or modify it under
the terms of the **GNU General Public License v3.0 or later** as published by
the Free Software Foundation. See [LICENSE](LICENSE) for the full text.

This program is distributed in the hope that it will be useful, but **WITHOUT
ANY WARRANTY**; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE.

## Acknowledgements

AMMBA integrates with the [GSY Decentralized Exchange](https://github.com/gridsingularity)
off-chain database and targets the [Energy Web Chain](https://www.energyweb.org/).
