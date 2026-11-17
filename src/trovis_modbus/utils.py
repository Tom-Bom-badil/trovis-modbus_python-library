"""Small helpers shared across sub-systems: curves and native value types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import NamedTuple, Protocol

from modbus_connection import ModbusError, ModbusExceptionError

from .addresses import register_address

# Outdoor-temperature x-axis shared by every heating characteristic.
OUTDOOR_TEMPERATURES: list[int] = list(range(-20, 21))


class MonthDay(NamedTuple):
    """A recurring day-of-year without a year (e.g. a summer boundary)."""

    day: int
    month: int

    def __str__(self) -> str:
        """Render as the controller displays it, e.g. ``15.05``."""
        return f"{self.day:02d}.{self.month:02d}"


class TemperatureRange(NamedTuple):
    """Lower and upper edge of a derived temperature interval."""

    minimum: float
    maximum: float


def time_from_hhmm(raw: int | None) -> time | None:
    """Decode the controller's packed HHMM time (e.g. 1430 -> 14:30)."""
    if raw is None:
        return None
    hour, minute = divmod(raw, 100)
    try:
        return time(hour=hour, minute=minute)
    except ValueError:
        return None


def time_to_hhmm(value: time) -> int:
    """Encode a naive, minute-resolution ``time`` as packed HHMM."""
    if not isinstance(value, time):
        raise TypeError(f"expected datetime.time, got {type(value).__name__}")
    if value.tzinfo is not None:
        raise ValueError("TROVIS clock values must not contain a timezone")
    if value.second or value.microsecond:
        raise ValueError("TROVIS clock values have one-minute resolution")
    return value.hour * 100 + value.minute


def month_day_from_ddmm(raw: int | None) -> MonthDay | None:
    """Decode a packed DDMM value into a validated recurring date."""
    if raw is None:
        return None
    day, month = divmod(raw, 100)
    try:
        # Leap year allows the recurring value 29 February.
        date(2000, month, day)
    except ValueError:
        return None
    return MonthDay(day=day, month=month)


def month_day_to_ddmm(value: MonthDay) -> int:
    """Encode a validated recurring date as packed DDMM."""
    if not isinstance(value, MonthDay):
        raise TypeError(f"expected MonthDay, got {type(value).__name__}")
    try:
        date(2000, value.month, value.day)
    except ValueError as err:
        raise ValueError(f"invalid recurring date: {value}") from err
    return value.day * 100 + value.month


def date_from_ddmm_year(raw_date: int | None, year: int | None) -> date | None:
    """Decode packed DDMM plus a separate year register."""
    if raw_date is None or year is None:
        return None
    recurring = month_day_from_ddmm(raw_date)
    if recurring is None:
        return None
    try:
        return date(year, recurring.month, recurring.day)
    except ValueError:
        return None


def date_to_ddmm_year(value: date) -> tuple[int, int]:
    """Encode a calendar date as ``(DDMM, year)``."""
    if not isinstance(value, date):
        raise TypeError(f"expected datetime.date, got {type(value).__name__}")
    return value.day * 100 + value.month, value.year


def heating_curve(
    *,
    room_setpoint: float,
    slope: float,
    offset: float,
    minimum_flow_temperature: float,
    maximum_flow_temperature: float,
    base_temperature: float = 24.0,
) -> list[float]:
    """Calculate a temperature characteristic for outdoor temperatures -20..20 °C.

    ``base_temperature`` is the characteristic value at 20 °C outdoor and
    20 °C room setpoint before applying ``offset``. The TROVIS flow
    characteristic uses 24 °C; the return characteristic uses its configured
    return-flow base point.
    """
    curve: list[float] = []
    for outdoor_temperature in OUTDOOR_TEMPERATURES:
        shifted = outdoor_temperature - 20
        flow = (
            base_temperature
            + offset
            + 2 * slope * (room_setpoint - 20)
            - (0.1 + 0.9 * slope) * (1.5 * shifted + 0.01 * (shifted * shifted))
        )
        curve.append(
            round(max(minimum_flow_temperature, min(maximum_flow_temperature, flow)), 2)
        )
    return curve


# --- Minimal device identity ----------------------------------------------


@dataclass(frozen=True)
class TrovisIdentity:
    """Raw TROVIS model and integer hundredths firmware version."""

    model: int
    firmware: int


async def async_read_identity(unit: object) -> TrovisIdentity:
    """Read HR40001/HR40003 independently, before optional sensor discovery."""
    model_values = await unit.read_holding_registers(register_address(40001), 1)
    firmware_values = await unit.read_holding_registers(register_address(40003), 1)
    if len(model_values) != 1 or len(firmware_values) != 1:
        raise ValueError("Incomplete TROVIS model/firmware identity response")
    model = int(model_values[0])
    firmware = int(firmware_values[0])
    if model <= 0 or firmware <= 0:
        raise ValueError("Invalid TROVIS model or firmware identity")
    return TrovisIdentity(model=model, firmware=firmware)


# --- Conservative Illegal Data Address diagnosis (FC01 / FC03) ------------


class RefusedReadBlock(Protocol):
    """The structural block attached by modbus-connection to a failed read."""

    space: str
    address: int
    count: int


_ILLEGAL_DATA_ADDRESS = 0x02

MAX_DIAGNOSTIC_BLOCK_SIZE = 50


def illegal_address_block(error: ModbusError) -> RefusedReadBlock | None:
    """Return a valid refused read block for a genuine 0x02 response."""
    if not isinstance(error, ModbusExceptionError):
        return None
    if error.exception_code != _ILLEGAL_DATA_ADDRESS:
        return None
    block = getattr(error, "block", None)
    if block is None or block.space not in {"holding", "coil"}:
        return None
    if not 1 <= block.count <= MAX_DIAGNOSTIC_BLOCK_SIZE:
        return None
    if not 0 <= block.address <= 0xFFFF - block.count + 1:
        return None
    return block


async def async_confirm_illegal_addresses(
    unit: object, block: RefusedReadBlock
) -> frozenset[int]:
    """Confirm each illegal PDU address in a rejected block separately.

    Propagate non-0x02 failures. No removal is justified when all single reads
    succeed, which can happen if a combined read crossed a firmware boundary.
    """
    if block.space not in {"holding", "coil"}:
        raise ValueError("Only coil and holding-register reads may be diagnosed")
    if not 1 <= block.count <= MAX_DIAGNOSTIC_BLOCK_SIZE:
        raise ValueError("Diagnostic block is outside the safety limit")
    if not 0 <= block.address <= 0xFFFF - block.count + 1:
        raise ValueError("Diagnostic block exceeds Modbus address range")
    method = (
        unit.read_holding_registers if block.space == "holding" else unit.read_coils
    )
    confirmed: set[int] = set()
    for address in range(block.address, block.address + block.count):
        try:
            await method(address, 1)
        except ModbusExceptionError as error:
            if error.exception_code != _ILLEGAL_DATA_ADDRESS:
                raise
            confirmed.add(address)
    return frozenset(confirmed)
