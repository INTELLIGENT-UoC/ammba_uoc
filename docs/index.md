# AMMBA: Automated Market Maker for Batch Auctions

AMMBA is a market mechanism for local energy communities. Participants submit
the quantities of energy they want to buy or sell in a delivery slot. When the
slot closes, all orders are cleared together against a community pool at a
single price. The price is a sigmoid function of the ratio between offered and
requested energy, and it always lies between the feed-in remuneration and the
retail price: the two alternatives every participant has outside the community.

AMMBA is developed by the University of Cologne in Task 5.4 of the Horizon
Europe project [INTELLIGENT](https://intelligent-project.eu/) (Grant Agreement
No. 101160678). It is an alternative matching mechanism for the Grid
Singularity Decentralised Energy Exchange (GSY DEX) and exchanges data in the
INTELLIGENT ontology, so a community can use it instead of the exchange's
order-book mechanisms without changing the data its members submit.

> **Status.** The clearing engine, the calibration tool and local single-community
> operation are complete. Reading orders, markets and measurements through the
> Energy Web Digital Spine (EWDS) and autonomous market clearing have been
> validated against the project staging environment. On-chain settlement of
> AMM matches is in development as part of version 2. See the
> [roadmap](project/roadmap.md).

## Key properties

- **One price per slot.** All participants in a slot trade at the same price,
  which anyone can recompute from two aggregate quantities and the published
  parameters.
- **Never worse than the grid.** The price stays inside the band set by the
  retail price and the feed-in remuneration, so every traded kWh is at least as
  good for each participant as the grid alternative.
- **Budget-balanced pool.** The pool pays sellers exactly what it collects from
  buyers. It needs no subsidy, no liquidity providers and no operator margin.
- **Maximal local matching.** Every slot clears the smaller of total supply and
  total demand; the longer side of the market is served pro rata.
- **Community-governed distribution.** The pricing parameters decide how the
  gains from local trade are split between buyers and sellers, and the
  community decides them through a transparent process.

## How these docs are organised

| Section                                          | What you find there                                                  |
| ------------------------------------------------ | -------------------------------------------------------------------- |
| [Getting started](getting-started/quickstart.md) | Run AMMBA locally, operate it for one community                      |
| [Background](background/market-design.md)        | How AMMBA relates to other local energy market designs               |
| [Market model](model/index.md)                   | The theory: pricing, allocation, calibration, governance, incentives |
| [Implementation](implementation/architecture.md) | Components, clearing engine, calibration tool, settlement engine     |
| [Integration](integration/index.md)              | Integration with the GSY DEX and EWDS, data model, identifiers       |
| [Reference](reference/configuration.md)          | Configuration, interfaces, decision log, glossary, bibliography      |
| [Project](project/deliverable.md)                | Relation to the INTELLIGENT deliverable, roadmap, contributing       |

These pages form the documentation part of the T5.4 deliverable of
INTELLIGENT, which pairs a written report with this open-source repository.
The [deliverable mapping](project/deliverable.md) shows which page documents
which part of the report.

## Licence

AMMBA is free software, published under the GNU General Public License v3.0 or
later (GPL-3.0-or-later). The project has received funding from the European
Union's Horizon Europe research and innovation programme under Grant Agreement
No. 101160678.
