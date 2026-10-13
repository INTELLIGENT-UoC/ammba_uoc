# Market design and positioning

This page positions AMMBA among local energy market designs. It summarises the
distinctions needed to place AMMBA and classifies clearing mechanisms in a way
that frames the comparison between order-book-based systems and pool-based
automated market makers. For broader reviews of peer-to-peer and
community-based market designs, see Sousa et al. (2019) and Tushar et al.
(2020) in the [bibliography](../reference/bibliography.md).

## Local energy market designs

Local energy markets broadly follow one of two trading approaches:

- **Peer-to-peer trading.** Participants, or software agents acting for them,
  trade with each other, and prices can differ from one match to the next.
- **Peer-to-pool (peer-to-market) trading.** Participants trade with a
  community-level counterparty at a community price.

In current practice, peer-to-pool arrangements are often implemented as
collective self-consumption: local generation is aggregated and allocated to
members according to predetermined coefficients, and settled ex post, while
demand not covered locally is bought from the supplier and surplus is exported
at the feed-in tariff [GSY wiki, Market Types]. Such schemes share energy, but
they do not discover a price.

The GSY DEX, the decentralised exchange used in INTELLIGENT, separates the
matching of orders from their verification and settlement. Matching engines
read open orders from the exchange's off-chain storage and submit matches,
which are verified against the constraints of the underlying orders and
settled on-chain. Because verification does not depend on the internal logic
of a particular algorithm, several matching mechanisms can coexist and a
community can choose the one that suits it. The exchange implements a
two-sided pay-as-bid mechanism and foresees pay-as-clear and an automated
market maker as alternatives [GSY wiki, GSY DEX Matching Engine]. In
INTELLIGENT, pay-as-bid and pay-as-clear matching are complemented by the
AMM-based trading mechanism of Task 5.4 [INTELLIGENT D3.2].

AMMBA is a peer-to-pool mechanism, but not a coefficient-based sharing scheme.
Participants submit orders ex ante for every delivery slot, the pool price is
formed anew in each slot from the community's aggregate supply and demand, and
the price moves within the band set by the participants' outside options.
AMMBA therefore keeps the defining feature of an exchange, price discovery
driven by local scarcity, while clearing against a pool instead of matching
participants bilaterally. Within the GSY DEX, it is the AMM-based alternative
mechanism.

## Order books and liquidity-pool market makers

The call behind INTELLIGENT (HORIZON-CL5-2023-D3-03-05) asks projects to
explore and compare order-book-based systems and liquidity-pool-based
automated market makers. A meaningful comparison needs more than a binary
contrast, because the mechanisms differ along several independent dimensions:

- **Timing of matching.** In continuous mechanisms, each incoming order is
  matched immediately against the resting orders. In periodic (batch)
  mechanisms, all orders of a period are collected and cleared together. All
  designs considered here divide delivery into discrete slots, typically of 15
  minutes. "Continuous" and "discrete" refer to the matching within a slot,
  not to delivery: the GSY pay-as-bid market, for instance, is a continuous
  auction in which an order can be matched as soon as it is posted, before the
  end of the market slot [GSY wiki, Market Types].
- **Price formation.** Prices can be discriminatory, with each trade at the
  prices of the matched orders (pay-as-bid); uniform and derived from the
  order stack, where the aggregate bid and offer curves intersect
  (pay-as-clear); uniform and derived from a pricing function of the pool
  state (AMM); or administratively set (coefficient-based sharing).
- **Counterparty.** Participants are either matched with each other, as in an
  order book, or trade with a common pool.

| Mechanism                                     | Matching                           | Price formation                                                                 | Counterparty                            | Order content                               | Remarks                                                  |
| --------------------------------------------- | ---------------------------------- | ------------------------------------------------------------------------------- | --------------------------------------- | ------------------------------------------- | -------------------------------------------------------- |
| Two-sided pay-as-bid (GSY DEX)                | Continuous within each slot        | Discriminatory: prices of the matched orders                                    | Bilateral                               | Quantity and limit price                    | Partial matches; residual orders stay in the market      |
| Two-sided pay-as-clear                        | Periodic: cleared at set intervals | Uniform: intersection of bid and offer curves                                   | Bilateral, derived from the cleared set | Quantity and limit price                    | No trade if bids and offers do not cross                 |
| Coefficient-based sharing                     | Ex post                            | Administrative: tariff or allocation keys                                       | Pool                                    | None: metered quantities                    | No price discovery                                       |
| Constant-function AMM (decentralised finance) | Continuous: per swap               | Pricing function of the pool reserves                                           | Pool funded by liquidity providers      | Swap amount                                 | Needs pool inventory from liquidity providers            |
| **AMMBA**                                     | Periodic: one clearing per slot    | Uniform: pricing function of the supply-to-demand ratio, bounded by grid prices | Virtual pool without inventory          | Quantity; limit prices not used for pricing | Always clears min(S, D); residuals settled with the grid |

AMMBA combines two established ideas. From periodic auctions it takes the
uniform treatment of all orders of a period, which removes any advantage of
submitting earlier or faster within the period (Budish et al., 2015). From
automated market makers it takes a deterministic, publicly known pricing
function in place of price formation from the order stack (Angeris and Chitra,
2020). Unlike constant-function market makers in decentralised finance, the
AMMBA pool holds no inventory and needs no liquidity providers: the external
grid acts as the residual counterparty at the two ends of the price band, so
any imbalance between local supply and demand is absorbed at the feed-in or
retail price.

The comparison the call requests is operationalised in the
[evaluation](../model/evaluation.md), which benchmarks AMMBA against an
order-book market on the same data.

## Why a batch AMM for community energy

Local energy markets differ from the wholesale and financial markets that
order books were designed for. Communities are small, most participants are
households, and trading takes place in many short delivery slots. These
features motivate the design of AMMBA:

- **Thin markets.** With tens to a few hundred participants per community, an
  order book holds few resting orders per slot, which makes prices volatile
  and matching uncertain. AMMBA always matches the largest feasible local
  volume.
- **Low participation burden.** Households, or the energy management systems
  acting for them, state quantities only. Nobody has to form price bids for
  each of the 96 daily slots.
- **One understandable price.** All participants in a slot trade at the same
  price, which is easy to communicate and to verify.
- **No timing advantage.** Because all orders of a slot are cleared together,
  submitting earlier or faster within the slot confers no benefit.
- **Protection against unfavourable outcomes.** The price band guarantees that
  nobody pays more than the retail price or receives less than the feed-in
  remuneration for traded energy.
- **Community-governed distribution.** The pricing parameters determine how
  the gains from local trade are shared between buyers and sellers, and the
  community sets them through a [transparent process](../model/governance.md).

These advantages come with limitations that the design addresses explicitly.
Because the price depends only on quantities, participants could try to
influence it by misreporting quantities; [penalties](../model/incentives.md)
counter this. Participants cannot express a willingness to pay through limit
prices; [preferences](../model/extensions.md) for specific partners and energy
types partly restore this expressiveness. Network constraints are outside the
scope of the current model.
