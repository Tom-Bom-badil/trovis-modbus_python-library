"""Tests for central TROVIS enums and their reusable option metadata."""

from __future__ import annotations

from trovis_modbus import (
    ControlCircuitRole,
    EnergyUnit,
    FlowRateUnit,
    HeatMeterReadMode,
    OperatingMode,
    PowerUnit,
    VolumeUnit,
)
from trovis_modbus.enums import (
    DHW_OPERATING_MODE_OPTIONS,
    ENERGY_UNIT_OPTIONS,
    FLOW_RATE_UNIT_OPTIONS,
    HEAT_METER_READ_MODE_OPTIONS,
    HEATING_OPERATING_MODE_OPTIONS,
    OPERATING_MODE_OPTIONS,
    POWER_UNIT_OPTIONS,
    VOLUME_UNIT_OPTIONS,
)
from trovis_modbus.metadata import OptionMetadata


def _option_values(options: tuple[OptionMetadata, ...]) -> tuple[int, ...]:
    return tuple(option.value for option in options)


def _option_keys(options: tuple[OptionMetadata, ...]) -> tuple[str, ...]:
    return tuple(option.key for option in options)


def test_operating_mode_options_separate_decode_domain_from_remote_writes() -> None:
    """Remote mode subsets exclude PROGRAM/MANUAL while Rk1-Rk4 include NIGHT."""
    assert _option_keys(HEATING_OPERATING_MODE_OPTIONS) == (
        "automatic",
        "standby",
        "day",
        "night",
    )
    assert _option_values(HEATING_OPERATING_MODE_OPTIONS) == (
        int(OperatingMode.AUTOMATIC),
        int(OperatingMode.STANDBY),
        int(OperatingMode.DAY),
        int(OperatingMode.NIGHT),
    )
    assert _option_keys(DHW_OPERATING_MODE_OPTIONS) == (
        "automatic",
        "standby",
        "day",
        "night",
    )
    assert _option_values(DHW_OPERATING_MODE_OPTIONS) == (
        int(OperatingMode.AUTOMATIC),
        int(OperatingMode.STANDBY),
        int(OperatingMode.DAY),
        int(OperatingMode.NIGHT),
    )
    assert OPERATING_MODE_OPTIONS == HEATING_OPERATING_MODE_OPTIONS
    assert int(OperatingMode.PROGRAM) not in _option_values(OPERATING_MODE_OPTIONS)
    assert int(OperatingMode.MANUAL) not in _option_values(OPERATING_MODE_OPTIONS)


def test_heat_meter_read_mode_options_match_controller_values() -> None:
    assert _option_values(HEAT_METER_READ_MODE_OPTIONS) == tuple(
        map(int, HeatMeterReadMode)
    )


def test_heat_meter_unit_options_match_controller_values() -> None:
    assert _option_values(FLOW_RATE_UNIT_OPTIONS) == tuple(map(int, FlowRateUnit))
    assert _option_values(VOLUME_UNIT_OPTIONS) == tuple(map(int, VolumeUnit))
    assert _option_values(ENERGY_UNIT_OPTIONS) == tuple(map(int, EnergyUnit))
    assert _option_values(POWER_UNIT_OPTIONS) == tuple(map(int, PowerUnit))


def test_control_circuit_roles_have_stable_api_values() -> None:
    assert tuple(ControlCircuitRole) == (
        ControlCircuitRole.UNUSED,
        ControlCircuitRole.HEATING,
        ControlCircuitRole.PRECONTROL,
        ControlCircuitRole.BUFFER_TANK,
        ControlCircuitRole.DOMESTIC_HOT_WATER,
    )
    assert ControlCircuitRole.PRECONTROL.value == "precontrol"
    assert ControlCircuitRole.BUFFER_TANK.value == "buffer_tank"
