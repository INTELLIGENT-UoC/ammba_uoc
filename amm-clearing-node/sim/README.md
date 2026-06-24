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

Seeds an in-memory store from `seed_orders.json` (one market with a mutual
preferred pair). Endpoints: `GET /orders`, `GET /trades`, `POST /trades-normalized`,
`POST /clearing-results`, `GET /clearing-results`, `POST /_reset`, `GET /health`.

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
