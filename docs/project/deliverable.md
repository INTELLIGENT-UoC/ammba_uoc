# Deliverable mapping

AMMBA is the result of Task 5.4 of the INTELLIGENT project, in Work Package 5
(peer-to-peer energy and flexibility exchange). The task's deliverable combines
a written report with this open-source repository and its documentation, and
it is released in two versions:

| Version | Due                                     | Focus                                                                                                           |
| ------- | --------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| V1      | End of November 2026 (project month 24) | The market model, its calibration and governance, and the basic implementation                                  |
| V2      | End of March 2027 (project month 28)    | Preferences and differential pricing in depth, settlement, integration with the GSY DEX and EWDS, pilot results |

## Report sections and documentation pages

The documentation follows the structure of the report, so each part of the
report has a maintained counterpart here.

| Report section (V1)                                              | Documentation                                                                                                                                                                                                  |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Market design context and positioning                            | [Market design and positioning](../background/market-design.md)                                                                                                                                                |
| Market setting, pricing function and its properties              | [Pricing function](../model/pricing.md)                                                                                                                                                                        |
| Allocation, budget balance and the split of the gains from trade | [Allocation and gains from trade](../model/allocation.md)                                                                                                                                                      |
| Calibration of the pricing parameters                            | [Parameter calibration](../model/calibration.md)                                                                                                                                                               |
| Parameter governance and the role of the community               | [Parameter governance](../model/governance.md)                                                                                                                                                                 |
| Incentives and deviation management                              | [Incentives and penalties](../model/incentives.md)                                                                                                                                                             |
| Simulation-based evaluation                                      | [Evaluation design](../model/evaluation.md)                                                                                                                                                                    |
| Extensions treated in V2                                         | [Preferences and differential pricing](../model/extensions.md)                                                                                                                                                 |
| Basic implementation                                             | [Architecture](../implementation/architecture.md), [clearing engine](../implementation/clearing-engine.md), [calibration tool](../implementation/calibration-tool.md), [testing](../implementation/testing.md) |
| Integration strategy and roadmap                                 | [Integration](../integration/index.md), [roadmap](roadmap.md)                                                                                                                                                  |
| Open-source repository and documentation                         | This site, [contributing](contributing.md)                                                                                                                                                                     |
| Notation annex                                                   | [Notation](../model/notation.md)                                                                                                                                                                               |

The repository documents some topics in more technical depth than V1 of the
report, because the software already implements them: the
[EWDS transport](../integration/ewds.md), the
[data model and identifiers](../integration/data-model.md) and the
[settlement engine](../implementation/settlement-engine.md). The report covers
them in V2.

## Citing AMMBA

The repository contains a `CITATION.cff` file with the software citation;
GitHub shows it under "Cite this repository". The citation of the companion
publication will be added once it is available.
