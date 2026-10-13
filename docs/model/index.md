# Market model

This section documents the AMMBA market model. All formulas correspond to the
implementation in this repository; where the implementation deviates for
numerical reasons, the pages say so. The model is also the subject of a
companion publication, which will be referenced here once it is available.

## Reading order

1. [Pricing function](pricing.md): the market setting, the notation, and how
   the clearing price follows from the ratio of supply to demand.
2. [Allocation and gains from trade](allocation.md): who trades how much, why
   the pool is budget-balanced, and how the price splits the gains from local
   trade. Includes a fully worked example.
3. [Parameter calibration](calibration.md): how the shape of the pricing
   function is fitted to a community's own data.
4. [Parameter governance](governance.md): who decides the parameters, through
   which process, and under which principles.
5. [Incentives and penalties](incentives.md): how the mechanism handles
   delivery shortfalls and strategic misreporting of quantities.
6. [Preferences and differential pricing](extensions.md): the two extensions
   of the base model implemented in the clearing engine.
7. [Evaluation design](evaluation.md): how AMMBA is compared with an
   order-book market.

The [notation](notation.md) page lists all symbols.

## Assumptions of the current model

- Participants are price takers. Orders state quantities; limit prices are not
  used for pricing.
- Submitted quantities are inelastic within a slot.
- Each participant can always fall back on the grid: buying at the retail
  price and exporting at the feed-in remuneration.
- Network charges and taxes for local exchange are reflected in the choice of
  the price band.
- Network constraints are not modelled.
