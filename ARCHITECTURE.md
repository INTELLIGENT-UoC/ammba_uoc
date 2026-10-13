# Architecture

This file is the one-page architecture overview of AMMBA. The detailed,
maintained documentation lives in [`docs/`](docs/index.md); this page links to
it section by section.

## System in one paragraph

AMMBA clears local energy markets in periodic batches. For each delivery slot,
the clearing engine reads the community's bids and offers, computes one uniform
price from the ratio of supply to demand with a bounded sigmoid, allocates the
traded volume pro rata, and writes trades and a clearing result back in the
INTELLIGENT ontology format. Participants trade with a virtual pool, except
mutual preferred partners, who trade directly. The pricing parameters are
calibrated offline from the community's metering history. In the integrated
platform, the clearing engine reads market data through the Energy Web Digital
Spine (EWDS), and a settlement engine turns AMM trades into on-chain matches for
the GSY DEX settlement layer.

## Components

| Component            | Role                                                 | Documentation                                                  |
| -------------------- | ---------------------------------------------------- | -------------------------------------------------------------- |
| `amm-clearing-node`  | Clearing engine, scheduler, REST and EWDS transports | [Clearing engine](docs/implementation/clearing-engine.md)      |
| `amm-calibration`    | Offline calibration of the pricing parameters        | [Calibration tool](docs/implementation/calibration-tool.md)    |
| `amm-execution-node` | Settlement engine (version 2) and penalty formulas   | [Settlement engine](docs/implementation/settlement-engine.md)  |
| `amm-smart-contract` | Optional on-chain audit anchor                       | [Audit anchor contract](docs/implementation/smart-contract.md) |

## Data flow

```text
orders (int:Order) ──► clearing engine ──► trades (int:Trade) + clearing result (int:ClearingResult)
                         ▲          │
   parameters θ, β ──────┘          └──► (version 2) settlement engine ──► on-chain matches
   from the calibration tool
```

The transport between the clearing engine and the off-chain store is either
direct REST or the EWDS gateway; both expose the same interface to the
pipeline. See [EWDS transport](docs/integration/ewds.md).

## Where the details are

| Topic                                        | Page                                                                                                       |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Pricing function and its properties          | [docs/model/pricing.md](docs/model/pricing.md)                                                             |
| Allocation, budget balance, gains from trade | [docs/model/allocation.md](docs/model/allocation.md)                                                       |
| Calibration objective and method             | [docs/model/calibration.md](docs/model/calibration.md)                                                     |
| Parameter governance                         | [docs/model/governance.md](docs/model/governance.md)                                                       |
| Penalties                                    | [docs/model/incentives.md](docs/model/incentives.md)                                                       |
| Preferences and differential pricing         | [docs/model/extensions.md](docs/model/extensions.md)                                                       |
| Design principles and repository layout      | [docs/implementation/architecture.md](docs/implementation/architecture.md)                                 |
| Wire objects, units and identifiers          | [docs/integration/data-model.md](docs/integration/data-model.md)                                           |
| Configuration and environment variables      | [docs/reference/configuration.md](docs/reference/configuration.md)                                         |
| HTTP API, tools and simulator                | [docs/reference/interfaces.md](docs/reference/interfaces.md)                                               |
| Decision log                                 | [docs/reference/decisions.md](docs/reference/decisions.md)                                                 |
| Glossary and notation                        | [docs/reference/glossary.md](docs/reference/glossary.md), [docs/model/notation.md](docs/model/notation.md) |

Open work items are tracked as
[issues](https://github.com/INTELLIGENT-UoC/ammba_uoc/issues), grouped by
milestone; see the [roadmap](docs/project/roadmap.md).
