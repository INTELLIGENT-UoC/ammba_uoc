# Glossary

| Term                                | Definition                                                                                                                               |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **AMM (automated market maker)**    | A market mechanism that sets prices with a deterministic pricing function of its state instead of matching orders in an order book.      |
| **AMMBA**                           | Automated Market Maker for Batch Auctions; the mechanism documented here.                                                                |
| **Batch auction**                   | A periodic auction in which all orders of a period are cleared together at one price.                                                    |
| **Clearing**                        | Determining the price and the allocation of a market slot.                                                                               |
| **Clearing price**                  | The uniform price $p_t$ at which all trades of a slot are executed.                                                                      |
| **Client Gateway**                  | The component through which applications publish and read messages on the Energy Web Digital Spine.                                      |
| **Community manager**               | The person or organisation that operates an energy community's market on its behalf; maintains the price band and runs the calibration.  |
| **Differential pricing**            | The optional scheme that pays green sellers a subsidy funded by a levy on grey sellers.                                                  |
| **EWDS (Energy Web Digital Spine)** | The data exchange layer of the INTELLIGENT platform, used by the GSY DEX components to reach the off-chain storage.                      |
| **Feed-in remuneration ($K_l$)**    | What the grid pays for exported energy; the lower end of the price band.                                                                 |
| **GSY DEX**                         | The Grid Singularity Decentralised Energy Exchange, the exchange platform of INTELLIGENT.                                                |
| **Match**                           | A pairing of a bid with an offer, submitted for on-chain settlement.                                                                     |
| **Off-chain storage**               | The GSY DEX component that stores orders, markets, measurements, trades and clearing results.                                            |
| **Ontology (INTELLIGENT)**          | The common data model of the project, which defines the objects exchanged by all platform components.                                    |
| **Pool**                            | The virtual counterparty of AMMBA, which buys from all sellers and sells to all buyers of a slot at the clearing price.                  |
| **Price band**                      | The interval between the feed-in remuneration and the retail price, within which the clearing price always lies.                         |
| **Pro rata**                        | Allocation in proportion to submitted quantities.                                                                                        |
| **Prosumer**                        | A participant who both consumes and produces energy.                                                                                     |
| **Retail price ($K_u$)**            | What a supplier charges for energy; the upper end of the price band.                                                                     |
| **Settlement**                      | The on-chain finalisation of matches, after which the off-chain storage records the resulting trades.                                    |
| **Time slot**                       | A delivery period, typically 15 minutes, for which one market is cleared.                                                                |
| **VCG (Vickrey–Clarke–Groves)**     | A family of mechanisms that charge participants for the harm their reports impose on others; the basis of AMMBA's externality penalties. |
