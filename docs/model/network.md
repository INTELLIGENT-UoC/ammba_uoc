# Network-aware extension

Local trades are constrained by the physical limits of the distribution network,
and they change the network losses. Saber et al. (2026) extend AMMBA with an
on-chain network model that addresses both aspects after market clearing,
without changing the clearing rule itself. The extension targets radial
distribution networks.

> **Scope.** The extension is part of the published mechanism and of its
> simulation code. It is not implemented in the software of this repository,
> whose clearing engine clears without network constraints.

## Elements

**On-chain power flow (OC-PF).** In the AC power flow equations, the main
nonlinearity stems from the feeder losses. By introducing suitable virtual
variables, the OC-PF formulation removes the loss terms, so that feeder flows
become linear functions of the nodal injections and node voltages follow from
a simple fixed-point iteration. The computation is light enough to run in a
smart contract.

**Corrective actions.** If the traded schedule violates voltage or
feeder-flow limits, a corrective action algorithm computes the smallest
adjustments, in the least-squares sense, of the buyers' consumption and the
sellers' generation that restore feasibility. The problem decomposes by agent
through Lagrangian relaxation: each agent computes its adjustment in closed
form from the current dual variables, which are updated by a subgradient step
until convergence. Without violations, all adjustments are zero and the market
outcome is unchanged.

**Loss allocation.** Network losses caused by the trades are allocated ex post
based on marginal loss factors (MLFs), which measure how an incremental
withdrawal at a node changes the total losses:

- When trading increases losses, the cost, valued at the retail price, is
  borne by the participants whose positions increase them.
- When trading reduces losses, for example when local generation supplies
  nearby load around midday, the benefit, valued at the feed-in tariff, is
  credited to the participants who cause the reduction.

Shares are proportional to the MLF-weighted traded energy. The result is a
participant-specific final price around the uniform clearing price.

## Results

The publication evaluates the extension on the IEEE 33-node distribution test
network with 1,000 households and a high share of prosumers:

- Voltages and flows computed with OC-PF deviate only marginally from a full
  AC power flow, and the daily network losses by about 2.5%.
- With a minimum voltage of 0.90 p.u., the voltage limits were violated in two
  15-minute intervals of the evening peak. Reducing buyer consumption by
  42.4 kWh and 60.2 kWh, respectively, restored them.
- With flow limits imposed on two lines, the evening overloads were removed
  with a total consumption adjustment of about 1,495 kWh over the day.
- Network losses were negative around midday, when local generation served
  local load, so the sellers received a loss-reduction benefit in these
  periods.
