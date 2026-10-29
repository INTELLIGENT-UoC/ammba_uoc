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
sides relative to their outside options. A buyer saves the difference between
the retail price and the clearing price on every kWh it buys locally, and a
seller earns the difference between the clearing price and the feed-in tariff
on every kWh it sells:

$$
U_t = K_{\mathrm{up},t} - \pi_t, \qquad P_t = \pi_t - K_{\mathrm{lo}} \tag{5}
$$

Because all participants of a slot trade at the uniform price, these returns
are the same for every buyer and for every seller of the slot. Together they
make up the gain per kWh of local trade,
$U_t + P_t = K_{\mathrm{up},t} - K_{\mathrm{lo}}$, which the price divides
between the two sides; see [gains from trade](allocation.md#gains-from-trade).

## Objective

Calibration chooses $(\Theta, B)$ to maximise the average return of the
worse-off side of the market over the $N$ historical slots with positive
supply and demand, while penalising price curves that do not span the band:

$$
\max_{\Theta, B} \; \frac{1}{N} \sum_{t=1}^{N} \min\left( U_t, P_t \right)
- \alpha \Big( \big(f(r_{\max}) - K_{\mathrm{lo}}\big) + \big(K_{\mathrm{up}} - f(r_{\min})\big) \Big) \tag{6}
$$

Here $U_t$ and $P_t$ depend on $(\Theta, B)$ through $\pi_t = f(r_t)$,
$r_{\max}$ and $r_{\min}$ are the largest and smallest ratios observed in the
data, and $K_{\mathrm{up}}$ in the range term is the retail price of the slot
with the smallest ratio; with a constant band, it is simply the retail price.

**Fairness term.** For each slot, the first term is the per-kWh return of the
worse-off side of the market, buyers or sellers. It is a max-min fairness
criterion between the two sides. Taken alone, it is maximised by the
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
on the band. They are derived from the community's metering history, the
`int:Measurement` records that the GSY DEX off-chain storage holds for the
community. The clearing node's fetch step (`src.fetch_measurements`) retrieves
these records over the EWDS and writes them to a snapshot file; the
[calibration tool](../implementation/calibration-tool.md) reads the snapshot,
converts each record into demand or supply under a configurable sign
convention and sums them per slot. The optimisation itself runs offline on the
snapshot, and only the per-slot aggregates enter the objective.

## Solution method

Saber et al. (2026) solve the calibration problem with the bounded
quasi-Newton method L-BFGS-B. The calibration tool evaluates Eq. (6) with a
constant band and searches $\Theta, B \in [0, 50]$ with a deterministic
coarse-to-fine grid search: a full 51 × 51 grid, followed by a refined
41 × 41 grid around the best point. Because the min operator makes the objective non-smooth, the grid
search avoids the difficulties of gradient-based methods at the non-smooth
points and gives reproducible results without external numerical libraries.
The objective uses the pricing function without the operational clamping, as
the reference implementation does; since the function never leaves the band,
the clamp would not change the result.

Calibrated parameters are specific to a community. They depend on the
community's mix of consumers and prosumers and on its generation profile,
which is why the [evaluation](evaluation.md#calibrated-parameters) calibrates
separate parameters for each scenario. The calibration can be
repeated weekly, monthly or seasonally, as the community decides.
