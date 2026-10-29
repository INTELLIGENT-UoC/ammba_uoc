# Calibration tool

The calibration tool (`amm-calibration`) implements the
[parameter calibration](../model/calibration.md) as an offline job. The
community's administrator runs it in two steps: the clearing engine's fetch
step retrieves the metering history over the EWDS and writes it to a snapshot
file, and the calibration tool fits $\Theta$ and $B$ to that snapshot. The
tool itself needs only the Python standard library and a YAML parser.

## Input data

The metering history consists of the `int:Measurement` records that the GSY
DEX off-chain storage holds for the community. The fetch step of the clearing
engine retrieves them for a time window through the EWDS gateway
(`measurements.query`) and writes them unchanged to a JSON file:

```bash
cd amm-clearing-node
uv run python -m src.fetch_measurements --start 2026-06-01T00:00:00Z \
  --end 2026-09-01T00:00:00Z --community <community-uuid> \
  --out ../amm-calibration/history.json
```

| Argument           | Meaning                                                           |
| ------------------ | ----------------------------------------------------------------- |
| `--start`, `--end` | Time window, as Unix seconds or ISO-8601 (required)               |
| `--community`      | Only records of this community                                    |
| `--facility`       | Only records of this facility                                     |
| `--gateway-url`    | Gateway URL; overrides `EWDS_GATEWAY_URL`                         |
| `--out`            | Output file; default `measurements.json` in the working directory |

The fetch step always uses the EWDS gateway, with the gateway settings of the
[configuration](../reference/configuration.md#environment-variables)
(`EWDS_*` variables).

The calibration tool uses the fields `communityUuid`, `timeSlot` and
`energyKwh` of each record. By default, a positive `energyKwh` is net
consumption (demand) and a negative one net injection (supply). For each slot,
the tool sums demand and supply over all records of the community, so the
objective only ever sees per-slot aggregates.

## Usage

```bash
cd amm-calibration
uv run python -m src.calibrate --measurements history.json \
  --community <community-uuid> --k-upper 28.5 --k-lower 8.0 --alpha 0.5 \
  --pool-id <pool-label> --pool-actor-uuid <pool-actor-uuid> --out params.yaml
```

| Argument                         | Meaning                                                   |
| -------------------------------- | --------------------------------------------------------- |
| `--measurements`                 | JSON list of measurement records (required)               |
| `--community`                    | Only use records of this community                        |
| `--k-upper`, `--k-lower`         | Price band in ct/kWh (required)                           |
| `--alpha`                        | Weight of the range term; default 0.5                     |
| `--pool-id`, `--pool-actor-uuid` | Copied into the configuration snippet                     |
| `--injection-positive`           | Treat positive energy as injection instead of consumption |
| `--out`                          | Write the configuration snippet to this YAML file         |

## Output

The tool reports the calibrated `theta` and `steepness`, the value of the
objective it minimises (Eq. (6) with the opposite sign) and the number of
slots used. It renders a `communities` entry for
`amm-clearing-node/configuration.yaml` with the band and the calibrated
parameters, and writes it to the file named with `--out` (otherwise to
standard output). The entry is keyed by `--community`; without it, the key is
the placeholder `<community_uuid>`. The clearing engine requires `pool_id` and
`pool_actor_uuid` for every community, so pass `--pool-id` and
`--pool-actor-uuid`, or add them before merging the entry.

## In the governance cycle

Running the tool for several values of $\alpha$ supports the assessment step
of the [parameter cycle](../model/governance.md#process): it shows how the
calibrated parameters, and therefore prices and the split of the gains from
trade, change with the community's normative choice.
