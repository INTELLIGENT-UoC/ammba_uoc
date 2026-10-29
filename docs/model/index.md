# Market mechanism

This section documents the AMMBA market mechanism as the software in this
repository implements it. It follows the notation of Saber et al. (2026), which
introduces the mechanism, proves its incentive properties and evaluates it in
simulation; see the [publications](../reference/bibliography.md#ammba-publications).

## Trading cycle

Members of an energy community trade energy in a sequence of market cycles,
one per delivery slot of typically 15 minutes. Before each cycle, the energy
management system of every member schedules the household's assets, such as a
PV system, a home battery or an electric vehicle, and determines its net
position for the slot. Members with a deficit participate as buyers, members
with a surplus as sellers. Only the net position reaches the market.

On the GSY DEX, participants submit orders that state energy quantities:
sellers offer their expected surplus and buyers state their demand, both in
kWh. When the order window of a slot closes, the clearing engine collects the
orders of the slot in one batch and

1. computes one uniform clearing price from the ratio of total supply to total
   demand,
2. allocates the traded energy pro rata through the AMMBA pool, and
3. records the resulting trades; payments follow from the allocation at the
   uniform price.

The pool exists only for the duration of one cycle. Unlike the reserves of a
conventional automated market maker, nothing is carried over to the next cycle.

## Reading order

1. [Market design and positioning](../background/market-design.md): how AMMBA
   relates to order books, other local market designs and DeFi market makers.
2. [Pricing function](pricing.md): how the clearing price follows from the
   supply-to-demand ratio.
3. [Allocation and gains from trade](allocation.md): who trades how much, why
   the pool is budget-balanced, and how the price splits the gains from local
   trade, with a worked example.
4. [Parameter calibration](calibration.md): how the shape of the pricing
   function is fitted to a community's own data.
5. [Parameter governance](governance.md): who decides the parameters, through
   which process, and under which principles.
6. [Incentives and penalties](incentives.md): how penalties make truthful
   reporting a dominant strategy.
7. [Preferences and differential pricing](extensions.md): the two optional
   extensions implemented in the clearing engine.

The [evaluation](evaluation.md) reports the simulation results, and the
[notation](notation.md) page lists all symbols.

## Assumptions

- Participants are price takers. Orders state quantities; limit prices are not
  used for pricing.
- Each participant can always fall back on the grid, buying at the retail price
  and exporting at the feed-in tariff.
- Network charges and taxes on local exchange are reflected in the choice of
  the price band.
- The clearing does not model the distribution network.
