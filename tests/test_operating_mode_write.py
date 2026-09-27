"""Tests for TROVIS operating-mode command, effective state and ownership."""

from __future__ import annotations

import logging

import pytest
from modbus_connection import ModbusTimeoutError
from modbus_connection.mock import MockModbusUnit

from trovis_modbus import (
    OperatingMode,
    Trovis557x,
    TrovisValueValidationError,
)
from trovis_modbus.enums import (
    DHW_OPERATING_MODE_OPTIONS,
    HEATING_OPERATING_MODE_OPTIONS,
)


def test_circuits_expose_separate_remote_operating_mode_options(
    trovis: Trovis557x,
) -> None:
    """Heating and DHW keep full decoding with the verified remote write subset."""
    heating_metadata = trovis.rk1.require_metadata_for("mode")
    ww_metadata = trovis.rk4.require_metadata_for("mode")

    assert heating_metadata.enum is not None
    assert ww_metadata.enum is not None
    assert heating_metadata.enum.options == HEATING_OPERATING_MODE_OPTIONS
    assert ww_metadata.enum.options == DHW_OPERATING_MODE_OPTIONS

    assert tuple(option.value for option in HEATING_OPERATING_MODE_OPTIONS) == (
        1,
        2,
        4,
        5,
    )
    assert tuple(option.value for option in DHW_OPERATING_MODE_OPTIONS) == (
        1,
        2,
        4,
        5,
    )


def test_effective_operating_mode_addresses_are_separate_from_command_registers(
    trovis: Trovis557x,
) -> None:
    """Command and effective operating modes use the verified separate HRs."""
    assert trovis.rk1._address(trovis.rk1.declared_fields["active_mode"]) == 73
    assert trovis.rk2._address(trovis.rk2.declared_fields["active_mode"]) == 74
    assert trovis.rk3._address(trovis.rk3.declared_fields["active_mode"]) == 75
    assert trovis.rk4._address(trovis.rk4.declared_fields["active_mode"]) == 76

    assert trovis.rk1._address(trovis.rk1.declared_fields["mode"]) == 105
    assert trovis.rk2._address(trovis.rk2.declared_fields["mode"]) == 107
    assert trovis.rk3._address(trovis.rk3.declared_fields["mode"]) == 109
    assert trovis.rk4._address(trovis.rk4.declared_fields["mode"]) == 111


async def test_heating_mode_write_has_no_glt_prewrite_and_uses_active_mode(
    trovis: Trovis557x,
    unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A direct mode command lets the controller switch itself to GLT."""
    original_write_register = unit.write_register
    original_write_coil = unit.write_coil
    mode_coil_writes: list[tuple[int, bool]] = []

    async def emulate_controller_mode_write(address: int, value: int) -> None:
        await original_write_register(address, value)
        if address == 105:  # HR40106 / Rk1 command
            unit.holding[73] = value  # HR40074 / effective mode
            unit.coil[88] = False  # CL89 / controller switches ownership to GLT

    async def track_coil_writes(address: int, value: bool) -> None:
        mode_coil_writes.append((address, value))
        await original_write_coil(address, value)

    monkeypatch.setattr(unit, "write_register", emulate_controller_mode_write)
    monkeypatch.setattr(unit, "write_coil", track_coil_writes)

    await trovis.rk1.set_mode(OperatingMode.NIGHT)

    assert mode_coil_writes == []
    assert (await unit.read_holding_registers(105, 1))[0] == int(OperatingMode.NIGHT)
    assert (await unit.read_holding_registers(73, 1))[0] == int(OperatingMode.NIGHT)
    assert (await unit.read_coils(88, 1))[0] is False
    assert trovis.rk1.active_mode is OperatingMode.NIGHT
    assert trovis.rk1.mode_control_autonomous is False


async def test_external_automatic_is_distinct_from_autark(
    trovis: Trovis557x,
    unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Technical AUTOMATIC=1 is an external GLT command, not ownership release."""
    original_write_register = unit.write_register

    unit.holding[105] = int(OperatingMode.DAY)
    unit.holding[73] = int(OperatingMode.DAY)
    unit.coil[88] = True

    async def emulate_controller_mode_write(address: int, value: int) -> None:
        await original_write_register(address, value)
        if address == 105:
            unit.holding[73] = value
            unit.coil[88] = False

    monkeypatch.setattr(unit, "write_register", emulate_controller_mode_write)

    await trovis.rk1.set_mode(OperatingMode.AUTOMATIC)

    assert (await unit.read_holding_registers(105, 1))[0] == 1
    assert (await unit.read_holding_registers(73, 1))[0] == 1
    assert (await unit.read_coils(88, 1))[0] is False
    assert trovis.rk1.active_mode is OperatingMode.AUTOMATIC


async def test_rk2_normalized_command_readback_does_not_break_verification(
    trovis: Trovis557x,
    unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rk2 NIGHT succeeds even when HR40108 normalizes back to value 2."""
    original_write_register = unit.write_register

    async def emulate_rk2_normalized_readback(address: int, value: int) -> None:
        await original_write_register(address, value)
        if address == 107:  # HR40108
            unit.holding[107] = int(OperatingMode.STANDBY)
            unit.holding[74] = int(OperatingMode.NIGHT)  # HR40075 is authoritative
            unit.coil[90] = False

    monkeypatch.setattr(unit, "write_register", emulate_rk2_normalized_readback)

    verified = await trovis.rk2.async_write_datapoint("mode", OperatingMode.NIGHT)

    assert verified is True
    assert (await unit.read_holding_registers(107, 1))[0] == 2
    assert trovis.rk2.active_mode is OperatingMode.NIGHT
    assert trovis.rk2.mode_control_autonomous is False


async def test_mode_write_waits_for_active_mode_without_rewriting(
    trovis: Trovis557x,
    unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A delayed active_mode update is polled without repeating an ack write."""
    import trovis_modbus.data_model as data_model

    original_write_register = unit.write_register
    original_read_holding_registers = unit.read_holding_registers
    mode_writes = 0
    active_reads = 0

    async def emulate_delayed_mode_write(address: int, value: int) -> None:
        nonlocal mode_writes
        await original_write_register(address, value)
        if address == 105:
            mode_writes += 1
            unit.coil[88] = False

    async def delayed_active_read(address: int, count: int) -> list[int]:
        nonlocal active_reads
        if address == 73 and count == 1:
            active_reads += 1
            if active_reads == 3:
                unit.holding[73] = int(OperatingMode.DAY)
        return await original_read_holding_registers(address, count)

    async def no_wait(_delay: float) -> None:
        return None

    monkeypatch.setattr(unit, "write_register", emulate_delayed_mode_write)
    monkeypatch.setattr(unit, "read_holding_registers", delayed_active_read)
    monkeypatch.setattr(data_model.asyncio, "sleep", no_wait)
    caplog.set_level(logging.INFO, logger="trovis_modbus.data_model")

    await trovis.rk1.set_mode(OperatingMode.DAY)

    assert mode_writes == 1
    assert active_reads == 3
    assert trovis.rk1.active_mode is OperatingMode.DAY
    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "Rk1 operating-mode change requested: target=DAY" in msg for msg in messages
    )
    assert any("Rk1 operating-mode settling: requested=DAY" in msg for msg in messages)
    assert any("Rk1 operating-mode verified: requested=DAY" in msg for msg in messages)
    assert any(
        "Rk1 operating-mode change complete: active=DAY" in msg for msg in messages
    )


async def test_mode_write_timeout_checks_active_mode_before_retry(
    trovis: Trovis557x,
    unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lost mode-write response is not duplicated once active_mode matches."""
    original_write_register = unit.write_register
    mode_writes = 0

    async def write_with_lost_response(address: int, value: int) -> None:
        nonlocal mode_writes
        await original_write_register(address, value)
        if address == 105:
            mode_writes += 1
            unit.holding[73] = value
            unit.coil[88] = False
            if mode_writes == 1:
                raise ModbusTimeoutError("simulated lost operating-mode response")

    monkeypatch.setattr(unit, "write_register", write_with_lost_response)

    await trovis.rk1.set_mode(OperatingMode.DAY)

    assert mode_writes == 1
    assert trovis.rk1.active_mode is OperatingMode.DAY


async def test_autark_release_only_writes_ownership_coil(
    trovis: Trovis557x,
    unit: MockModbusUnit,
) -> None:
    """AUTARK release leaves the external command register untouched."""
    unit.holding[105] = int(OperatingMode.NIGHT)
    unit.holding[73] = int(OperatingMode.NIGHT)
    unit.coil[88] = False

    await trovis.rk1.release_mode_control()

    assert (await unit.read_coils(88, 1))[0] is True
    assert (await unit.read_holding_registers(105, 1))[0] == int(OperatingMode.NIGHT)
    assert trovis.rk1.mode_control_autonomous is True
    assert trovis.rk1.active_mode is OperatingMode.NIGHT


async def test_rk4_accepts_night_but_rejects_manual_remote_mode(
    trovis: Trovis557x,
    unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DHW accepts NIGHT=5 at HR40112 while MANUAL remains read-only state."""
    original_write_register = unit.write_register

    async def emulate_rk4_mode_write(address: int, value: int) -> None:
        await original_write_register(address, value)
        if address == 111:  # HR40112 / Rk4 command
            unit.holding[76] = value  # HR40077 / effective mode
            unit.coil[94] = False  # CL95 / GLT ownership

    monkeypatch.setattr(unit, "write_register", emulate_rk4_mode_write)

    await trovis.rk4.set_mode(OperatingMode.NIGHT)

    assert (await unit.read_holding_registers(111, 1))[0] == int(OperatingMode.NIGHT)
    assert trovis.rk4.active_mode is OperatingMode.NIGHT
    assert trovis.rk4.mode_control_autonomous is False

    with pytest.raises(TrovisValueValidationError):
        await trovis.rk4.set_mode(OperatingMode.MANUAL)


def test_rk4_setpoint_absolute_ranges_are_5_to_90_celsius(
    trovis: Trovis557x,
) -> None:
    """DHW day/night and adjustable bounds share the documented 5..90 °C domain."""
    for field in ("setpoint_day", "setpoint_night", "setpoint_min", "setpoint_max"):
        metadata = trovis.rk4.require_metadata_for(field)
        assert metadata.number is not None
        assert metadata.number.min_value == 5
        assert metadata.number.max_value == 90


async def test_global_glt_status_is_derived_from_present_circuits(
    trovis: Trovis557x,
    unit: MockModbusUnit,
) -> None:
    """The device-wide GLT flag is on when any present Rk has ownership=GLT."""
    await trovis.async_update()
    assert trovis.any_operating_mode_glt_active is False

    # Rk1 is present in the fixture's system; one GLT ownership bit is enough.
    unit.coil[88] = False
    await trovis.async_update()
    assert trovis.any_operating_mode_glt_active is True

    # Unknown ownership must not be reported as an all-AUTARK state.
    unit.coil[88] = True
    await trovis.async_update()
    trovis.rk1._bits["mode_control_autonomous"] = None
    assert trovis.any_operating_mode_glt_active is None
