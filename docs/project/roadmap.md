# Roadmap

Work is tracked publicly as
[issues](https://github.com/INTELLIGENT-UoC/ammba_uoc/issues), grouped into
three [milestones](https://github.com/INTELLIGENT-UoC/ammba_uoc/milestones):

| Milestone                | Scope                                                                                                                  |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| v1.x staging integration | Operating the clearing engine on the INTELLIGENT staging environment: data alignment, market discovery, gateway access |
| v2.0 settlement          | Settling AMM matches through the GSY DEX: pool representation, identifiers, units, settlement engine                   |
| backlog                  | Later work, for example the penalty mechanism in operation and multiple preferred partners                             |

Items that wait for an upstream project carry the label `blocked-external`.

## Planned for version 2

| Topic                                 | Planned content                                                                          |
| ------------------------------------- | ---------------------------------------------------------------------------------------- |
| Preferences and differential pricing  | Formal treatment, evaluation and configuration guidelines                                |
| Settlement                            | Settlement of AMM matches through the GSY DEX, live operation of the settlement engine   |
| Incentive mechanism                   | Penalties computed from metered delivery through the settlement layer                    |
| Integration                           | Operation through EWDS in the project environment                                        |
| Parameter publication                 | Publishing the parameter set in force with each clearing result                          |
| Pilot deployment                      | Community configuration, calibration with pilot data, validation of the governance model |
| Comparison with order-book mechanisms | Comparison with the GSY DEX order-book mechanisms on pilot data                          |

## Release history

Releases are versioned semantically and generated from the commit history.
The [changelog](https://github.com/INTELLIGENT-UoC/ammba_uoc/blob/main/CHANGELOG.md)
lists every change.
