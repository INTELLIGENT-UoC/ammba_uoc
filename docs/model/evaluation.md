# Evaluation design

AMMBA is evaluated against an order-book market (OBM) on household data. The
evaluation operationalises the comparison between pool-based and
order-book-based mechanisms that the INTELLIGENT call asks for. This page
describes the design; the results are reported in the companion publication.

## Data

The evaluation uses four consecutive days of quarter-hourly household data (96
slots per day): net demand per household and slot, time-of-day retail prices
and feed-in tariffs that define the price band of each slot, and bid and offer
prices per household and slot for the order-book baseline.

## Scenarios

Three scenarios represent different levels of PV penetration. Of the
households that export energy in the original data, 34% (Low), 66% (Medium) and
100% (High) are kept as prosumers; the others are treated as pure consumers.
Only slots with positive local surplus are cleared, since only these offer
local trade.

## Protocol

- **Train/test split.** For each scenario, $\theta$ and $\beta$ are calibrated
  on days 2 to 4 and the mechanisms are evaluated on day 1, so the evaluation
  uses data not seen during calibration.
- **Weight.** Parameters are calibrated for $\alpha = 0.4$ and
  $\alpha = 0.5$, and the evaluation uses those obtained with $\alpha = 0.5$.
- **Baseline.** The OBM clears each slot by submitting the bids, in descending
  order of price, and the offers, in ascending order of price, as limit orders
  to an order book.

## Strategic behaviour

Two targeted experiments on the High scenario test the
[penalty mechanism](incentives.md). In each, 10% of the participants behave
strategically: either sellers withhold 20% of their available surplus, or
buyers under-report 10% of their demand. Both experiments are run with
penalties enabled, with $\gamma = 1.1$ and $\eta = 0$.

## Outlook

Version 2 of the deliverable extends the evaluation with data from the
INTELLIGENT pilot sites and compares AMMBA with the order-book mechanisms of the
GSY DEX on that data.
