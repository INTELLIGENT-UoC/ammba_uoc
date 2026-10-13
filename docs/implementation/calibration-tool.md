# Calibration tool

The calibration tool (`amm-calibration`) implements the
[parameter calibration](../model/calibration.md) as an offline job. A community
manager can run it on the community's own infrastructure; it needs only the
Python standard library and a YAML parser.

## Usage

```bash
cd amm-calibration
uv run python -m src.calibrate --measurements history.json \
  --community <community-uuid> --k-upper 28.5 --k-lower 8.0 \
  --alpha 0.5 --out params.yaml
```

| Argument                         | Meaning                                                   |
| -------------------------------- | --------------------------------------------------------- |
| `--measurements`                 | JSON list of measurement records (required)               |
| `--community`                    | Only use records of this community                        |
| `--k-upper`, `--k-lower`         | Price band in ct/kWh (required)                           |
| `--alpha`                        | Weight of the range-usage term; default 0.5               |
| `--pool-id`, `--pool-actor-uuid` | Copied into the configuration snippet                     |
| `--injection-positive`           | Treat positive energy as injection instead of consumption |
| `--out`                          | Write the configuration snippet to this YAML file         |

## Input

The input is a list of measurement records in the measurement format of the
INTELLIGENT ontology. The tool uses the fields `facilityId`, `communityUuid`,
`timeSlot` and `energyKwh`. By default, a positive `energyKwh` is net
consumption (demand) and a negative one net injection (supply). For each slot,
the tool sums demand and supply over all facilities of the community, so the
objective only ever sees per-slot aggregates.

In a connected deployment, the clearing engine's measurement fetcher retrieves
such a history through the EWDS gateway:

```bash
cd amm-clearing-node
uv run python -m src.fetch_measurements --start 2026-06-01T00:00:00Z \
  --end 2026-09-01T00:00:00Z --community <community-uuid> --out history.json
```

## Output

The tool reports the calibrated `theta` and `steepness`, the objective value
and the number of slots used. It renders a `communities` entry for
`amm-clearing-node/configuration.yaml` containing the band, the calibrated
parameters and, if given, the pool identity, and writes it to the file named
with `--out`.

## In the governance cycle

Running the tool for several values of $\alpha$ supports the assessment step
of the [parameter cycle](../model/governance.md#process): it shows how the
calibrated parameters, and therefore prices and the split of the gains from
trade, change with the community's normative choice.
