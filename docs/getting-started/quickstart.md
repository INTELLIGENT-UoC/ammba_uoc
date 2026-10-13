# Quick start

This page runs AMMBA locally, clears the bundled sample market, and sets up a
development environment.

## Prerequisites

- Docker with Docker Compose v2, for the containerised quick start.
- [uv](https://docs.astral.sh/uv/) and Python 3.11 or newer, for development.
  Continuous integration uses Python 3.13.
- Node.js 20, only for the optional smart contract.

## Run the local stack

```bash
git clone https://github.com/INTELLIGENT-UoC/ammba_uoc.git
cd ammba_uoc
cp .env.example .env
docker compose --profile dev up --build
```

The `dev` profile starts two services: the clearing engine on port 8081 and a
schema-validating simulator of the off-chain store on port 8080. The simulator
is seeded with one sample market. Check that the engine is up:

```bash
curl http://localhost:8081/health
```

## Clear the sample market

```bash
curl -X POST http://localhost:8081/trigger-clearing \
  -H 'Content-Type: application/json' \
  -d '{"market_id": "33333333-3333-4333-8333-333333333333",
       "community_uuid": "11111111-1111-4111-8111-111111111111",
       "time_slot": 1782900000}'
```

The engine answers with HTTP 202 and a clearing summary in the `detail` field.
For the sample market, with the default parameters of the sample community,
the summary reads:

```json
{
  "status": "cleared",
  "market_id": "33333333-3333-4333-8333-333333333333",
  "total_supply_kwh": 11.0,
  "total_demand_kwh": 10.0,
  "clearing_price_ct_per_kwh": 16.97538173184114,
  "clearing_price_eur_per_kwh": 0.16975381731841138,
  "traded_quantity_kwh": 10.0,
  "num_trades": 4,
  "tx_hash": "0x0",
  "price_adjustments": null
}
```

Supply exceeds demand (ratio 1.1), so the price lies slightly below the
midpoint of the band and buyers are served in full. `tx_hash` is `0x0` because
no on-chain anchor is configured. Inspect the trades the simulator received:

```bash
curl 'http://localhost:8080/trades?market_id=33333333-3333-4333-8333-333333333333'
```

A second trigger for the same market returns without creating new trades,
because the engine checks for existing trades before clearing.

## Development setup

Each Python component is an independent uv project:

```bash
cd amm-clearing-node && uv sync --extra dev && uv run pytest
cd ../amm-calibration && uv sync --extra dev && uv run pytest
cd ../amm-execution-node && uv sync --extra dev && uv run pytest
```

Run the engine and the simulator without Docker:

```bash
cd amm-clearing-node
uv run uvicorn sim.offchain_sim:app --port 8080 &
OFFCHAIN_DB_URL=http://localhost:8080 uv run uvicorn src.main:app --port 8081
```

The smart contract uses Hardhat:

```bash
cd amm-smart-contract && npm ci && npx hardhat test
```

## Build this documentation

```bash
uvx --with-requirements docs/requirements.txt mkdocs serve
```

The site is then available at `http://127.0.0.1:8000`. Continuous integration
builds it with `mkdocs build --strict`, so broken links fail the build.

## Next steps

- [Self-host AMMBA for a community](self-hosting.md)
- [Understand the market model](../model/index.md)
- [Configure the engine](../reference/configuration.md)
