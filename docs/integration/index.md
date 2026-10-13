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
- **Data exchange through EWDS.** Like the other GSY DEX engines, AMMBA reads
  market data through the EWDS gateway. See the [EWDS transport](ewds.md).
- **Settlement through the GSY DEX.** AMMBA's matches are settled through the
  exchange's on-chain settlement layer, so all mechanisms share one verifiable
  settlement path. See the
  [settlement engine](../implementation/settlement-engine.md).

## Integration stages

| Stage                   | Content                                                     | Status                               |
| ----------------------- | ----------------------------------------------------------- | ------------------------------------ |
| 1. Data contract        | Inputs and outputs aligned with the INTELLIGENT ontology    | Complete                             |
| 2. Read path            | Orders, markets and measurements read through EWDS          | Validated on the staging environment |
| 3. Autonomous operation | Discovery of closed AMM markets and self-triggered clearing | Validated on the staging environment |
| 4. On-chain settlement  | Pool representation, identifier mapping, settlement engine  | In development                       |
| 5. Pilot operation      | Configuration, calibration and operation at the pilot sites | Planned                              |

## Open design questions

- How the pool, which submits no orders of its own, is placed in the on-chain
  order registry in time; the registry accepts orders only while a market is
  open.
- How AMMBA's uniform price relates to the order-level price constraints that
  the settlement layer verifies, given that AMMBA does not use limit prices.
- Which party operates the AMMBA components at each pilot site.

The [roadmap](../project/roadmap.md) tracks these questions.
