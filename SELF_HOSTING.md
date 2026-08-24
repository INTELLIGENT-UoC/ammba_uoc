# Self-hosting the AMMBA stack

This guide describes how to run the AMMBA components **self-contained, for a
single community, without any external services** — and what changes when you
join a shared deployment instead. Self-contained operation is a supported
configuration, in line with the project's open-source goals: the shared data
spine and shared settlement are what you join when you want to interoperate
beyond your own community.

## What you run

| Component | Role | Required |
|---|---|---|
| `amm-clearing-node` | Market clearing: orders in → trades out | yes |
| off-chain store | Holds orders/trades (`sim/` simulator for dev, or any store implementing the REST surface) | yes |
| `amm-calibration` | Offline: derive sigmoid params from your history | recommended |
| `amm-smart-contract` | On-chain audit anchor | optional |

## Quick start (one machine)

```bash
git clone https://github.com/INTELLIGENT-UoC/ammba_uoc.git
cd ammba_uoc
docker compose --profile dev up --build
```

This starts the clearing node on `:8081` and the bundled off-chain simulator on
`:8080`, pre-seeded with a sample market. Trigger a clearing and inspect the
resulting trades as shown in [`amm-clearing-node/sim/README.md`](amm-clearing-node/sim/README.md).

For continuous operation, enable the self-trigger scheduler so the node
discovers closed AMM markets and clears them without manual triggers:

```bash
SCHEDULER_ENABLED=true SCHEDULER_POLL_INTERVAL_SEC=60 docker compose --profile dev up
```

## Configuring your community

Edit [`amm-clearing-node/configuration.yaml`](amm-clearing-node/configuration.yaml):

- one entry per community (keyed by its UUID) with the price bounds
  (`k_upper_ct_per_kwh` retail price, `k_lower_ct_per_kwh` feed-in tariff),
  the sigmoid shape (`theta`, `steepness`), and the pool identity
  (`pool_actor_uuid`);
- optional seller-side differential pricing (`green_subsidy_rate`,
  `grey_levy_rate`, `levy_cap_ct_per_kwh`) — zero-sum green/grey price
  adjustment, disabled by default.

Derive `theta`/`steepness` from your own history instead of guessing:

```bash
cd amm-calibration
uv run python -m src.calibrate --measurements history.json \
  --community <uuid> --k-upper 28.5 --k-lower 8.0 --out params.yaml
```

`history.json` is a list of measurement records (positive `energyKwh` =
consumption, negative = production). In a connected deployment you can pull it
over the gateway: `uv run python -m src.fetch_measurements` (see below).

## Production notes

- **Persistence:** the bundled simulator is in-memory and for development.
  For real operation point `OFFCHAIN_DB_URL` at a persistent store
  implementing the same REST surface (the GSY off-chain storage is the
  reference implementation, GPL-3.0, self-hostable with MongoDB).
- **Keys and secrets:** only needed for the optional on-chain anchor
  (`CLEARING_NODE_PRIVATE_KEY`, `CONTRACT_ADDRESS`, `RPC_URL`). Keep keys in
  environment/secret storage, never in the YAML. Without them the node runs
  fully off-chain.
- **Health checks:** `GET /health` on the clearing node; the compose file
  wires container health checks already.
- **Upgrades:** images build from the repo; `uv.lock` pins Python
  dependencies. Run `uv run pytest` per component before deploying a change.

## Joining a shared deployment (interoperability mode)

To participate in a shared data spine (EWDS) instead of the local REST store:

1. Obtain access to the deployment's Client Gateway from its operator (in
   the INTELLIGENT project, GSY operates the gateway): the gateway URL, any
   authentication requirements, and an authorized client id for the AMM.
2. Switch the transport: `OFFCHAIN_TRANSPORT=ewds`,
   `EWDS_GATEWAY_URL=<your gateway>`, plus the topic settings in
   [.env.example](.env.example).
3. Reads (orders, markets, measurements) then flow over the gateway;
   settlement of matches moves on-chain in v2 of the integration.

The clearing algorithm, calibration, and configuration are identical in both
modes — the transport is the only difference.
