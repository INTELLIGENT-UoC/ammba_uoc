"""Aggregate historical int:Measurement records into per-slot market state.

Input is a list of int:Measurement objects (the GSY DEX ontology shape:
``facilityId``, ``communityUuid``, ``timeSlot``, ``creationTime``, ``energyKwh``).
Output is one `Slot` per time slot with aggregate supply and demand, ready for
the optimizer.

SIGN CONVENTION (confirmed by GSY): positive ``energyKwh`` is net consumption
(demand), negative is net injection / production (supply) — the net-load
convention used in the reference research data. The ``positive_is_consumption``
flag stays for flexibility but the default is the agreed convention.
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
