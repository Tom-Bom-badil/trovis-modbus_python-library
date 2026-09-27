"""Enumerations used across the TROVIS model."""

from __future__ import annotations

from enum import IntEnum, IntFlag, StrEnum

from .metadata import OptionMetadata


class ControllerModel(StrEnum):
    """Supported TROVIS controller model designation."""

    TROVIS_5573 = "5573"
    TROVIS_5573_1 = "5573-1"
    TROVIS_5575 = "5575"
    TROVIS_5576 = "5576"
    TROVIS_5578 = "5578"
    TROVIS_5578_E = "5578-E"
    TROVIS_5579 = "5579"


class ControlCircuitRole(StrEnum):
    """Hydronic role assigned to one technical control-circuit slot."""

    UNUSED = "unused"
    HEATING = "heating"
    PRECONTROL = "precontrol"
    BUFFER_TANK = "buffer_tank"
    DOMESTIC_HOT_WATER = "domestic_hot_water"


class HeatingCircuitControlMode(StrEnum):
    """Setpoint-generation mode used by one heating circuit."""

    HEATING_CURVE = "heating_curve"
    FOUR_POINT = "four_point"
    FIXED_SETPOINT = "fixed_setpoint"


class PumpControlMode(StrEnum):
    """Ownership/state selection for a remotely controllable pump output."""

    AUTO = "auto"
    ON = "on"
    OFF = "off"


class RemoteInputRole(StrEnum):
    """Resolved physical meaning of one FG1-FG3 input."""

    ROOM_UNIT_OFFSET = "room_unit_offset"
    RESISTANCE_REMOTE = "resistance_remote"


class OperatingMode(IntEnum):
    """Operating mode of a heating circuit, domestic hot water, or rotary switch.

    Matches the controller's complete switch list (``Liste_Schalter``). The
    writable option list intentionally excludes :attr:`PROGRAM`, while every
    heating and domestic-hot-water circuit uses the same enum.
    """

    PROGRAM = 0  # timer program ("PA")
    AUTOMATIC = 1
    STANDBY = 2
    MANUAL = 3  # manual mode / "Hand"
    DAY = 4  # daytime settings / "Sonne"
    NIGHT = 5  # nighttime settings / "Mond"


class Weekday(IntEnum):
    """Weekday for the thermal-disinfection schedule (0 = disabled)."""

    OFF = 0
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6
    SUNDAY = 7


class HeatMeterReadMode(IntEnum):
    """Read mode used by a connected heat meter."""

    HOURS_24 = 0
    CONTINUOUS = 1
    COIL = 2


class FlowRateUnit(IntEnum):
    """Unit selector for heat-meter flow-rate values."""

    CUBIC_METERS_PER_HOUR = 0
    LITERS_PER_HOUR = 1


class VolumeUnit(IntEnum):
    """Unit selector for heat-meter volume values."""

    CUBIC_METERS = 0
    LITERS = 1


class EnergyUnit(IntEnum):
    """Unit selector for heat-meter energy values."""

    MEGAWATT_HOURS = 0
    KILOWATT_HOURS = 1
    GIGAJOULES = 2


class PowerUnit(IntEnum):
    """Unit selector for heat-meter power values."""

    KILOWATTS = 0
    MEGAWATTS = 1


class StorageStatus(IntEnum):
    """Current domestic-hot-water storage operating state (HR41827)."""

    STANDBY = 0
    MONITORING = 1
    CIRCULATION = 2
    DEMAND = 3
    CHARGING = 4
    PUMP_OVERRUN = 5
    DISCHARGE_PROTECTION = 6


class BufferTankStatus(IntEnum):
    """Current operating state of the Rk1 buffer-tank charging process."""

    STANDBY = 0
    MONITORING = 1
    RESERVED = 2  # value is not described in the manufacturer register table
    DEMAND = 3
    CHARGING = 4
    PUMP_OVERRUN = 5
    DISCHARGE_PROTECTION = 6


class SystemActivity(IntEnum):
    """Combined heating and domestic-hot-water system activity."""

    IDLE = 0
    HEATING = 1
    DOMESTIC_HOT_WATER = 2
    HEATING_AND_DOMESTIC_HOT_WATER = 3


class SystemOverallStatus(IntFlag):
    """Bit mask of current pump and valve output states."""

    NONE = 0
    RK1_VALVE_OPEN = 1
    RK2_VALVE_OPEN = 2
    RK3_VALVE_OPEN = 4
    SLP_RUNNING = 8
    UP1_RUNNING = 16
    UP2_RUNNING = 32
    UP3_RUNNING = 64
    ZP_RUNNING = 128


# Reusable option metadata for the enums above.
#
# ``OperatingMode`` represents the complete value domain reported by the
# controller. Remote write support is intentionally narrower than that decode
# domain: PROGRAM and MANUAL remain decodable states but are not normal Modbus
# write targets. Heating and DHW option tuples stay separate so model-family
# restrictions can be represented independently if later evidence requires it.
HEATING_OPERATING_MODE_OPTIONS = (
    OptionMetadata("automatic", int(OperatingMode.AUTOMATIC), "Auto"),
    OptionMetadata("standby", int(OperatingMode.STANDBY), "Standby"),
    OptionMetadata("day", int(OperatingMode.DAY), "Sonne"),
    OptionMetadata("night", int(OperatingMode.NIGHT), "Mond"),
)

DHW_OPERATING_MODE_OPTIONS = (
    OptionMetadata("automatic", int(OperatingMode.AUTOMATIC), "Auto"),
    OptionMetadata("standby", int(OperatingMode.STANDBY), "Standby"),
    OptionMetadata("day", int(OperatingMode.DAY), "Sonne"),
    OptionMetadata("night", int(OperatingMode.NIGHT), "Mond"),
)

# Backwards-compatible alias for callers that historically imported the single
# common option list. Heating circuits remain the superset.
OPERATING_MODE_OPTIONS = HEATING_OPERATING_MODE_OPTIONS


WEEKDAY_OPTIONS = (
    OptionMetadata("off", int(Weekday.OFF), "Aus"),
    OptionMetadata("monday", int(Weekday.MONDAY), "Montag"),
    OptionMetadata("tuesday", int(Weekday.TUESDAY), "Dienstag"),
    OptionMetadata("wednesday", int(Weekday.WEDNESDAY), "Mittwoch"),
    OptionMetadata("thursday", int(Weekday.THURSDAY), "Donnerstag"),
    OptionMetadata("friday", int(Weekday.FRIDAY), "Freitag"),
    OptionMetadata("saturday", int(Weekday.SATURDAY), "Samstag"),
    OptionMetadata("sunday", int(Weekday.SUNDAY), "Sonntag"),
)


HEAT_METER_READ_MODE_OPTIONS = (
    OptionMetadata("hours_24", int(HeatMeterReadMode.HOURS_24), "24h"),
    OptionMetadata("continuous", int(HeatMeterReadMode.CONTINUOUS), "Cont"),
    OptionMetadata("coil", int(HeatMeterReadMode.COIL), "Coil"),
)


VOLUME_UNIT_OPTIONS = (
    OptionMetadata("cubic_meters", int(VolumeUnit.CUBIC_METERS), "m³"),
    OptionMetadata("liters", int(VolumeUnit.LITERS), "l"),
)


ENERGY_UNIT_OPTIONS = (
    OptionMetadata("megawatt_hours", int(EnergyUnit.MEGAWATT_HOURS), "MWh"),
    OptionMetadata("kilowatt_hours", int(EnergyUnit.KILOWATT_HOURS), "kWh"),
    OptionMetadata("gigajoules", int(EnergyUnit.GIGAJOULES), "GJ"),
)


POWER_UNIT_OPTIONS = (
    OptionMetadata("kilowatts", int(PowerUnit.KILOWATTS), "kW"),
    OptionMetadata("megawatts", int(PowerUnit.MEGAWATTS), "MW"),
)


FLOW_RATE_UNIT_OPTIONS = (
    OptionMetadata(
        "cubic_meters_per_hour",
        int(FlowRateUnit.CUBIC_METERS_PER_HOUR),
        "m³/h",
    ),
    OptionMetadata(
        "liters_per_hour",
        int(FlowRateUnit.LITERS_PER_HOUR),
        "l/h",
    ),
)
