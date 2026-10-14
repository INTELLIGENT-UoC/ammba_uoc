# AMMBA: Automated Market Maker for Batch Auctions

AMMBA is a market mechanism for local energy communities. The orders of a
delivery slot are collected in a batch and cleared together against a
community pool at one uniform price. The price is a sigmoid function of the
ratio between local supply and demand, and it always lies between the feed-in
tariff and the retail price: the two alternatives every participant has outside
the community.

AMMBA is an alternative matching mechanism for the Grid Singularity
Decentralised Energy Exchange (GSY DEX). It exchanges data in the INTELLIGENT
ontology, so a community can use it instead of the exchange's order-book
mechanisms without changing the data its members submit. The mechanism and its
evaluation are published in [Saber et al. (2026)](reference/bibliography.md#ammba-publications).

## Key properties

- **One price per slot.** All participants in a slot trade at the same price,
  which anyone can recompute from two aggregate quantities and the published
  parameters.
- **Never worse than the grid.** The price stays inside the band set by the
  retail price and the feed-in tariff, so every traded kWh is at least as good
  for each participant as the grid alternative.
- **Budget-balanced pool.** The pool pays sellers exactly what it collects from
  buyers. It needs no subsidy, no liquidity providers and no operator margin.
- **Maximal local matching.** Every slot clears the largest feasible local
  volume; the longer side of the market is served pro rata.
- **Truthful reporting.** Ex-post penalties make reporting true demand and
  supply a dominant strategy for every participant.
- **Community-governed distribution.** The pricing parameters decide how the
  gains from local trade are split between buyers and sellers, and the
  community decides them through a transparent process.

In a simulation study with 1,000 households, AMMBA achieved about 20% higher
community self-consumption and welfare than a continuous double auction and a
uniform-price auction; see the [evaluation](model/evaluation.md).

## Status

The clearing engine, the calibration tool and local operation for a single
community are complete and tested. The clearing engine reads market data from
the GSY DEX through the Energy Web Digital Spine (EWDS) and can clear markets
autonomously. Settlement of AMM matches on the GSY DEX is in development. Work
in progress is tracked in the
[issue tracker](https://github.com/INTELLIGENT-UoC/ammba_uoc/issues).

## How these docs are organised

| Section                                          | What you find there                                                     |
| ------------------------------------------------ | ----------------------------------------------------------------------- |
| [Getting started](getting-started/quickstart.md) | Run AMMBA locally, operate it for one community                         |
| [Market mechanism](model/index.md)               | Positioning, pricing, allocation, calibration, governance, incentives   |
| [Evaluation](model/evaluation.md)                | Simulation results against a double auction and a uniform-price auction |
| [Implementation](implementation/architecture.md) | Components, clearing engine, calibration tool, settlement engine        |
| [Integration](integration/index.md)              | Integration with the GSY DEX and EWDS, data model, identifiers          |
| [Reference](reference/configuration.md)          | Configuration, interfaces, notation, glossary, publications             |

## Citing AMMBA

If you use AMMBA in academic work, please cite the publication and, where
relevant, the software release:

- H. Saber, T. Celig, S. Talari, W. Ketter, D. Schoder. An incentivized
  automated market maker-based batch auction mechanism for network-aware local
  energy markets with loss allocation. _Applied Energy_, 416, 127957, 2026.
  <https://doi.org/10.1016/j.apenergy.2026.127957>
- The software release, described in
  [`CITATION.cff`](https://github.com/INTELLIGENT-UoC/ammba_uoc/blob/main/CITATION.cff).

## Licence and funding

AMMBA is free software, published under the GNU General Public License v3.0 or
later (GPL-3.0-or-later). It is developed by the University of Cologne in the
Horizon Europe project [INTELLIGENT](https://intelligent-project.eu/), which has
received funding from the European Union's Horizon Europe research and
innovation programme under Grant Agreement No. 101160678.
