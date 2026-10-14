# Parameter calibration

## Parameter groups

The parameters of the pricing function fall into three groups:

- The **band** $(K_{\mathrm{up},t}, K_{\mathrm{lo}})$ is given by the tariffs
  the community faces.
- The **shape** $(\Theta, B)$ determines the split of the gains from trade and
  the strength of the scarcity signal. It is calibrated from the community's
  historical data.
- The **weight** $\alpha$ expresses a normative choice between these two goals
  and is set by the community; see [parameter governance](governance.md).

## Returns of buyers and sellers

Calibration measures the outcome of a slot by the per-kWh returns of both
sides relative to their outside options. The utility of buyer $i$ is its
saving per kWh received compared with the retail price, reduced by the loss on
any energy received beyond its demand, which is sold back at the feed-in
tariff. The profit of seller $j$ is its revenue per kWh sold above the feed-in
tariff:

$$
U_{t,i} = \frac{q_{t,i} (K_{\mathrm{up},t} - \pi_t) - \max(0,\; q_{t,i} - D_{t,i}) (\pi_t - K_{\mathrm{lo}})}{q_{t,i}},
\qquad P_{t,j} = \pi_t - K_{\mathrm{lo}} \tag{7}
$$

## Objective

Calibration chooses $(\Theta, B)$ to maximise the return of the worse-off side
of the market, summed over the historical slots, while penalising price curves
that do not span the band:

$$
\max_{\Theta, B} \sum_t \left[ \min\left( \frac{U_t}{I_t}, \frac{P_t}{J_t} \right)
- \alpha \big( f(r_{\max}) - K_{\mathrm{lo}} + K_{\mathrm{up},t} - f(r_{\min}) \big) \right] \tag{8}
$$

Here $U_t$ and $P_t$ are the sums of the per-kWh returns of the $I_t$ buyers
and $J_t$ sellers of slot $t$, so that the first term compares their average
returns, and $r_{\max}$ and $r_{\min}$ are the largest and smallest ratios
observed in the data.

**Fairness term.** For each slot, the first term is the average per-kWh return
of the worse-off side of the market, buyers or sellers. It is a max-min
fairness criterion between the two sides. Taken alone, it is maximised by the
flat price $B = 0$, which splits the gains of every slot evenly but carries no
information about scarcity.

**Range term.** The second term penalises curves that fail to approach the
feed-in tariff at the most abundant slot and the retail price at the scarcest
slot. It thereby ensures that the calibrated price uses the full band and
conveys scarcity. The weight $\alpha$ governs the trade-off: a lower $\alpha$
yields flatter curves and more stable prices, a higher $\alpha$ more responsive
prices.

## Data requirements

The objective depends only on the per-slot aggregates of supply and demand and
on the band. These aggregates are derived from the community's metering data:
the [calibration tool](../implementation/calibration-tool.md) converts
per-slot measurement records into demand and supply under a configurable sign
convention and sums them per slot. Individual measurement data is needed only
for this aggregation, which can take place within the community's own
infrastructure.

## Solution method

The publication solves Eq. (8) with the bounded quasi-Newton method L-BFGS-B.
The calibration tool evaluates the same objective in the order-based form, with
a constant band and normalised by the number of slots. With truthful reporting,
no buyer receives more than its demand, so the fairness term reduces to the
mean of $\min(K_{\mathrm{up}} - \pi_t,\; \pi_t - K_{\mathrm{lo}})$ over the
slots with positive supply and demand.

The tool searches $\Theta, B \in [0, 50]$ with a deterministic coarse-to-fine
grid search: a full 51 × 51 grid, followed by a refined 41 × 41 grid around the
best point. Because the min operator makes the objective non-smooth, the grid
search avoids the difficulties of gradient-based methods at the non-smooth
points and gives reproducible results without external numerical libraries.
The objective uses the pricing function without the operational clamping, so
that the range term remains informative near the limits of the band.

Calibrated parameters are specific to a community and to the form of the
ratio. They depend on the community's mix of consumers and prosumers and on
its generation profile, which is why the [evaluation](evaluation.md#calibrated-parameters)
calibrates separate parameters for each scenario. The calibration can be
repeated weekly, monthly or seasonally, as the community decides.
