"""Aggregate historical int:Measurement records into per-slot market state.

Input is a list of int:Measurement objects (the GSY DEX ontology shape:
``areaUuid``, ``communityUuid``, ``timeSlot``, ``creationTime``, ``energyKwh``).
Output is one `Slot` per time slot with aggregate supply and demand, ready for
the optimizer.

SIGN CONVENTION (provisional — open question with GSY): we assume the
**net-load** convention used in the reference research data, where a positive
``energyKwh`` is net consumption (demand) and a negative value is net injection
(production surplus). Flip ``positive_is_consumption=False`` if GSY confirms the
opposite. This is the single semantic assumption to revisit once the measurement
feed is specified — see INTEGRATION_NOTES.md.
"""

from src.optimizer import Slot


def aggregate_slots(
    measurements: list[dict],
    k_upper: float,
    k_lower: float,
    community_uuid: str | None = None,
    positive_is_consumption: bool = True,
) -> list[Slot]:
    """Group int:Measurement records by time slot into `Slot` aggregates.

    ``k_upper`` / ``k_lower`` are the community's price bounds, applied flat to
    every slot for now (a per-slot tariff series can replace this later).
    """
    demand: dict = {}
    supply: dict = {}

    for m in measurements:
        if community_uuid is not None and m.get("communityUuid") != community_uuid:
            continue
        slot = m["timeSlot"]
        energy = m["energyKwh"]
        consumption = energy if positive_is_consumption else -energy
        if consumption >= 0:
            demand[slot] = demand.get(slot, 0.0) + consumption
        else:
            supply[slot] = supply.get(slot, 0.0) + (-consumption)

    slots = []
    for key in sorted(set(demand) | set(supply), key=str):
        slots.append(
            Slot(
                total_supply=supply.get(key, 0.0),
                total_demand=demand.get(key, 0.0),
                k_upper=k_upper,
                k_lower=k_lower,
            )
        )
    return slots
