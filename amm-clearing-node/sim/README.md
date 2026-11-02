# Off-chain DB simulator (dev only)

A local stand-in for the GSY DEX off-chain storage, used to test the clearing
node end-to-end without the real GSY environment. It exposes the REST surface
the clearing node uses and serves / accepts **only** `int.*` ontology objects,
validating every payload against the vendored schemas — so a format mismatch
fails loudly instead of silently passing.

It is not part of the deployed service. It ships in the image only so the
compose `dev` profile can run it; it is never started in staging/production.

## Run standalone

```bash
uv run uvicorn sim.offchain_sim:app --port 8080
```

Seeds an in-memory store from `seed_orders.json` (orders with a mutual
preferred pair), `seed_markets.json` (one AMM and one pay-as-bid market) and
`seed_measurements.json` (metering records for the calibration fetch step).
REST endpoints: `GET /orders`, `GET /markets`, `GET /trades`,
`POST /trades-normalized`, `POST /clearing-results`, `GET /clearing-results`,
`POST /ids`, `POST /_reset`, `GET /health` (alias `/health_check`). The EWDS
gateway emulation (`POST`/`GET /api/v2/messages`) answers `ordersQuery`,
`tradesQuery`, `marketsQuery`, `measurementsQuery` and `idsQuery`.

## Run with the clearing node (compose)

```bash
docker compose --profile dev up
```

Starts the simulator on `:8080` and the clearing node on `:8081` wired to it.
Trigger a clearing cycle (the seed market's slot is `2026-07-01T10:00:00Z`):

```bash
curl -X POST localhost:8081/trigger-clearing \
  -H 'content-type: application/json' \
  -d '{"market_id":"33333333-3333-4333-8333-333333333333",
       "community_uuid":"11111111-1111-4111-8111-111111111111",
       "time_slot":1782900000}'
```

Then inspect the produced trades: `curl 'localhost:8080/trades?market_id=33333333-3333-4333-8333-333333333333'`.

The same flow is exercised automatically by `tests/test_e2e.py`.

## Staging test data

A staging environment receives no live orders or metering data, so its
off-chain storage is seeded with test data instead. `sim.staging_seed`
generates a deterministic set for one UTC day:

```bash
uv run python -m sim.staging_seed --date 2026-11-10 --out staging-seed
```

- `seed_markets.json`: 96 quarter-hour AMM markets of a dedicated test
  community, each opening 30 minutes before delivery.
- `seed_orders.json`: the bids and offers of seven synthetic participants
  (households, a bakery, two PV roofs, a biomass CHP) in every market,
  including one mutual preferred pair. The supply/demand ratio ranges from
  about 0.3 in the evening peak to about 3.7 at midday.
- `seed_measurements.json`: net-load metering of the same participants for the
  days before (`--history-days`, default 2) for `amm-calibration`.
- `community.yaml`: the community block for `configuration.yaml`.

All objects validate against the vendored `int.*` schemas, and IDs are
`uuid5` values, so regenerating a date reproduces the same objects. Price
limits sit outside the community's price band: AMM clearing ignores them, but
on-chain settlement checks them.

The file names match the simulator's, so the set can be rehearsed locally
before it goes to staging:

```bash
SIM_SEED_DIR=staging-seed uv run uvicorn sim.offchain_sim:app --port 8080
```

Add the `community.yaml` block to `configuration.yaml` and start the clearing
node with `SCHEDULER_ENABLED=true`. The scheduler only looks at markets that
opened in the last 24 hours, so generate the set for the day of the test.
`tests/test_staging_seed.py` runs this rehearsal in-process.
