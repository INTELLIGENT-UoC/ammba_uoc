# Configuration

The clearing engine reads static parameters from
`amm-clearing-node/configuration.yaml` and deployment-specific values from
environment variables. Environment variables always take precedence over the
YAML file; an empty variable counts as unset. The repository's `.env.example`
lists every variable, and Docker Compose passes them from `.env` or the shell
to the clearing node.

## YAML file

| Key                           | Default                           | Environment override |
| ----------------------------- | --------------------------------- | -------------------- |
| `application.host`, `.port`   | `0.0.0.0`, `8081`                 | `HOST`, `PORT`       |
| `offchain_db.base_url`        | `http://localhost:8080`           | `OFFCHAIN_DB_URL`    |
| `blockchain.rpc_url`          | `https://volta-rpc.energyweb.org` | `RPC_URL`            |
| `blockchain.contract_address` | empty (no audit anchor)           | `CONTRACT_ADDRESS`   |
| `market.time_slot_sec`        | `900`                             | `TIME_SLOT_SEC`      |
| `communities`                 | none                              | none                 |

The transport, the EWDS settings, the scheduler, inbound validation and the
signing key have no YAML key and are set through environment variables only.

## Community parameters

Each community is an entry under `communities`, keyed by its UUID:

```yaml
communities:
  11111111-1111-4111-8111-111111111111:
    k_upper_ct_per_kwh: 28.5 # retail price (upper end of the band)
    k_lower_ct_per_kwh: 8.0 # feed-in tariff (lower end of the band)
    theta: 1.0 # midpoint of the pricing function
    steepness: 2.5 # steepness of the pricing function
    green_subsidy_rate: 0.0 # differential pricing, off when both rates are 0
    grey_levy_rate: 0.0
    levy_cap_ct_per_kwh: 5.0
```

| Parameter             | Type   | Default  | Meaning                                                       |
| --------------------- | ------ | -------- | ------------------------------------------------------------- |
| `k_upper_ct_per_kwh`  | number | required | Retail price $K_{\mathrm{up}}$, ct/kWh                        |
| `k_lower_ct_per_kwh`  | number | required | Feed-in tariff $K_{\mathrm{lo}}$, ct/kWh                      |
| `theta`               | number | required | Midpoint $\Theta$; see [calibration](../model/calibration.md) |
| `steepness`           | number | required | Steepness $B$                                                 |
| `green_subsidy_rate`  | number | 0.0      | Target subsidy for green sellers, as a fraction of the price  |
| `grey_levy_rate`      | number | 0.0      | Levy on grey sellers, as a fraction of the price              |
| `levy_cap_ct_per_kwh` | number | 5.0      | Upper limit of the levy per kWh                               |

The last three parameters configure
[differential pricing](../model/extensions.md#energy-type-differential-pricing).
Its adjustments are reported in the clearing summary but not applied to trade
prices. Older configuration files may still carry `pool_id` or
`pool_actor_uuid`; these keys are no longer used and are ignored.

## Environment variables

| Variable                                               | Default                                 | Meaning                                                                                             |
| ------------------------------------------------------ | --------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `HOST`, `PORT`                                         | `0.0.0.0`, `8081`                       | Bind address when started with `python -m src.main`; uvicorn and the image set `--host`/`--port`    |
| `TIME_SLOT_SEC`                                        | `900`                                   | Length of a market slot in seconds                                                                  |
| `OFFCHAIN_TRANSPORT`                                   | `rest`                                  | `rest` for direct store access, `ewds` for the EWDS gateway                                         |
| `OFFCHAIN_DB_URL`                                      | `http://localhost:8080`                 | Off-chain store, for the `rest` transport; Compose defaults to the simulator                        |
| `OFFCHAIN_STRICT_VALIDATION`                           | `true`                                  | Drop (`true`) or only log (`false`) inbound orders that fail validation                             |
| `SCHEDULER_ENABLED`                                    | `false`                                 | Enable the self-trigger scheduler                                                                   |
| `SCHEDULER_POLL_INTERVAL_SEC`                          | `60`                                    | Base interval of the scheduler                                                                      |
| `EWDS_GATEWAY_URL`                                     | `http://ewds-gateway-api:3333`          | Client Gateway, for the `ewds` transport                                                            |
| `EWDS_TOPIC_OWNER`                                     | `integration.apps.intelligent.auth.ewc` | Owner of the request and response topics                                                            |
| `EWDS_TOPIC_VERSION`                                   | `1.0.0`                                 | Topic version                                                                                       |
| `EWDS_REQUEST_PUBLISH_FQCN` or `EWDS_REQUEST_FQCN`     | `gsy.intelligent.requests.pub`          | Channel for publishing requests                                                                     |
| `EWDS_RESPONSE_SUBSCRIBE_FQCN` or `EWDS_RESPONSE_FQCN` | `gsy.intelligent.responses.sub`         | Channel for reading responses                                                                       |
| `EWDS_AMM_CLIENT_ID` or `EWDS_RESPONSE_CLIENT_ID`      | `ammclearingnode`                       | Base of the consumer identifiers; see [consumer identity](../integration/ewds.md#consumer-identity) |
| `EWDS_RESPONSE_TIMEOUT_MS`                             | `60000`                                 | Time to wait for a response                                                                         |
| `EWDS_RESPONSE_POLL_INTERVAL_MS`                       | `1000`                                  | Delay before the first response poll                                                                |
| `EWDS_RESPONSE_POLL_MAX_INTERVAL_MS`                   | `5000`                                  | Ceiling of the polling back-off                                                                     |
| `EWDS_EMPTY_RESPONSE_GRACE_MS`                         | `10000`                                 | Wait for a non-empty response after an empty one; `0` accepts the first response                    |
| `EWDS_RATE_LIMIT_BACKOFF_MS`                           | `2000`                                  | First re-publish delay when a publish reached no recipient or got HTTP 429                          |
| `EWDS_RATE_LIMIT_MAX_BACKOFF_MS`                       | `30000`                                 | Ceiling of the re-publish back-off                                                                  |
| `RPC_URL`                                              | `https://volta-rpc.energyweb.org`       | Chain endpoint, for the optional audit anchor                                                       |
| `CONTRACT_ADDRESS`                                     | empty                                   | Address of the audit-anchor contract                                                                |
| `AUDIT_ANCHOR_PRIVATE_KEY`                             | none                                    | Key that signs audit-anchor transactions (formerly `CLEARING_NODE_PRIVATE_KEY`, still accepted)     |

The audit anchor is used only when both `CONTRACT_ADDRESS` and
`AUDIT_ANCHOR_PRIVATE_KEY` are set; otherwise the engine runs fully off-chain.
Boolean variables accept `true`/`false`, `1`/`0`, `yes`/`no` and `on`/`off`;
any other value stops the service at start-up.

## Other components

**Calibration tool.** Configured through command-line arguments only; see the
[calibration tool](../implementation/calibration-tool.md#usage).

**Settlement engine.** Live execution needs `SETTLEMENT_RPC_URL`,
`TRADE_SETTLEMENT_ADDRESS` and `SETTLEMENT_PRIVATE_KEY`; the dry-run planner
needs none of them. See the
[settlement engine](../implementation/settlement-engine.md).

**Contract deployment.** `amm-smart-contract/scripts/deploy.js` needs
`DEPLOYER_PRIVATE_KEY` and `CLEARING_NODE_ADDRESS` (the account allowed to call
`clearMarket`). Optionally, `COMMUNITY_UUID` with `K_UPPER`, `K_LOWER`, `THETA`
and `STEEPNESS` (scaled by 10,000; defaults 285000, 80000, 10000, 25000)
registers one community's parameters after deployment; the community
identifier must fit into 32 bytes. Hardhat does not read `.env`: export the
variables in the shell.

Never commit real keys. Keep them in environment or secret storage.
