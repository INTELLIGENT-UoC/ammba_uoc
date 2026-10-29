# Incentives and penalties

## Deviations

Two kinds of deviation can undermine the mechanism:

- **Delivery shortfalls.** Trading takes place before delivery, so a seller may
  deliver less than it sold, for example because its generation forecast was
  too optimistic.
- **Strategic misreporting.** Because the price depends on the
  supply-to-demand ratio, participants can try to move it by misreporting. A
  seller can raise the price by withholding part of its available surplus, and
  a buyer can lower it by under-reporting its demand.

Manipulation through limit prices is not possible, because AMMBA does not use
limit prices for pricing.

## Penalties

AMMBA addresses both kinds of deviation with ex-post penalties, computed after
delivery from metered data. Smart meters provide the metered demand
$D^{\mathrm{met}}_{t,i}$ of each buyer and the deliverable surplus $A_{t,j}$ of
each seller, and a deadband $\eta_t \ge 0$ absorbs small exogenous deviations.
A cycle is _supply-limited_ if all offered energy is sold ($Q_t = E_t$) and
_demand-limited_ if all stated demand is served ($Q_t = D_t$).

**Shortfall penalty.** A seller $j$ that sold more than it can deliver pays

$$
\Phi_{t,j} = \gamma \, K_{\mathrm{up},t} \cdot \max\big(0,\; s_{t,j} - A_{t,j} - \eta_t\big) \tag{7}
$$

with $\gamma > 1$, so that each undelivered kWh costs more than the highest
price the seller could have obtained for it.

**Seller externality penalty.** In a supply-limited cycle, a seller that
withholds $W^{\mathrm{sell}}_{t,j} = \max(0,\; A_{t,j} - s_{t,j} - \eta_t)$ of its
deliverable surplus pays the price increase that the withholding causes on the
whole traded volume:

$$
\varphi^{\mathrm{sell}}_{t,j} = \big(\pi_t - \pi^{\mathrm{cf,sell}}_{t,j}\big) \, Q_t,
\qquad \pi^{\mathrm{cf,sell}}_{t,j} = f\!\left( \frac{E_t + W^{\mathrm{sell}}_{t,j}}{D_t} \right) \tag{8}
$$

**Buyer externality penalty.** Symmetrically, in a demand-limited cycle, a
buyer whose stated demand falls short of its metered demand by
$W^{\mathrm{buy}}_{t,i} = \max(0,\; D^{\mathrm{met}}_{t,i} - D_{t,i})$ is
treated as if it had stated its full demand, and pays the price reduction that
its under-reporting caused:

$$
\varphi^{\mathrm{buy}}_{t,i} = \big(\pi^{\mathrm{cf,buy}}_{t,i} - \pi_t\big) \, Q_t,
\qquad \pi^{\mathrm{cf,buy}}_{t,i} = f\!\left( \frac{E_t}{D_t + W^{\mathrm{buy}}_{t,i}} \right) \tag{9}
$$

The externality penalties follow the logic of Vickrey–Clarke–Groves mechanisms
(Vickrey, 1961; Clarke, 1971; Groves, 1973): a participant is charged for the
harm its report imposes on the other participants, measured against the
counterfactual in which it reported truthfully.

## Incentive properties

For participants acting individually, Saber et al. (2026) prove the following
properties. Their formulation lets buyers fund their purchases instead of
stating quantities; the penalties above are its counterparts on the energy
ratio $E_t / D_t$ of this software.

- **Sellers.** Over-reporting the deliverable surplus is strictly
  unprofitable, because each undelivered kWh costs more than it can earn.
  Withholding surplus in a supply-limited cycle does not pay, because the
  penalty is at least as large as the gain from the higher price.
- **Buyers.** Over-reporting demand does not pay, because energy beyond the
  buyer's need is worth only the feed-in tariff to it. Under-reporting in a
  demand-limited cycle reduces the buyer's net payoff, because the penalty is
  at least as large as the saving from the lower price.
- **Dominant-strategy incentive compatibility.** As a consequence, truthful
  reporting is a dominant strategy for every participant: each buyer states
  its true metered demand, $D_{t,i} = D^{\mathrm{met}}_{t,i}$, and each seller
  offers its true deliverable surplus, $E_{t,j} = A_{t,j}$.

These guarantees cover individual deviations. Coordinated withholding by a
coalition of sellers is not covered, because the externality penalty is
computed per seller; coalition-proof extensions are an open research question.

## Implementation status

The penalty formulas of Eqs. (7) to (9) are implemented in
`amm-execution-node/src/penalties.py` and covered by tests. They are
not yet connected to an operational data flow: computing penalties requires
metered delivery data and a settlement path. The execution engine of the GSY
DEX provides a penalty submission interface on-chain, which is the planned
path; see the [settlement engine](../implementation/settlement-engine.md).
