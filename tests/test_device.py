"""End-to-end tests of the object model over the in-memory mock backend."""

from __future__ import annotations

from datetime import date, time

import pytest
from modbus_connection import (
    ClientClosedError,
    GatewayTargetError,
    ModbusTimeoutError,
)
from modbus_connection.mock import MockModbusConnection, MockModbusUnit

from trovis_modbus import (
    ControlCircuitRole,
    MonthDay,
    OperatingMode,
    RemoteInputRole,
    SystemActivity,
    SystemOverallStatus,
    TemperatureRange,
    Trovis557x,
    TrovisWriteAccessError,
    TrovisWriteVerificationError,
    Weekday,
)
from trovis_modbus.configurations.address_ranges import (
    COIL_RANGES,
    REGISTER_RANGES,
)

from .conftest import COILS, HOLDING


def test_sets_modbus_timing_requirements(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    Trovis557x(mock_modbus_unit)
    assert mock_modbus_unit.required_timeout == 1
    assert mock_modbus_unit.required_connect_delay == 0


async def test_probe_sets_modbus_timing_requirements(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    await Trovis557x.async_probe(mock_modbus_unit)
    assert mock_modbus_unit.required_timeout == 1
    assert mock_modbus_unit.required_connect_delay == 0


async def test_device_info(trovis: Trovis557x) -> None:
    await trovis.async_update()
    info = trovis.info
    assert info.manufacturer == "SAMSON"
    assert info.model == "TROVIS 5579"  # shaped inline by the property
    assert info.serial_number == "12345"
    assert info.firmware_version == "3.05"


async def test_sensors(trovis: Trovis557x) -> None:
    await trovis.async_update()
    assert trovis.sensors.af1 == pytest.approx(-5.0)  # signed, outdoor temperature
    assert trovis.sensors.vf1 == pytest.approx(30.0)  # unsigned, water in pipes
    assert trovis.sensors.rf1 == pytest.approx(20.0)
    assert trovis.sensors.sf1 == pytest.approx(45.0)
    assert trovis.sensors.sf2 is None  # NaN sentinel
    assert trovis.sensors.sf3 == pytest.approx(65.0)
    assert trovis.sensors.ae1 is None
    # The register descriptors keep the canonical 0.1 scale. The configured
    # role then decides whether that scaled value is kelvin or must be
    # converted back to whole ohms by ``sensor_value``.
    assert trovis.sensors.fg1 == pytest.approx(95.2)
    assert trovis.sensors.ae2 is None
    assert trovis.sensors.fg2 == pytest.approx(325.0)
    assert trovis.sensors.ae3 is None
    assert trovis.sensors.fg3 == pytest.approx(12.5)
    assert trovis.sensor_value("fg1") == pytest.approx(95.2)
    assert trovis.sensor_value("fg2") == 3250
    assert trovis.sensor_value("fg3") == 125
    # The raw IMP register is read for supported models so it remains available
    # for diagnostics. CL139 decides whether IMP is exposed as a canonical sensor.
    assert trovis.sensors.pulse_rate == 240
    assert "pulse_rate" not in trovis.available_sensor_keys
    assert trovis.sensors.analog_input_voltage == pytest.approx(7.35)
    assert trovis.sensors.analog_input_current is None


async def test_clock(trovis: Trovis557x) -> None:
    await trovis.async_update()
    assert trovis.clock.time == time(14, 30)
    assert trovis.clock.date == date(2026, 6, 21)
    assert trovis.clock.datetime.isoformat() == "2026-06-21T14:30:00"


async def test_controller(trovis: Trovis557x) -> None:
    await trovis.async_update()
    assert trovis.controller.switch_top is OperatingMode.AUTOMATIC
    assert trovis.controller.max_flow_setpoint == pytest.approx(90.0)
    assert trovis.controller.summer_start == MonthDay(day=15, month=5)
    assert trovis.controller.summer_end == MonthDay(day=30, month=9)
    assert trovis.controller.temperature_monitoring_deviation == pytest.approx(5.0)
    assert trovis.controller.temperature_monitoring_window == 30
    assert trovis.controller.outdoor_temperature_input_range_start == pytest.approx(
        -20.0
    )
    assert trovis.controller.outdoor_temperature_input_range_end == pytest.approx(50.0)
    assert trovis.controller.summer_outdoor_temperature_average == pytest.approx(18.5)
    assert trovis.controller.glt_timeout_active is False


async def test_heating_circuit_reads(trovis: Trovis557x) -> None:
    await trovis.async_update()
    rk1 = trovis.rk1
    assert rk1.mode is OperatingMode.AUTOMATIC
    assert rk1.active_mode is OperatingMode.AUTOMATIC
    assert rk1.mode_control_autonomous is True
    assert rk1.valve_setpoint == 42
    assert rk1.flow_setpoint == pytest.approx(55.0)
    assert rk1.room_setpoint_active == pytest.approx(21.0)
    assert rk1.pump_running is True
    assert rk1.day_active is True
    assert rk1.automatic is True


async def test_circuit_offset_pattern(trovis: Trovis557x) -> None:
    """Circuit 2 reads its own (+200) registers."""
    await trovis.async_update()
    assert trovis.rk2.flow_setpoint == pytest.approx(48.0)
    assert trovis.rk1.flow_setpoint == pytest.approx(55.0)


async def test_heating_curve(trovis: Trovis557x) -> None:
    await trovis.async_update()
    curve = trovis.rk1.heating_curve()
    assert curve is not None and len(curve) == 41
    # day active, room 21, slope 1.2, offset 0, clamp [20, 80]
    assert curve[-1] == pytest.approx(26.4)  # outdoor temperature +20 °C
    assert trovis.rk1.heating_curve("night") is not None


async def test_domestic_hot_water(trovis: Trovis557x) -> None:
    await trovis.async_update()
    rk4 = trovis.rk4
    assert rk4.setpoint_day == pytest.approx(50.0)
    assert rk4.setpoint_active == pytest.approx(50.0)
    assert rk4.active_mode is OperatingMode.AUTOMATIC
    assert rk4.mode_control_autonomous is True
    assert rk4.active_charging_setpoint == pytest.approx(67.0)
    assert rk4.disinfection_weekday is Weekday.WEDNESDAY
    assert rk4.disinfection_start == time(19, 0)
    assert rk4.disinfection_stop == time(21, 0)
    assert rk4.day_temperature_range == TemperatureRange(50.0, 55.0)
    assert rk4.night_temperature_range == TemperatureRange(45.0, 50.0)
    assert rk4.automatic is True
    assert rk4.storage_tank_charging_pump_running is True


async def test_combined_activity(trovis: Trovis557x) -> None:
    await trovis.async_update()
    assert trovis.system_activity is SystemActivity.HEATING_AND_DOMESTIC_HOT_WATER


async def test_system_overall_status(trovis: Trovis557x) -> None:
    """The overall status combines the configured actuator states."""
    await trovis.async_update()

    assert trovis.system_overall_status == (
        SystemOverallStatus.RK1_VALVE_OPEN
        | SystemOverallStatus.SLP_RUNNING
        | SystemOverallStatus.UP1_RUNNING
    )
    assert int(trovis.system_overall_status) == 25


async def test_system_overall_status_bit_order(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    """Every actuator state occupies its permanently assigned bit."""
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding.update(
        {
            1: 61,  # Anlage 6.1: Rk1, Rk2, Rk3 and Rk4
            106: 10,  # Rk1 valve setpoint
            108: 20,  # Rk2 valve setpoint
            110: 30,  # Rk3 valve setpoint
        }
    )
    mock_modbus_unit.coil.update(COILS)
    mock_modbus_unit.coil.update(
        {
            56: True,  # UP1
            57: True,  # UP2
            58: True,  # UP3
            59: True,  # SLP
            60: True,  # ZP
        }
    )

    device = Trovis557x(mock_modbus_unit, model=5579)
    await device.async_update()

    assert device.control_circuit_indices == (1, 2, 3, 4)
    assert device.system_overall_status == (
        SystemOverallStatus.RK1_VALVE_OPEN
        | SystemOverallStatus.RK2_VALVE_OPEN
        | SystemOverallStatus.RK3_VALVE_OPEN
        | SystemOverallStatus.SLP_RUNNING
        | SystemOverallStatus.UP1_RUNNING
        | SystemOverallStatus.UP2_RUNNING
        | SystemOverallStatus.UP3_RUNNING
        | SystemOverallStatus.ZP_RUNNING
    )
    assert int(device.system_overall_status) == 255


async def test_independent_component_update(trovis: Trovis557x) -> None:
    """A sub-system refreshes on its own, without the rest."""
    await trovis.rk4.async_update()
    assert trovis.rk4.setpoint_day == pytest.approx(50.0)
    assert trovis.rk1.flow_setpoint is None  # not updated yet


async def test_full_update_consolidates_reads(
    trovis: Trovis557x, unit: MockModbusUnit
) -> None:
    """A full device update pools all sub-systems into a few block reads."""
    field_count = sum(len(c.readable_field_names) for c in trovis.components)
    await trovis.async_update()

    # Many fields collapse into a small number of range-aware block reads — far
    # fewer than the field count, and well under a naive per-field strategy.
    assert len(unit.read_events) < field_count // 4

    # The exact number of blocks may change when manufacturer ranges or the
    # planner improve. The stable safety guarantee is the configured max_span.
    assert all(event.count <= 50 for event in unit.read_events)


async def test_full_update_never_reads_across_an_unreadable_gap(
    trovis: Trovis557x, unit: MockModbusUnit
) -> None:
    """Every block stays inside the controller's readable ranges (no NAK risk)."""
    await trovis.async_update()

    ranges = {"holding": REGISTER_RANGES, "coil": COIL_RANGES}
    for event in unit.read_events:
        declared = ranges[event.register_type]
        covered = range(event.address, event.address + event.count)
        assert all(
            any(low <= address <= high for low, high in declared) for address in covered
        ), (
            f"{event.register_type} block {covered.start}..{covered.stop - 1} "
            "crosses an unreadable gap"
        )
    # Addresses 7-8 (between ranges [0,6] and [9,40]) are never read — the low
    # registers split there instead of being merged into one 0..26 block.
    read = {
        event.address + i
        for event in unit.read_events
        if event.register_type == "holding"
        for i in range(event.count)
    }
    assert 7 not in read and 8 not in read


async def test_consolidated_reads_decode_correctly(unit: MockModbusUnit) -> None:
    """Adjacent physical sensor registers decode to the right sensor inputs."""
    # Flow sensors VF1/VF2/VF3 are at adjacent addresses 12/13/14 — fetched in
    # one block, then decoded on the central Sensors component.
    unit.holding.update({12: 300, 13: 310, 14: 320})
    device = Trovis557x(unit)

    await device.async_update()

    assert device.sensors.vf1 == pytest.approx(30.0)
    assert device.sensors.vf2 == pytest.approx(31.0)
    assert device.sensors.vf3 == pytest.approx(32.0)


async def test_update_survives_a_dropped_connection() -> None:
    """A dropped link heals on the next update — the device is not rebuilt."""
    connection = MockModbusConnection()
    unit = connection.for_unit(1)
    unit.holding.update(HOLDING)
    unit.coil.update(COILS)
    device = Trovis557x(unit)
    await device.async_update()
    assert device.rk1.flow_setpoint == pytest.approx(55.0)

    lost: list[int] = []
    connection.on_connection_lost(lambda: lost.append(1))
    connection.simulate_connection_lost()
    assert lost == [1]

    # The same device and unit handles keep working; the request reconnects.
    await device.async_update()
    assert device.rk1.flow_setpoint == pytest.approx(55.0)


async def test_update_survives_a_recycled_connection() -> None:
    """disconnect() recycles a stuck link; the device keeps its handles."""
    connection = MockModbusConnection()
    unit = connection.for_unit(1)
    unit.holding.update(HOLDING)
    unit.coil.update(COILS)
    device = Trovis557x(unit)
    await device.async_update()

    lost: list[int] = []
    connection.on_connection_lost(lambda: lost.append(1))
    await connection.disconnect()

    await device.async_update()
    assert device.rk1.flow_setpoint == pytest.approx(55.0)
    # The owner tore the link down; nothing was lost.
    assert lost == []


async def test_update_after_close_raises() -> None:
    """Closing is the owner's permanent end of the connection, not a drop."""
    connection = MockModbusConnection()
    unit = connection.for_unit(1)
    unit.holding.update(HOLDING)
    device = Trovis557x(unit)
    await connection.close()

    with pytest.raises(ClientClosedError):
        await device.async_update()


async def test_update_listener(trovis: Trovis557x) -> None:
    calls: list[int] = []
    unsubscribe = trovis.rk4.add_update_listener(lambda: calls.append(1))
    await trovis.rk4.async_update()
    await trovis.rk4.async_update()
    assert len(calls) == 2
    unsubscribe()
    await trovis.rk4.async_update()
    assert len(calls) == 2  # no longer notified


async def test_write_roundtrip(trovis: Trovis557x) -> None:
    await trovis.async_update()
    await trovis.async_enable_writing()
    await trovis.rk1.set_room_setpoint_day(21.5)
    await trovis.rk4.set_setpoint(52.0)
    await trovis.rk1.async_update()
    await trovis.rk4.async_update()
    assert trovis.rk1.room_setpoint_day == pytest.approx(21.5)
    assert trovis.rk4.setpoint_day == pytest.approx(52.0)


async def test_write_rejects_readonly(trovis: Trovis557x) -> None:
    with pytest.raises(AttributeError):
        await trovis.rk1.write("flow_setpoint", 50.0)


async def test_mode_write_uses_command_register_and_effective_readback(
    trovis: Trovis557x,
    unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mode writes do not prewrite ownership and verify the active-mode HR."""
    original_write_register = unit.write_register
    original_write_coil = unit.write_coil
    coil_writes: list[tuple[int, bool]] = []

    async def emulate_controller_mode_write(address: int, value: int) -> None:
        await original_write_register(address, value)
        if address == 105:
            unit.holding[73] = value
            unit.coil[88] = False

    async def track_coil_write(address: int, value: bool) -> None:
        coil_writes.append((address, value))
        await original_write_coil(address, value)

    monkeypatch.setattr(unit, "write_register", emulate_controller_mode_write)
    monkeypatch.setattr(unit, "write_coil", track_coil_write)

    await trovis.rk1.set_mode(OperatingMode.DAY)

    assert coil_writes == []
    assert (await unit.read_holding_registers(105, 1))[0] == int(OperatingMode.DAY)
    assert (await unit.read_holding_registers(73, 1))[0] == int(OperatingMode.DAY)
    assert trovis.rk1.active_mode is OperatingMode.DAY
    assert trovis.rk1.mode_control_autonomous is False


async def test_circuit2_mode_uses_its_own_command_and_active_registers(
    trovis: Trovis557x,
    unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Circuit 2 uses HR40108/HR40075 and its own ownership bit."""
    original_write_register = unit.write_register

    async def emulate_controller_mode_write(address: int, value: int) -> None:
        await original_write_register(address, value)
        if address == 107:
            unit.holding[74] = value
            unit.coil[90] = False

    monkeypatch.setattr(unit, "write_register", emulate_controller_mode_write)

    await trovis.rk2.set_mode(OperatingMode.NIGHT)

    assert (await unit.read_holding_registers(107, 1))[0] == int(OperatingMode.NIGHT)
    assert (await unit.read_holding_registers(74, 1))[0] == int(OperatingMode.NIGHT)
    assert trovis.rk2.active_mode is OperatingMode.NIGHT
    assert trovis.rk2.mode_control_autonomous is False


async def test_write_access_enable_disable(
    trovis: Trovis557x, unit: MockModbusUnit
) -> None:
    assert await trovis.async_read_writing_enabled() is False

    await trovis.async_enable_writing()
    assert await trovis.async_read_writing_enabled() is True
    assert (await unit.read_holding_registers(144, 1))[0] == 1732

    await trovis.async_disable_writing()
    assert await trovis.async_read_writing_enabled() is False
    assert (await unit.read_holding_registers(144, 1))[0] == 0


async def test_write_refreshes_access_code(
    trovis: Trovis557x, unit: MockModbusUnit
) -> None:
    """The public write path refreshes HR40145 and caches verified readback."""
    assert await trovis.async_read_writing_enabled() is False

    verified = await trovis.rk1.async_write_datapoint("room_setpoint_day", 21.5)

    assert verified is True
    assert (await unit.read_holding_registers(144, 1))[0] == 1732
    assert (await unit.read_holding_registers(1002, 1))[0] == 215
    assert trovis.rk1.room_setpoint_day == pytest.approx(21.5)


async def test_write_access_timeout_is_read_back_before_retry(
    trovis: Trovis557x, unit: MockModbusUnit, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lost HR40145 response must not cause an unnecessary second write."""
    original_write_register = unit.write_register
    access_writes = 0

    async def write_access_with_lost_response(address: int, value: int) -> None:
        nonlocal access_writes
        await original_write_register(address, value)
        if address == 144:
            access_writes += 1
            if access_writes == 1:
                raise ModbusTimeoutError("simulated lost HR40145 response")

    monkeypatch.setattr(unit, "write_register", write_access_with_lost_response)

    await trovis.async_enable_writing()

    assert access_writes == 1
    assert trovis.writing_enabled is True
    assert (await unit.read_holding_registers(144, 1))[0] == 1732


async def test_write_timeout_is_read_back_before_retry(
    trovis: Trovis557x, unit: MockModbusUnit, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lost write response must not duplicate a write that already landed."""
    original_write_register = unit.write_register
    datapoint_writes = 0

    async def write_register_with_lost_response(address: int, value: int) -> None:
        nonlocal datapoint_writes
        await original_write_register(address, value)
        if address == 1002:
            datapoint_writes += 1
            if datapoint_writes == 1:
                raise ModbusTimeoutError("simulated lost write response")

    monkeypatch.setattr(unit, "write_register", write_register_with_lost_response)

    verified = await trovis.rk1.async_write_datapoint("room_setpoint_day", 21.5)

    assert verified is True
    assert datapoint_writes == 1
    assert trovis.rk1.room_setpoint_day == pytest.approx(21.5)


async def test_coil_write_timeout_is_read_back_before_retry(
    trovis: Trovis557x, unit: MockModbusUnit, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lost response for an ordinary state coil is verified before retrying."""
    original_write_coil = unit.write_coil
    datapoint_writes = 0

    async def write_coil_with_lost_response(address: int, value: bool) -> None:
        nonlocal datapoint_writes
        await original_write_coil(address, value)
        if address == 1810:
            datapoint_writes += 1
            if datapoint_writes == 1:
                raise ModbusTimeoutError("simulated lost coil response")

    monkeypatch.setattr(unit, "write_coil", write_coil_with_lost_response)

    verified = await trovis.rk4.async_write_datapoint(
        "storage_tank_charging_enabled", True
    )

    assert verified is True
    assert datapoint_writes == 1
    assert trovis.rk4.storage_tank_charging_enabled is True


async def test_write_readback_mismatch_retries_twice_at_most(
    trovis: Trovis557x, unit: MockModbusUnit, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mismatching targeted readback causes another logical write attempt."""
    original_read_holding = unit.read_holding_registers
    original_write_register = unit.write_register
    datapoint_writes = 0
    datapoint_reads = 0

    async def count_write(address: int, value: int) -> None:
        nonlocal datapoint_writes
        await original_write_register(address, value)
        if address == 1002:
            datapoint_writes += 1

    async def stale_first_read(address: int, count: int) -> list[int]:
        nonlocal datapoint_reads
        if address == 1002:
            datapoint_reads += 1
            if datapoint_reads == 1:
                return [210]
        return await original_read_holding(address, count)

    monkeypatch.setattr(unit, "write_register", count_write)
    monkeypatch.setattr(unit, "read_holding_registers", stale_first_read)

    verified = await trovis.rk1.async_write_datapoint("room_setpoint_day", 21.5)

    assert verified is True
    assert datapoint_writes == 2
    assert datapoint_reads == 2
    assert trovis.rk1.room_setpoint_day == pytest.approx(21.5)


async def test_write_stops_after_two_retries_when_readback_never_matches(
    trovis: Trovis557x, unit: MockModbusUnit, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A persistent mismatch sends one initial write plus exactly two retries."""
    original_read_holding = unit.read_holding_registers
    original_write_register = unit.write_register
    datapoint_writes = 0

    async def count_write(address: int, value: int) -> None:
        nonlocal datapoint_writes
        await original_write_register(address, value)
        if address == 1002:
            datapoint_writes += 1

    async def always_stale_read(address: int, count: int) -> list[int]:
        if address == 1002:
            return [210]
        return await original_read_holding(address, count)

    monkeypatch.setattr(unit, "write_register", count_write)
    monkeypatch.setattr(unit, "read_holding_registers", always_stale_read)

    with pytest.raises(TrovisWriteVerificationError):
        await trovis.rk1.async_write_datapoint("room_setpoint_day", 21.5)

    assert datapoint_writes == 3


async def test_forced_charging_timeout_is_never_retried(
    trovis: Trovis557x, unit: MockModbusUnit, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CL1807 is a trigger: an ambiguous timeout must never send it twice."""
    original_write_coil = unit.write_coil
    trigger_writes = 0

    async def trigger_with_lost_response(address: int, value: bool) -> None:
        nonlocal trigger_writes
        await original_write_coil(address, value)
        if address == 1806:
            trigger_writes += 1
            raise ModbusTimeoutError("simulated lost CL1807 response")

    monkeypatch.setattr(unit, "write_coil", trigger_with_lost_response)

    with pytest.raises(TrovisWriteVerificationError, match="deliberately not retried"):
        await trovis.rk4.async_write_datapoint("forced_charging", True)

    assert trigger_writes == 1
    assert (await unit.read_coils(1806, 1))[0] is True


async def test_write_access_reports_a_device_that_answers_nothing(
    trovis: Trovis557x, unit: MockModbusUnit
) -> None:
    """Every HR40145 path reports a refusal as a TROVIS write-access failure."""
    # A gateway that answers for itself while the controller behind it does not
    # — the usual failure of a TROVIS on an RTU-over-TCP bridge.
    unit.fail_requests(GatewayTargetError())

    with pytest.raises(TrovisWriteAccessError):
        await trovis.async_read_writing_enabled()
    with pytest.raises(TrovisWriteAccessError):
        await trovis.async_enable_writing()
    with pytest.raises(TrovisWriteAccessError):
        await trovis.async_disable_writing()
    # The public datapoint write refreshes the access code first, so it fails
    # there rather than reaching the register it was asked to write.
    with pytest.raises(TrovisWriteAccessError):
        await trovis.rk1.set_room_setpoint_day(21.5)
    assert trovis.writing_enabled is False


async def test_5576_anlage_2_1_exposes_rk1_and_rk4(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.coil.update(COILS)
    device = Trovis557x(
        mock_modbus_unit,
        model=5576,
    )
    await device.async_update()
    assert device.control_circuit_indices == (1, 4)


async def test_5576_anlage_2_1_exposes_rk_roles(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.coil.update(COILS)
    device = Trovis557x(
        mock_modbus_unit,
        model=5576,
    )

    await device.async_update()

    assert device.configuration_definition is not None
    assert device.configuration_definition.display_code == "2.1"
    assert device.configuration_supported_by_model is True
    assert device.control_circuit_indices == (1, 4)
    assert device.control_circuit_role(1) is ControlCircuitRole.HEATING
    assert device.control_circuit_role(2) is ControlCircuitRole.UNUSED
    assert device.control_circuit_role(3) is ControlCircuitRole.UNUSED
    assert device.control_circuit_role(4) is ControlCircuitRole.DOMESTIC_HOT_WATER
    assert device.has_rk4 is True


def test_device_exposes_only_rk_slot_names(mock_modbus_unit: MockModbusUnit) -> None:
    device = Trovis557x(mock_modbus_unit, model=5579)

    assert device.rk1 is device.control_circuits[0]
    assert device.rk2 is device.control_circuits[1]
    assert device.rk3 is device.control_circuits[2]
    assert device.rk4 is not None
    for legacy_name in ("hk1", "hk2", "hk3", "ww", "heating_circuits"):
        assert not hasattr(device, legacy_name)


async def test_control_circuit_roles_are_clipped_to_model_capacity(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = 61  # Anlage 6.1 uses Rk1 through Rk3.
    mock_modbus_unit.coil.update(COILS)
    device = Trovis557x(
        mock_modbus_unit,
        model=5576,
    )

    await device.async_update()

    assert device.configuration_definition is not None
    assert device.configuration_definition.display_code == "6.1"
    assert device.configuration_supported_by_model is False
    assert device.control_circuit_indices == (1, 2, 4)
    assert device.control_circuit_role(3) is ControlCircuitRole.UNUSED


async def test_5579_anlage_5_1_exposes_precontrol_and_heating_roles(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = 51
    mock_modbus_unit.coil.update(COILS)
    device = Trovis557x(
        mock_modbus_unit,
        model=5579,
    )

    await device.async_update()

    assert device.control_circuit_indices == (1, 2, 3, 4)
    assert device.control_circuit_role(1) is ControlCircuitRole.PRECONTROL
    assert device.control_circuit_role(2) is ControlCircuitRole.HEATING
    assert device.control_circuit_role(3) is ControlCircuitRole.HEATING
    assert device.control_circuit_role(4) is ControlCircuitRole.DOMESTIC_HOT_WATER
    assert device.room_heating_circuit_indices == (2, 3)
    assert device.has_rk4 is True


@pytest.mark.parametrize(
    (
        "room_feedback",
        "outdoor_sensor",
        "four_point",
        "optimization",
        "adaptation",
    ),
    (
        (False, True, False, False, False),
        (True, False, False, False, False),
        (True, True, False, True, True),
        (True, True, True, True, False),
    ),
)
async def test_heating_function_availability_follows_configuration(
    mock_modbus_unit: MockModbusUnit,
    room_feedback: bool,
    outdoor_sensor: bool,
    four_point: bool,
    optimization: bool,
    adaptation: bool,
) -> None:
    """Rk function availability follows F01/F02/F11, not live sensor values."""
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = 40  # Anlage 4.0: Rk1 and Rk2 are heating circuits.
    mock_modbus_unit.coil.update(COILS)
    mock_modbus_unit.coil.update(
        {
            1024: room_feedback,  # CL1025 / CO1-F01
            1025: outdoor_sensor,  # CL1026 / CO1-F02
            1034: four_point,  # CL1035 / CO1-F11
        }
    )
    device = Trovis557x(mock_modbus_unit, model=5579)

    await device.async_update()

    assert device.heating_circuit_uses_room_feedback(1) is room_feedback
    assert device.heating_circuit_optimization_available(1) is optimization
    assert device.heating_circuit_adaptation_available(1) is adaptation


async def test_room_dependent_functions_are_not_available_for_precontrol(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    """Optimization and adaptation are exposed only for real heating circuits."""
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = 51  # Anlage 5.1: Rk1 precontrol, Rk2/Rk3 heating.
    mock_modbus_unit.coil.update(COILS)
    mock_modbus_unit.coil.update(
        {
            1024: True,  # CL1025 / CO1-F01
            1025: True,  # CL1026 / CO1-F02
            1034: False,  # CL1035 / CO1-F11
            1224: True,  # CL1225 / CO2-F01
            1225: True,  # CL1226 / CO2-F02
            1234: False,  # CL1235 / CO2-F11
            1424: True,  # CL1425 / CO3-F01
            1425: True,  # CL1426 / CO3-F02
            1434: False,  # CL1435 / CO3-F11
        }
    )
    device = Trovis557x(mock_modbus_unit, model=5579)

    await device.async_update()

    assert device.control_circuit_role(1) is ControlCircuitRole.PRECONTROL
    assert device.heating_circuit_uses_room_feedback(1) is False
    assert device.heating_circuit_uses_outdoor_sensor(1) is False
    assert device.heating_circuit_uses_four_point_characteristic(1) is False
    assert device.heating_circuit_operating_mode(1) is None
    assert device.heating_circuit_optimization_available(1) is False
    assert device.heating_circuit_adaptation_available(1) is False
    assert device.remote_input_role(1) is RemoteInputRole.RESISTANCE_REMOTE

    assert device.control_circuit_role(2) is ControlCircuitRole.HEATING
    assert device.heating_circuit_optimization_available(2) is True
    assert device.heating_circuit_adaptation_available(2) is True

    assert device.control_circuit_role(3) is ControlCircuitRole.HEATING
    assert device.heating_circuit_optimization_available(3) is True
    assert device.heating_circuit_adaptation_available(3) is True


@pytest.mark.parametrize("model", (5573, 55731, 5575, 5576, 5578, 55781, 5579))
async def test_rk2_room_functions_use_only_rk2_f02(
    mock_modbus_unit: MockModbusUnit,
    model: int,
) -> None:
    """Optimization uses the same Rk's F02 selector on every model."""
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = 40  # Anlage 4.0: Rk1 and Rk2 are heating circuits.
    mock_modbus_unit.coil.update(COILS)
    mock_modbus_unit.coil.update(
        {
            1025: False,  # CL1026 / CO1-F02
            1224: True,  # CL1225 / CO2-F01
            1225: True,  # CL1226 / CO2-F02
            1234: False,  # CL1235 / CO2-F11
        }
    )
    device = Trovis557x(mock_modbus_unit, model=model)

    await device.async_update()

    assert device.control_circuit_role(2) is ControlCircuitRole.HEATING
    assert device.heating_circuit_optimization_available(2) is True


@pytest.mark.parametrize("model", (5573, 55731, 5575, 5576, 5578, 55781, 5579))
async def test_rk1_f02_does_not_enable_rk2_room_functions(
    mock_modbus_unit: MockModbusUnit,
    model: int,
) -> None:
    """Another circuit's F02 must never satisfy Rk2 room-function gating."""
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = 40  # Anlage 4.0: Rk1 and Rk2 are heating circuits.
    mock_modbus_unit.coil.update(COILS)
    mock_modbus_unit.coil.update(
        {
            1025: True,  # CL1026 / CO1-F02
            1224: True,  # CL1225 / CO2-F01
            1225: False,  # CL1226 / CO2-F02
            1234: False,  # CL1235 / CO2-F11
        }
    )
    device = Trovis557x(mock_modbus_unit, model=model)

    await device.async_update()

    assert device.control_circuit_role(2) is ControlCircuitRole.HEATING
    assert device.heating_circuit_optimization_available(2) is False


@pytest.mark.parametrize(
    (
        "room_feedback",
        "trovis_5570",
        "expected_role",
        "expected_unit",
        "expected_min",
        "expected_max",
        "expected_step",
        "expected_digits",
        "expected_value",
    ),
    (
        (
            False,
            False,
            RemoteInputRole.RESISTANCE_REMOTE,
            "Ω",
            0,
            2000,
            1,
            0,
            3250,
        ),
        (
            True,
            False,
            RemoteInputRole.ROOM_UNIT_OFFSET,
            "K",
            -5,
            5,
            0.1,
            1,
            325.0,
        ),
        (
            True,
            True,
            RemoteInputRole.RESISTANCE_REMOTE,
            "Ω",
            0,
            2000,
            1,
            0,
            3250,
        ),
    ),
)
async def test_fg_role_and_metadata_follow_room_configuration(
    mock_modbus_unit: MockModbusUnit,
    room_feedback: bool,
    trovis_5570: bool,
    expected_role: RemoteInputRole,
    expected_unit: str,
    expected_min: int,
    expected_max: int,
    expected_step: float | int,
    expected_digits: int,
    expected_value: float | int,
) -> None:
    """FG2 semantics follow F01 and the TROVIS 5570 device-bus exception."""
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = 40  # Rk2 is a real heating circuit.
    mock_modbus_unit.coil.update(COILS)
    mock_modbus_unit.coil.update(
        {
            1224: room_feedback,  # CL1225 / CO2-F01
            703: trovis_5570,  # CL704 / CO7-F04 / TROVIS 5570 in Rk2
        }
    )
    device = Trovis557x(mock_modbus_unit, model=5579)

    await device.async_update()

    assert device.heating_circuit_uses_trovis_5570(2) is trovis_5570
    assert device.remote_input_role(2) is expected_role

    metadata = device.sensor_number_metadata("fg2")
    assert metadata.unit == expected_unit
    assert metadata.min_value == expected_min
    assert metadata.max_value == expected_max
    assert metadata.step == pytest.approx(expected_step)
    assert metadata.digits == expected_digits
    assert device.sensor_value("fg2") == pytest.approx(expected_value)


@pytest.mark.parametrize(
    ("model", "system_code", "expected"),
    (
        (5578, 60, (True, True, True)),
        (5578, 61, (False, False, False)),
        (55781, 60, (True, True, True)),
        (55781, 61, (True, True, True)),
        (5579, 60, (True, True, True)),
        (5579, 61, (False, False, False)),
        (5576, 40, (True, True, False)),
        (5575, 40, (True, True, False)),
        (5573, 40, (False, False, False)),
        (55731, 40, (False, False, False)),
    ),
)
async def test_trovis_5570_availability_follows_model_and_hydronic_system(
    mock_modbus_unit: MockModbusUnit,
    model: int,
    system_code: int,
    expected: tuple[bool, bool, bool],
) -> None:
    """CO7-F03/F04/F05 availability comes from manual model/system lists."""
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = system_code
    mock_modbus_unit.coil.update(COILS)
    device = Trovis557x(mock_modbus_unit, model=model)

    await device.async_update()

    for index, available in enumerate(expected, start=1):
        if index > len(device.control_circuits):
            assert available is False
            continue
        assert device.trovis_5570_room_control_unit_available(index) is available


async def test_unsupported_trovis_5570_coil_is_ignored(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    """A dormant true CO7-F03 bit must not affect 5578 Anlage 6.1."""
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = 61
    mock_modbus_unit.coil.update(COILS)
    mock_modbus_unit.coil[702] = True  # CL703 / CO7-F03, unsupported in 5578/6.1
    mock_modbus_unit.coil[1024] = True  # CO1-F01: local room feedback configured
    device = Trovis557x(mock_modbus_unit, model=5578)

    await device.async_update()

    assert device.trovis_5570_room_control_unit_available(1) is False
    assert device.heating_circuit_uses_trovis_5570(1) is False
    assert device.remote_input_role(1) is RemoteInputRole.ROOM_UNIT_OFFSET


@pytest.mark.parametrize(
    ("model", "system_code", "expected"),
    (
        (5578, 61, True),
        (55781, 61, True),
        (5579, 61, False),
        (5579, 51, False),
        (5579, 95, True),
        (5576, 81, True),
        (5575, 45, True),
    ),
)
async def test_intermediate_heating_availability_follows_model_and_system(
    mock_modbus_unit: MockModbusUnit,
    model: int,
    system_code: int,
    expected: bool,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = system_code
    mock_modbus_unit.coil.update(COILS)
    device = Trovis557x(mock_modbus_unit, model=model)

    await device.async_update()

    assert device.intermediate_heating_available is expected


async def test_5578_anlage_16_1_exposes_buffer_tank_role(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = 161
    mock_modbus_unit.coil.update(COILS)
    device = Trovis557x(
        mock_modbus_unit,
        model=5578,
    )

    await device.async_update()

    assert device.control_circuit_indices == (1, 2)
    assert device.control_circuit_role(1) is ControlCircuitRole.BUFFER_TANK
    assert device.has_buffer_tank_circuit is True
    assert device.has_buffer_tank_charging_parameters is True
    assert device.buffer_tank in device.components
    assert device.control_circuit_role(2) is ControlCircuitRole.HEATING
    assert device.room_heating_circuit_indices == (2,)
    assert device.has_rk4 is False


async def test_solar_capability_follows_hydronic_system(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.coil.update(COILS)
    device = Trovis557x(mock_modbus_unit, model=5579)

    await device.async_update()
    assert device.configuration_definition is not None
    assert device.configuration_definition.display_code == "2.1"
    assert device.has_solar is False

    mock_modbus_unit.holding[1] = 23  # Anlage 2.3 includes solar.
    await device.async_update()
    assert device.configuration_definition is not None
    assert device.configuration_definition.display_code == "2.3"
    assert device.has_solar is True
    assert device.solar.pump_on_temperature_difference == pytest.approx(10.0)
    assert device.solar.pump_off_temperature_difference == pytest.approx(3.0)
    assert device.solar.maximum_storage_temperature == pytest.approx(80.0)
    assert device.solar.operating_hours == 1234
    assert device.solar.pump_running is True


async def test_non_buffer_system_does_not_enable_buffer_tank_circuit(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = 21  # Anlage 2.1
    mock_modbus_unit.coil.update(COILS)

    device = Trovis557x(mock_modbus_unit, model=5579)
    await device.async_update()

    assert device.has_buffer_tank_circuit is False
    assert device.has_buffer_tank_charging_parameters is False


async def test_fixed_loading_buffer_system_omits_pa1_p16_to_p19_capability(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding[1] = 141  # Anlage 14.1
    mock_modbus_unit.coil.update(COILS)

    device = Trovis557x(mock_modbus_unit, model=5576)
    await device.async_update()

    assert device.has_buffer_tank_circuit is True
    assert device.has_buffer_tank_charging_parameters is False
