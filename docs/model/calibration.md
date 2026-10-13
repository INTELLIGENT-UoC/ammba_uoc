# Parameter calibration

## Parameter groups

The parameters of the pricing function fall into three groups:

- The **band** $(K_{u,t}, K_{l,t})$ is given by the tariffs the community
  faces.
- The **shape** $(\theta, \beta)$ determines the split of the gains from trade
  and the strength of the scarcity signal. It is calibrated from the
  community's historical data.
- The **weight** $\alpha$ expresses a normative choice between these two goals
  and is set by the community; see [parameter governance](governance.md).

## Objective

Calibration chooses $(\theta, \beta)$ to maximise

$$
J(\theta, \beta) = F(\theta, \beta) - \alpha \, R(\theta, \beta) \tag{6}
$$

with a fairness term and a range-usage term:

$$
F(\theta, \beta) = \frac{1}{N} \sum_{t \in T'} \min\big(K_{u,t} - p_t,\; p_t - K_{l,t}\big) \tag{7}
$$

$$
R(\theta, \beta) = \max\big(0,\; p(r_{\max}) - K_{l,\min}\big) + \max\big(0,\; K_{u,\min} - p(r_{\min})\big) \tag{8}
$$

Here $T'$ contains the $N$ historical slots with positive supply and demand,
$p_t$ is the price that Eq. (1) assigns to slot $t$, $r_{\max}$ and $r_{\min}$
are the largest and smallest observed ratios, and $K_{u,\min}$ and $K_{l,\min}$
denote the band of the slot with the smallest ratio.

**Fairness term.** For each slot, $F$ measures the per-kWh gain of the
worse-off side of the market, buyers or sellers, and averages it over time. It
is a max-min fairness criterion between the two sides. Taken alone, it is
maximised by the flat price $\beta = 0$, which splits the gains of every slot
evenly but carries no information about scarcity.

**Range-usage term.** $R$ counteracts this tendency. It penalises curves that
fail to approach the feed-in remuneration at the most abundant slot and the
retail price at the scarcest slot, and so ensures that the calibrated price
uses the full band and conveys scarcity. The weight $\alpha$ governs the
trade-off between the two goals.

## Data requirements

The objective depends only on the per-slot aggregates $S_t$ and $D_t$ and on
the band. These aggregates are derived from the community's metering data:
the [calibration tool](../implementation/calibration-tool.md) converts
per-slot measurement records into demand and supply under a configurable sign
convention and sums them per slot. Individual measurement data is needed only
for this aggregation, which can take place within the community's own
infrastructure.

## Solution method

The parameters are searched in the box $\theta, \beta \in [0, 50]$. Because the
min and max operators make the objective non-smooth, the calibration tool uses
a deterministic coarse-to-fine grid search: a full 51 × 51 grid, followed by a
refined 41 × 41 grid around the best point. This avoids the difficulties of
gradient-based methods at the non-smooth points and gives reproducible results
without external numerical libraries. The research code of the companion
publication applies a bounded quasi-Newton optimiser to the same objective.

The objective uses the pricing function without the operational clamping, so
that the range-usage term remains informative near the limits of the band.

Calibrated parameters are specific to a community. They depend on its mix of
consumers and prosumers and on its generation profile, which is why the
[evaluation](evaluation.md) calibrates separate parameters for each scenario.
