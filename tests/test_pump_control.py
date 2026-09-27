"""Pump AUTO/ON/OFF ownership semantics."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from modbus_connection.mock import MockModbusUnit

from trovis_modbus import PumpControlMode, Trovis557x


async def test_pump_control_mode_reflects_ownership_and_output(
    trovis: Trovis557x,
    unit: MockModbusUnit,
) -> None:
    """AUTO comes from ownership; GLT ON/OFF comes from the output state."""
    await trovis.async_update()
    assert trovis.rk1.pump_control_mode is PumpControlMode.AUTO
    assert trovis.rk4.storage_tank_charging_pump_control_mode is PumpControlMode.AUTO
    assert trovis.rk4.circulation_pump_control_mode is PumpControlMode.AUTO

    unit.coil[95] = False
    unit.coil[56] = True
    unit.coil[98] = False
    unit.coil[59] = False
    await trovis.async_update()

    assert trovis.rk1.pump_control_mode is PumpControlMode.ON
    assert trovis.rk4.storage_tank_charging_pump_control_mode is PumpControlMode.OFF


@pytest.mark.parametrize(
    ("component_name", "state_attr", "setter_name", "output", "ownership"),
    [
        ("rk1", "pump_control_mode", "async_set_pump_control_mode", 56, 95),
        ("rk2", "pump_control_mode", "async_set_pump_control_mode", 57, 96),
        ("rk3", "pump_control_mode", "async_set_pump_control_mode", 58, 97),
        (
            "rk4",
            "storage_tank_charging_pump_control_mode",
            "async_set_storage_tank_charging_pump_control_mode",
            59,
            98,
        ),
        (
            "rk4",
            "circulation_pump_control_mode",
            "async_set_circulation_pump_control_mode",
            60,
            99,
        ),
    ],
)
async def test_pump_manual_control_writes_output_without_glt_prewrite(
    trovis: Trovis557x,
    unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
    component_name: str,
    state_attr: str,
    setter_name: str,
    output: int,
    ownership: int,
) -> None:
    """Manual ON/OFF writes only the output; TROVIS moves ownership to GLT."""
    await trovis.async_update()
    component = getattr(trovis, component_name)
    unit.coil[ownership] = True
    unit.coil[output] = True
    writes: list[tuple[int, bool]] = []
    original_write_coil = unit.write_coil

    async def emulate_trovis_write(address: int, value: bool) -> Any:
        writes.append((address, value))
        result = await original_write_coil(address, value)
        if address == output:
            unit.coil[ownership] = False
        return result

    monkeypatch.setattr(unit, "write_coil", emulate_trovis_write)

    setter: Callable[..., Awaitable[None]] = getattr(component, setter_name)
    await setter(PumpControlMode.OFF)

    assert writes == [(output, False)]
    assert unit.coil[ownership] is False
    assert unit.coil[output] is False
    assert getattr(component, state_attr) is PumpControlMode.OFF


@pytest.mark.parametrize(
    ("component_name", "state_attr", "setter_name", "output", "ownership"),
    [
        ("rk1", "pump_control_mode", "async_set_pump_control_mode", 56, 95),
        (
            "rk4",
            "storage_tank_charging_pump_control_mode",
            "async_set_storage_tank_charging_pump_control_mode",
            59,
            98,
        ),
        (
            "rk4",
            "circulation_pump_control_mode",
            "async_set_circulation_pump_control_mode",
            60,
            99,
        ),
    ],
)
async def test_pump_auto_writes_only_ownership_coil(
    trovis: Trovis557x,
    unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
    component_name: str,
    state_attr: str,
    setter_name: str,
    output: int,
    ownership: int,
) -> None:
    """AUTO releases ownership without forcing an output state."""
    await trovis.async_update()
    component = getattr(trovis, component_name)
    unit.coil[ownership] = False
    unit.coil[output] = False
    writes: list[tuple[int, bool]] = []
    original_write_coil = unit.write_coil

    async def capture_write(address: int, value: bool) -> Any:
        writes.append((address, value))
        return await original_write_coil(address, value)

    monkeypatch.setattr(unit, "write_coil", capture_write)

    setter: Callable[..., Awaitable[None]] = getattr(component, setter_name)
    await setter(PumpControlMode.AUTO)

    assert writes == [(ownership, True)]
    assert unit.coil[output] is False
    assert getattr(component, state_attr) is PumpControlMode.AUTO


async def test_zp_off_regression_uses_cl61_not_cl100(
    trovis: Trovis557x,
    unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Norbert regression: ZP OFF must not pre-write CL100=GLT."""
    await trovis.async_update()
    unit.coil[99] = True  # CL100 ZP ownership = AUTARK
    unit.coil[60] = True  # CL61 ZP output = ON
    writes: list[tuple[int, bool]] = []
    original_write_coil = unit.write_coil

    async def emulate_trovis_write(address: int, value: bool) -> Any:
        writes.append((address, value))
        result = await original_write_coil(address, value)
        if address == 60:
            unit.coil[99] = False
        return result

    monkeypatch.setattr(unit, "write_coil", emulate_trovis_write)

    await trovis.rk4.async_set_circulation_pump_control_mode(PumpControlMode.OFF)

    assert writes == [(60, False)]
    assert (99, False) not in writes
    assert trovis.rk4.circulation_pump_control_mode is PumpControlMode.OFF
