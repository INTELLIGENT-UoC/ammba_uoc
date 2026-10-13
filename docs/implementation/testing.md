# Testing and verification

## Test suites

Every component has its own automated test suite.

| Component         | Command                                     | Covers                                                                                                                                                                                               |
| ----------------- | ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Clearing engine   | `cd amm-clearing-node && uv run pytest`     | Pricing function, allocation, preferences and differential pricing, trade generation, schema validation, transports with retry and back-off, scheduler, an end-to-end clearing against the simulator |
| Calibration tool  | `cd amm-calibration && uv run pytest`       | Objective, grid search, aggregation of measurements, sign convention                                                                                                                                 |
| Settlement engine | `cd amm-execution-node && uv run pytest`    | Identifier conventions, struct encoding, match building, pre-flight validation, engine pipeline against a mocked chain, penalty formulas                                                             |
| Audit anchor      | `cd amm-smart-contract && npx hardhat test` | Deployment, parameter registration, clearing records, access control, views                                                                                                                          |

Install the development dependencies of a Python component once with
`uv sync --extra dev`.

## Local end-to-end environment

The clearing engine ships a simulator of the off-chain store
(`amm-clearing-node/sim/`). It serves the same REST interface as the GSY DEX
off-chain storage, validates every object it receives against the ontology
schemas, and also emulates the EWDS gateway for the `ewds` transport. The
end-to-end test drives the real client against the simulator in-process, so
the clearing engine's wire compatibility is checked on every test run without
an external environment. The [quick start](../getting-started/quickstart.md)
runs the same pair of services with Docker.

## Continuous integration

Every pull request and every push to `main` runs continuous integration on
GitHub Actions. A first job detects which components changed; only their test
suites run, and a final job reports a single status for the whole pipeline.
The documentation is built with `mkdocs build --strict` whenever it changes, so
broken links and missing pages fail the build.

## Integration testing

Beyond the local environment, the read path through the EWDS gateway and the
autonomous discovery and clearing of markets have been validated against the
INTELLIGENT staging environment. These runs depend on project infrastructure
and are therefore not part of the automated suites.
