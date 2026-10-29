# Allocation and gains from trade

## Pro-rata allocation

Once the price is known, the traded volume is the largest volume that can be
matched locally. The short side of the market is served completely, and the
long side is rationed in proportion to the submitted quantities:

$$
Q_t = \min(E_t, D_t), \qquad q_{t,i} = D_{t,i} \frac{Q_t}{D_t}, \qquad s_{t,j} = E_{t,j} \frac{Q_t}{E_t} \tag{2}
$$

Here $q_{t,i}$ is the energy bought by buyer $i$ and $s_{t,j}$ the energy sold
by seller $j$. Residual demand $D_{t,i} - q_{t,i}$ is supplied by the retail
supplier at $K_{\mathrm{up},t}$, and residual supply $E_{t,j} - s_{t,j}$ is
exported at $K_{\mathrm{lo}}$, outside the AMMBA market. If one side of the
market is empty, no local trade takes place in the slot.

## Properties

- **Budget balance.** Buyers pay $\pi_t \sum_i q_{t,i} = \pi_t Q_t$ and sellers
  receive $\pi_t \sum_j s_{t,j} = \pi_t Q_t$. The pool neither accumulates nor
  requires money, so neither a subsidy nor an operator margin is needed.
- **Individual rationality.** Since $K_{\mathrm{lo}} \le \pi_t \le K_{\mathrm{up},t}$,
  every buyer pays at most the retail price and every seller receives at least
  the feed-in tariff for each traded kWh. Taking part in the market is never
  worse than using the grid alone.
- **Maximal local matching.** Given the submitted quantities, no allocation can
  match more energy locally than $Q_t$.

## Gains from trade

Relative to a situation in which all participants use only the grid, local
trade creates the gain

$$
G_t = Q_t \, (K_{\mathrm{up},t} - K_{\mathrm{lo}}) \tag{3}
$$

which does not depend on the price. The price only determines how this gain is
divided: buyers save $Q_t (K_{\mathrm{up},t} - \pi_t)$ and sellers earn
$Q_t (\pi_t - K_{\mathrm{lo}})$. Substituting Eq. (1) yields an exact
interpretation of the pricing function:

$$
\frac{K_{\mathrm{up},t} - \pi_t}{K_{\mathrm{up},t} - K_{\mathrm{lo}}} = \sigma\big(B (r_t - \Theta)\big),
\qquad \sigma(z) = \frac{1}{1 + e^{-z}} \tag{4}
$$

The buyers' share of the gains from local trade is the logistic function of the
scaled deviation of the ratio from $\Theta$, and the sellers receive the
complementary share. When supply is scarce ($r_t < \Theta$), sellers receive
more than half of the gains; when supply is abundant ($r_t > \Theta$), buyers
do. Within a slot, the pricing function is therefore a rule for sharing the
gains from local trade. Across slots, the resulting price variation signals
local scarcity and rewards shifting flexible consumption to periods of
abundant local generation.

## Worked example

Two buyers and two sellers trade in one slot with the default parameters $\Theta = 1$, $B = 2.5$, $K_{\mathrm{up}} = 28.5$ ct/kWh
and $K_{\mathrm{lo}} = 8.0$ ct/kWh. Supply is $E = 9$ kWh and demand
$D = 10$ kWh, so $r = 0.9$ and Eq. (1) gives $\pi = 19.52$ ct/kWh, slightly
above the midpoint of 18.25 ct/kWh because supply is the short side. Sellers
are served in full and buyers receive 90% of their bids.

| Participant |       Order (kWh) | Allocated (kWh) | Paid (+) / received (−) (ct) | Residual via grid (kWh) | Gain against grid (ct) |
| ----------- | ----------------: | --------------: | ---------------------------: | ----------------------: | ---------------------: |
| Buyer B1    |               6.0 |             5.4 |                      +105.43 |            0.6 imported |                  48.47 |
| Buyer B2    |               4.0 |             3.6 |                       +70.29 |            0.4 imported |                  32.31 |
| Seller S1   |               5.0 |             5.0 |                       −97.62 |                     0.0 |                  57.62 |
| Seller S2   |               4.0 |             4.0 |                       −78.10 |                     0.0 |                  46.10 |
| **Total**   | E = 9.0, D = 10.0 |         Q = 9.0 |    **0.00** (budget balance) |                     1.0 |             **184.50** |

The gains from local trade of 184.50 ct are split 43.8% to the buyers and
56.2% to the sellers, exactly as Eq. (4) predicts with
$\sigma(2.5 \cdot (0.9 - 1)) = 0.438$.

![Pool-mediated clearing of the worked example](../assets/figures/pool.png)

The clearing engine reproduces this example exactly: with these four orders it
computes a clearing price of 19.5246 ct/kWh and the allocation above.

## Representation as trades

On the exchange, every pool allocation is represented by two bilateral trades:
one between the buyer and the pool and one between the pool and the seller,
both at the clearing price. The pool appears as a configured actor of the
community. Mutual preferred partners trade directly with each other instead;
see [preferences](extensions.md#preferred-trading-partners) and the
[data model](../integration/data-model.md).
