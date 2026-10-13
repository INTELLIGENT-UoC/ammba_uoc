# Pricing function

## Market setting

An energy community trades energy in a sequence of delivery slots $t \in T$ of
fixed length, typically 15 minutes (96 slots per day). For each slot, a market
opens and closes before delivery. During the market window, each buyer $j$
submits a bid for a quantity $d_{j,t} > 0$ and each seller $i$ submits an offer
for a quantity $s_{i,t} > 0$, both in kWh. The aggregate demand and supply of
the slot are

$$
D_t = \sum_j d_{j,t}, \qquad S_t = \sum_i s_{i,t}.
$$

Every participant has an outside option: buying from its supplier at the
retail price $K_{u,t}$, or exporting to the grid at the feed-in remuneration
$K_{l,t}$, with $K_{u,t} > K_{l,t}$. Both may vary by slot, for example under
time-of-use tariffs. The difference $K_{u,t} - K_{l,t}$ is the gain per kWh that
local trade creates relative to the grid alternatives.

The AMMBA pool is a virtual counterparty. In each slot it buys all allocated
energy from the sellers and sells it to the buyers at a single clearing price
$p_t$. It holds no inventory and makes no profit.

## The pricing function

The clearing price is a function of the supply-to-demand ratio
$r_t = S_t / D_t$, defined for $S_t, D_t > 0$:

$$
p_t = K_{u,t} - \frac{K_{u,t} - K_{l,t}}{1 + e^{-\beta (r_t - \theta)}} \tag{1}
$$

The midpoint $\theta > 0$ and the steepness $\beta \ge 0$ set the shape of the
curve. The figure shows it for the default parameters of the implementation,
$\theta = 1$, $K_u = 28.5$ ct/kWh and $K_l = 8.0$ ct/kWh, and three values of
$\beta$.

![Pricing function and split of the gains from trade](../assets/figures/pricing.png)

_Panel (a): the clearing price as a function of the supply-to-demand ratio.
Panel (b): the buyers' share of the gains from local trade, explained in
[allocation and gains from trade](allocation.md#gains-from-trade)._

## Properties

The following properties follow directly from Eq. (1).

- **Bounded.** For every ratio, $K_{l,t} < p_t < K_{u,t}$: the price never
  leaves the band of the outside options. The implementation additionally
  clamps the result to the closed band to exclude numerical artefacts.
- **Monotone.** For $\beta > 0$ the price strictly decreases in $r_t$:
  relatively more local supply means a lower price, relatively more demand a
  higher one. For $\beta = 0$ the price is constant at the midpoint of the band.
- **Anchored at $\theta$.** At $r_t = \theta$ the price equals the midpoint
  $(K_{u,t} + K_{l,t})/2$. With $\theta = 1$, a balanced slot with
  $S_t = D_t$ is priced at the midpoint.
- **Tunable sensitivity.** The slope at the midpoint is
  $-\beta (K_{u,t} - K_{l,t})/4$, so $\beta$ scales how strongly the price
  reacts to scarcity or abundance.
- **Verifiable.** The price depends only on two aggregate quantities and the
  published parameters. Any participant can recompute it without access to
  individual orders.

## Interpretation as an automated market maker

In AMM terms, Eq. (1) plays the role of the bonding curve: the
supply-to-demand ratio of the batch takes the place of the ratio of pool
reserves in a constant-function market maker. Unlike such market makers, the
AMMBA pool holds no inventory. The grid absorbs any imbalance at the two ends
of the band; see [market design](../background/market-design.md).

## Implementation notes

The function is implemented in `amm-clearing-node/src/sigmoid.py`. The
exponent is limited to $[-500, 500]$ to prevent overflow, and the result is
clamped to $[K_{l,t}, K_{u,t}]$. A copy in `amm-execution-node/src/sigmoid.py`
serves counterfactual pricing for the penalty mechanism and must be kept
identical. The calibration tool uses the unclamped function; see
[calibration](calibration.md#solution-method).
