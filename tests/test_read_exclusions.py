from __future__ import annotations

import pytest
from modbus_connection.mock import MockModbusUnit

from trovis_modbus import Trovis557x
from trovis_modbus.addresses import (
    normalize_excluded_addresses,
    ranges_excluding_addresses,
)

from .conftest import COILS, HOLDING


def test_ranges_are_split_around_excluded_addresses() -> None:
    """Excluded addresses become real holes in the readable map."""
    assert ranges_excluding_addresses(
        ((0, 5), (10, 20)),
        frozenset({0, 3, 5, 12, 20, 999}),
    ) == (
        (1, 2),
        (4, 4),
        (10, 11),
        (13, 19),
    )


@pytest.mark.parametrize(
    "addresses",
    (
        {-1},
        {65536},
        {True},
    ),
)
def test_invalid_excluded_addresses_are_rejected(addresses: set[int]) -> None:
    """Only real zero-based Modbus PDU addresses are accepted."""
    with pytest.raises(ValueError):
        normalize_excluded_addresses(addresses)


async def test_excluded_addresses_are_never_read(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    """Excluded register and coil addresses never occur in pooled reads."""
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.coil.update(COILS)

    excluded_registers = {12, 1099}
    excluded_coils = {0, 56}
    device = Trovis557x(
        mock_modbus_unit,
        model=5578,
        excluded_registers=excluded_registers,
        excluded_coils=excluded_coils,
    )

    await device.async_update()

    for event in mock_modbus_unit.read_events:
        excluded = (
            excluded_registers if event.register_type == "holding" else excluded_coils
        )
        covered = range(event.address, event.address + event.count)
        assert excluded.isdisjoint(covered), (
            f"{event.register_type} block {covered.start}..{covered.stop - 1} "
            "contains an excluded address"
        )

    # HR40013 / PDU 12 and CL57 / PDU 56 are modeled datapoints.
    assert device.sensors.vf1 is None
    assert device.rk1.pump_running is None
