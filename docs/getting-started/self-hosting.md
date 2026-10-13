# Self-hosting a community

This guide describes how to run AMMBA self-contained for a single community,
without any external services, and what changes when the community joins a
shared deployment instead. Self-contained operation is a supported
configuration and reflects the project's goal that energy communities can own
and run their trading tools. A shared data spine and shared settlement are what
a community joins when it wants to interoperate beyond its own boundaries.

## What you run

| Component            | Role                                                                                                                                | Required    |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| `amm-clearing-node`  | Market clearing: orders in, trades and clearing result out                                                                          | yes         |
| Off-chain store      | Holds orders, markets, trades and results; the bundled simulator for development, or any store implementing the same REST interface | yes         |
| `amm-calibration`    | Offline job that derives the pricing parameters from the community's own history                                                    | recommended |
| `amm-smart-contract` | On-chain audit anchor of clearing results                                                                                           | optional    |

## Quick start on one machine

```bash
git clone https://github.com/INTELLIGENT-UoC/ammba_uoc.git
cd ammba_uoc
cp .env.example .env
docker compose --profile dev up --build
```

This starts the clearing engine on port 8081 and the off-chain store simulator
on port 8080, seeded with a sample market. The [quick start](quickstart.md)
shows how to trigger a clearing and inspect the trades.

For continuous operation, enable the self-trigger scheduler. The engine then
discovers closed AMM markets and clears them without manual triggers:

```bash
SCHEDULER_ENABLED=true SCHEDULER_POLL_INTERVAL_SEC=60 docker compose --profile dev up
```

## Configuring your community

Each community is one entry in
[`amm-clearing-node/configuration.yaml`](https://github.com/INTELLIGENT-UoC/ammba_uoc/blob/main/amm-clearing-node/configuration.yaml),
keyed by the community's UUID. An entry sets:

- the price band: `k_upper_ct_per_kwh` (retail price) and `k_lower_ct_per_kwh`
  (feed-in remuneration), in ct/kWh;
- the shape of the pricing function: `theta` and `steepness`;
- the identity of the pool on the exchange: `pool_id` and `pool_actor_uuid`;
- optionally, seller-side differential pricing: `green_subsidy_rate`,
  `grey_levy_rate` and `levy_cap_ct_per_kwh`. It is disabled by default; see
  [preferences and differential pricing](../model/extensions.md).

The full list is in the [configuration reference](../reference/configuration.md).

Derive `theta` and `steepness` from the community's own history rather than
guessing them:

```bash
cd amm-calibration
uv run python -m src.calibrate --measurements history.json \
  --community <community-uuid> --k-upper 28.5 --k-lower 8.0 --out params.yaml
```

`history.json` is a list of measurement records. By default, a positive
`energyKwh` denotes consumption and a negative one injection; pass
`--injection-positive` for the opposite convention. In a connected deployment
the history can be retrieved through the gateway with
`uv run python -m src.fetch_measurements` in `amm-clearing-node`. The
[calibration tool](../implementation/calibration-tool.md) page describes both
tools, and [parameter governance](../model/governance.md) describes who should
decide the parameters and how.

## Production notes

- **Persistence.** The bundled simulator keeps data in memory and is meant for
  development. For real operation, point `OFFCHAIN_DB_URL` at a persistent
  store that implements the same REST interface. The GSY DEX off-chain storage
  is the reference implementation; it is GPL-3.0 licensed and can be
  self-hosted with MongoDB.
- **Keys and secrets.** Keys are only needed for the optional on-chain anchor
  (`CLEARING_NODE_PRIVATE_KEY`, `CONTRACT_ADDRESS`, `RPC_URL`). Keep them in
  environment or secret storage, never in the YAML file. Without them the
  engine runs fully off-chain.
- **Health checks.** `GET /health` on the clearing engine; the compose file
  already wires container health checks.
- **Upgrades.** Images build from the repository, and `uv.lock` pins the
  Python dependencies. Run each component's test suite before deploying a
  change.

## Joining a shared deployment

To take part in a shared data spine (EWDS) instead of using the local store:

1. Obtain access to the deployment's Client Gateway from its operator: the
   gateway URL, any authentication requirements, and an authorised client id
   for the AMM. In the INTELLIGENT project, Grid Singularity operates the
   gateway.
2. Switch the transport with `OFFCHAIN_TRANSPORT=ewds` and
   `EWDS_GATEWAY_URL=<gateway URL>`, plus the topic settings listed in the
   [configuration reference](../reference/configuration.md#environment-variables).
3. Orders, markets and measurements are then read through the gateway.
   Settlement of matches moves on-chain with version 2 of the integration; see
   [the settlement engine](../implementation/settlement-engine.md).

The clearing algorithm, the calibration and the configuration are identical in
both modes; only the transport differs. The [EWDS transport](../integration/ewds.md)
page documents the gateway protocol.
