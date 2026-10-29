# Integration with the GSY DEX

AMMBA is integrated into the INTELLIGENT platform as an alternative matching
mechanism of the GSY Decentralised Energy Exchange (GSY DEX), alongside the
exchange's order-book mechanisms.

![AMMBA in the INTELLIGENT architecture](../assets/figures/context.png)

_Simplified view: participants' orders reach the GSY DEX off-chain storage,
matching mechanisms access it through the Energy Web Digital Spine (EWDS), and
matches are settled on-chain. The community selects the mechanism per market._

## Principles

- **Interchangeability through the ontology.** AMMBA consumes and produces the
  same ontology objects as the other mechanisms: orders as input, trades and
  clearing results as output. A community can therefore change its mechanism
  without changing the data that participants submit. See the
  [data model](data-model.md).
- **Data exchange through EWDS.** AMMBA reads market data through the EWDS
  gateway of the GSY DEX. See the [EWDS transport](ewds.md).
- **Settlement through the GSY DEX.** AMMBA's matches are settled through the
  exchange's on-chain settlement layer, so all mechanisms share one verifiable
  settlement path. See the
  [settlement engine](../implementation/settlement-engine.md).

## Current support

| Capability                                                                              | Status         |
| --------------------------------------------------------------------------------------- | -------------- |
| Orders in, trades and clearing results out in the ontology                              | Supported      |
| Reading orders and markets for clearing, and measurements for calibration, through EWDS | Supported      |
| Discovery of closed AMM markets and self-triggered clearing                             | Supported      |
| Settlement of AMM matches through the GSY DEX settlement layer                          | In development |

The [settlement engine](../implementation/settlement-engine.md#known-limitations)
page lists the known limitations of on-chain settlement.
