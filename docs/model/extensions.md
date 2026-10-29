# Preferences and differential pricing

The clearing engine implements two extensions of the base model. Both are
opt-in and leave the base model unchanged when unused. This page documents the
implemented behaviour; a formal treatment and evaluation are planned.

## Preferred trading partners

A buyer and a seller can each name preferred trading partners. On the
exchange this is the `preferredTradingPartner` field of an order.

1. After the [pro-rata allocation](allocation.md#pro-rata-allocation), the engine
   searches for **mutual** pairs: a bid that names the seller and an offer that
   names the buyer.
2. Each mutual pair trades directly with each other, at the uniform clearing
   price, up to the smaller of their two pro-rata allocations.
3. The direct volume is deducted from both partners' pool allocations; the
   remainder clears against the pool as usual.

Preference matching therefore changes _with whom_ a participant trades, not
_how much_ or _at what price_. Each participant's total allocation and price
are exactly those of the base model, so all [properties](allocation.md#properties)
continue to hold. One-sided preferences have no effect.

The energy-source preference of a bid (`energySourcePreference`) is carried
through the data model but not used for clearing in the current version.

## Energy-type differential pricing

A community can reward green generation. The scheme is seller-side: buyers
always pay the uniform clearing price $\pi_t$, and only the prices of pool sales
by sellers are adjusted.

Offers with a remaining pool allocation are classified by their energy type:
green (`GREEN`, `PV`, `HYDRO`, `BIOMASS`, `BATTERY`), grey (`GREY`), or
neutral (no type). With community-set rates $g$ (green subsidy rate) and $l$
(grey levy rate), and a levy cap $c$ in ct/kWh:

- the levy per kWh is $\ell_t = \min(l \, \pi_t,\; c)$, and grey sellers receive
  $\pi_t - \ell_t$;
- the target subsidy per kWh is $g \, \pi_t$; if the total target subsidy exceeds
  the levy revenue $\ell_t \cdot V^{\mathrm{grey}}_t$, it is scaled down to that
  revenue, so the subsidy never exceeds the levy collected;
- green sellers receive $\pi_t$ plus the (possibly scaled) subsidy per kWh;
- neutral sellers, buyers and direct preference trades are unaffected.

The scheme needs both a funding and a funded side: if a slot has no green or
no grey pool sales, no adjustment is made. When the levy revenue exceeds the
subsidy paid, the difference remains with the pool and is reported as the
pool residual. The adjusted price is written directly into the price of the
affected pool–seller trades, and the clearing summary records the full
provenance: base price, subsidy, levy, scaling factor, volumes, and the
per-seller adjustments.

The scheme is disabled by default. It is enabled per community with
`green_subsidy_rate`, `grey_levy_rate` and `levy_cap_ct_per_kwh`; see the
[configuration reference](../reference/configuration.md#community-parameters).
Under [parameter governance](governance.md), these rates are normative
choices for the community members.
