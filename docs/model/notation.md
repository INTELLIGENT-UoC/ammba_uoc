# Notation

| Symbol                                     | Meaning                                                         | Unit         |
| ------------------------------------------ | --------------------------------------------------------------- | ------------ |
| $t$, $T$                                   | Delivery slot; set of delivery slots                            | –            |
| $d_{j,t}$, $s_{i,t}$                       | Quantity bid by buyer $j$; quantity offered by seller $i$       | kWh          |
| $D_t$, $S_t$                               | Aggregate demand and supply of slot $t$                         | kWh          |
| $r_t$                                      | Supply-to-demand ratio $S_t / D_t$                              | –            |
| $K_{u,t}$, $K_{l,t}$                       | Retail price and feed-in remuneration (price band)              | ct/kWh       |
| $\theta$, $\beta$                          | Midpoint and steepness of the pricing function                  | –            |
| $p_t$                                      | Uniform clearing price                                          | ct/kWh       |
| $Q_t$                                      | Traded volume, $\min(S_t, D_t)$                                 | kWh          |
| $x_{i,t}$, $y_{j,t}$                       | Energy sold by seller $i$; energy bought by buyer $j$           | kWh          |
| $G_t$                                      | Gains from local trade relative to the grid                     | ct           |
| $\sigma(z)$                                | Logistic function $1/(1 + e^{-z})$                              | –            |
| $F$, $R$, $J$                              | Fairness term, range-usage term and calibration objective       | ct/kWh       |
| $\alpha$                                   | Weight of the range-usage term                                  | –            |
| $T'$, $N$                                  | Historical slots with positive supply and demand; their number  | –            |
| $r_{\max}$, $r_{\min}$                     | Largest and smallest observed ratio                             | –            |
| $K_{u,\min}$, $K_{l,\min}$                 | Band of the slot with the smallest ratio                        | ct/kWh       |
| $\gamma$, $\eta$                           | Shortfall penalty factor; tolerance                             | –; kWh       |
| $A_{i,t}$                                  | Energy delivered by seller $i$                                  | kWh          |
| $W_{i,t}$, $W_{j,t}$                       | Supply withheld by seller $i$; demand not reported by buyer $j$ | kWh          |
| $\Phi_{i,t}$, $E^{s}_{i,t}$, $E^{b}_{j,t}$ | Shortfall penalty; seller and buyer externality penalties       | ct           |
| $g$, $l$, $c$                              | Green subsidy rate, grey levy rate, levy cap                    | –; –; ct/kWh |
| $\ell_t$, $V^{\text{grey}}_t$              | Levy per kWh; grey pool volume                                  | ct/kWh; kWh  |
