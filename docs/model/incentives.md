# Incentives and penalties

## Deviations

Two kinds of deviation can undermine the mechanism:

- **Delivery shortfalls.** Trading takes place before delivery, so a seller may
  deliver less than it sold, for example because its generation forecast was
  too optimistic.
- **Strategic misreporting.** Because the price depends on the
  supply-to-demand ratio, participants can try to move it by misreporting
  quantities. A seller can raise the price by withholding part of its
  available surplus, and a buyer can lower it by under-reporting its demand.

Manipulation through limit prices is not possible, because AMMBA does not use
limit prices for pricing.

## Penalties

AMMBA addresses both kinds of deviation with ex-post penalties, computed after
delivery from metered data.

**Shortfall penalty.** A seller $i$ that delivers $A_{i,t} < x_{i,t}$ pays

$$
\Phi_{i,t} = \gamma \, K_{u,t} \cdot \max\big(0,\; x_{i,t} - A_{i,t} - \eta\big) \tag{9}
$$

with $\gamma > 1$, so that a shortfall costs more than replacement energy at
the retail price, and a tolerance $\eta$ for small deviations.

**Externality penalties.** In a supply-limited slot ($Q_t = S_t$), a seller
that withholds $W_{i,t} > 0$ of its available surplus pays the price increase it
causes on the whole traded volume, where $p(S, D)$ denotes Eq. (1) evaluated at
the ratio $S/D$:

$$
E^{s}_{i,t} = \max\big(0,\; p_t - p(S_t + W_{i,t}, D_t)\big) \cdot Q_t \tag{10}
$$

Symmetrically, in a demand-limited slot ($Q_t = D_t$), a buyer that
under-reports its demand by $W_{j,t} > 0$ pays

$$
E^{b}_{j,t} = \max\big(0,\; p(S_t, D_t + W_{j,t}) - p_t\big) \cdot Q_t \tag{11}
$$

The externality penalties follow the logic of Vickrey–Clarke–Groves mechanisms
(Vickrey, 1961; Clarke, 1971; Groves, 1973): a participant is charged for the
harm its report imposes on the other participants, measured against the
counterfactual in which it reported truthfully. The formal incentive properties
are analysed in the companion publication.

## Status

The penalty mechanism is specified and evaluated in simulation. Its formulas
are implemented in `amm-execution-node/src/penalties.py` and covered by tests,
but they are not yet connected to an operational data flow: computing penalties
requires metered delivery data and a settlement path. The execution engine of
the GSY DEX provides a penalty submission interface on-chain, which is the
planned path; see the [settlement engine](../implementation/settlement-engine.md)
and the [roadmap](../project/roadmap.md).
