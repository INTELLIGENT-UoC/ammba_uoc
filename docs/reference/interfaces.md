# Interfaces and tools

## Clearing engine HTTP API

The clearing engine serves a small HTTP API on port 8081 by default.

### `POST /trigger-clearing`

Clears one market slot.

```json
{
  "market_id": "33333333-3333-4333-8333-333333333333",
  "community_uuid": "11111111-1111-4111-8111-111111111111",
  "time_slot": 1782900000
}
```

| Field            | Meaning                                        |
| ---------------- | ---------------------------------------------- |
| `market_id`      | The market to clear                            |
| `community_uuid` | A community configured in `configuration.yaml` |
| `time_slot`      | Start of the delivery slot, in Unix seconds    |

Responses:

| Status | Body                                                                                                                                | When                                                                               |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| 202    | `{"status": "...", "detail": {...}}` with the [clearing summary](../implementation/clearing-engine.md#clearing-summary) in `detail` | The request was processed; `status` is `cleared`, `no_trade`, `skipped` or `error` |
| 400    | Error message                                                                                                                       | The community is not configured                                                    |
| 500    | Error message                                                                                                                       | Clearing failed, for example because the store could not be reached                |

### `GET /health`

Returns `{"status": "ok"}` when the service is running.

## Command-line tools

| Tool                               | Component            | Purpose                                                                                                          |
| ---------------------------------- | -------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `python -m src.calibrate`          | `amm-calibration`    | Calibrate the pricing parameters; see [calibration tool](../implementation/calibration-tool.md)                  |
| `python -m src.fetch_measurements` | `amm-clearing-node`  | Retrieve metering history through the EWDS gateway as input for calibration                                      |
| `python -m src.main`               | `amm-execution-node` | Dry-run settlement planner; see [settlement engine](../implementation/settlement-engine.md#command-line-planner) |

Run each tool from its component directory with `uv run`.

**`fetch_measurements` arguments:** `--start` and `--end` (Unix seconds or
ISO-8601, required), `--community`, `--facility`, `--gateway-url` (overrides
`EWDS_GATEWAY_URL`) and `--out` (default `measurements.json`).

## Off-chain store simulator

`amm-clearing-node/sim/` contains a simulator of the off-chain store for
development and tests. It validates every object it receives against the
ontology schemas and keeps data in memory.

| Method and path                                   | Purpose                                                               |
| ------------------------------------------------- | --------------------------------------------------------------------- |
| `GET /health`, `GET /health_check`                | Health check                                                          |
| `GET /orders`                                     | Orders of a market, filtered by `market_id`, `start_time`, `end_time` |
| `GET /markets`                                    | All markets                                                           |
| `GET /trades`, `POST /trades-normalized`          | Read and write trades                                                 |
| `GET /clearing-results`, `POST /clearing-results` | Read and write clearing results                                       |
| `POST /ids`                                       | Identifier mapping, as in the GSY DEX off-chain storage               |
| `GET /api/v2/messages`, `POST /api/v2/messages`   | Emulation of the EWDS gateway                                         |
| `POST /_reset`                                    | Reset to the seeded sample data                                       |

The [simulator guide](https://github.com/INTELLIGENT-UoC/ammba_uoc/blob/main/amm-clearing-node/sim/README.md)
describes local end-to-end runs.
