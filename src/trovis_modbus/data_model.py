"""Trovis-specific pieces layered on the ``modbus_connection.model`` framework."""

from __future__ import annotations

import asyncio
import datetime
import logging
from collections.abc import Callable, Iterable
from enum import IntEnum
from time import monotonic
from typing import Any

from modbus_connection import ModbusError, ModbusTimeoutError
from modbus_connection.model import (
    Component,
    RegisterField,
    coil as _modbus_coil,
    enum as _modbus_enum,
    gauge as _modbus_gauge,
    integer as _modbus_integer,
    raw_register as _modbus_raw_register,
)

from .addresses import coil_address, register_address
from .configurations.address_ranges import (
    COIL_RANGES,
    REGISTER_RANGES,
    is_span_readable,
)
from .enums import OperatingMode, PumpControlMode
from .exceptions import (
    TrovisValueValidationError,
    TrovisWriteAccessError,
    TrovisWriteVerificationError,
)
from .metadata import (
    BooleanMetadata,
    DatapointMetadata,
    EnumMetadata,
    NumberMetadata,
    OptionMetadata,
    TemporalMetadata,
    attach_metadata,
    step_from_digits,
)
from .utils import (
    MonthDay,
    date_from_ddmm_year,
    date_to_ddmm_year,
    month_day_from_ddmm,
    month_day_to_ddmm,
    time_from_hhmm,
    time_to_hhmm,
)

NAN_INT16 = 0x7FFF  # the value the controller returns for an absent sensor

DEFAULT_WRITE_ACCESS_CODE = 1732
WRITE_ACCESS_REGISTER = 40145  # HR40145 / Write-En_Modem, Modbus address 144
WRITE_ACCESS_DISABLE_CODE = 0

LEVEL_GLT = False
LEVEL_AUTARK = True

# One initial attempt plus two retries. Only response timeouts and an
# explicit readback mismatch are retried; Modbus exception responses and
# other protocol/connection errors keep their normal fail-fast semantics.
WRITE_RETRIES = 2

# Operating-mode commands are processed asynchronously inside TROVIS. A write
# response can therefore arrive before HR40074..HR40077 expose the new effective
# mode. Keep the command write and the state-settling phase separate: successful
# writes are never repeated merely because active_mode has not caught up yet.
OPERATING_MODE_VERIFY_INTERVAL = 0.25
OPERATING_MODE_VERIFY_TIMEOUT = 5.0

# Direct pump-output writes request GLT control. Releasing an output back to
# controller/time-program operation is the opposite direction: its ownership
# coil is written to AUTARK. Do not pre-write ownership=GLT; some TROVIS
# controllers reject that direction with Modbus Illegal Function.
PUMP_CONTROL_VERIFY_INTERVAL = 0.25
PUMP_CONTROL_VERIFY_TIMEOUT = 5.0

_LOGGER = logging.getLogger(__name__)


class PackedTimeField(RegisterField[datetime.time]):
    """A TROVIS HHMM register exposed as a native ``datetime.time``."""

    def __init__(
        self,
        address: int,
        *,
        min_value: datetime.time,
        max_value: datetime.time,
        raw_min: int,
        raw_max: int,
        writable: bool = False,
    ) -> None:
        super().__init__(address, writable=writable)
        self.min_value = min_value
        self.max_value = max_value
        self.raw_min = raw_min
        self.raw_max = raw_max

    def decode(
        self,
        words: list[int],
        scale_exponent: int | None = None,
    ) -> datetime.time | None:
        """Decode one packed HHMM word within the documented range."""
        raw = words[0]
        if not self.raw_min <= raw <= self.raw_max:
            return None
        value = time_from_hhmm(raw)
        if value is None or not self.min_value <= value <= self.max_value:
            return None
        return value

    def encode(
        self,
        value: Any,
        scale_exponent: int | None = None,
    ) -> list[int]:
        """Encode a native time at the regulator's supported precision."""
        try:
            raw = time_to_hhmm(value)
        except (TypeError, ValueError) as err:
            raise TrovisValueValidationError(str(err)) from err
        if not self.min_value <= value <= self.max_value:
            raise TrovisValueValidationError(
                f"Time {value.isoformat()} is outside "
                f"{self.min_value.isoformat()}..{self.max_value.isoformat()}"
            )
        if not self.raw_min <= raw <= self.raw_max:
            raise TrovisValueValidationError(
                f"Packed time {raw} is outside {self.raw_min}..{self.raw_max}"
            )
        return [raw]


def _month_day_key(value: MonthDay) -> tuple[int, int]:
    """Return a calendar-order key for a recurring month/day value."""
    return value.month, value.day


class PackedMonthDayField(RegisterField[MonthDay]):
    """A TROVIS DDMM register exposed as a recurring ``MonthDay``."""

    def __init__(
        self,
        address: int,
        *,
        min_value: MonthDay,
        max_value: MonthDay,
        raw_min: int,
        raw_max: int,
        writable: bool = False,
    ) -> None:
        super().__init__(address, writable=writable)
        self.min_value = min_value
        self.max_value = max_value
        self.raw_min = raw_min
        self.raw_max = raw_max

    def decode(
        self,
        words: list[int],
        scale_exponent: int | None = None,
    ) -> MonthDay | None:
        """Decode one packed DDMM word within the documented range."""
        raw = words[0]
        if not self.raw_min <= raw <= self.raw_max:
            return None
        value = month_day_from_ddmm(raw)
        if value is None:
            return None
        if not (
            _month_day_key(self.min_value)
            <= _month_day_key(value)
            <= _month_day_key(self.max_value)
        ):
            return None
        return value

    def encode(
        self,
        value: Any,
        scale_exponent: int | None = None,
    ) -> list[int]:
        """Encode a validated recurring date."""
        try:
            raw = month_day_to_ddmm(value)
        except (TypeError, ValueError) as err:
            raise TrovisValueValidationError(str(err)) from err
        if not (
            _month_day_key(self.min_value)
            <= _month_day_key(value)
            <= _month_day_key(self.max_value)
        ):
            raise TrovisValueValidationError(
                f"Recurring date {value} is outside {self.min_value}..{self.max_value}"
            )
        if not self.raw_min <= raw <= self.raw_max:
            raise TrovisValueValidationError(
                f"Packed recurring date {raw} is outside {self.raw_min}..{self.raw_max}"
            )
        return [raw]


class PackedDateField(RegisterField[datetime.date]):
    """A TROVIS DDMM register followed by its separate year register."""

    def __init__(
        self,
        address: int,
        *,
        min_value: datetime.date,
        max_value: datetime.date,
        raw_min: int,
        raw_max: int,
        writable: bool = False,
    ) -> None:
        super().__init__(address, count=2, writable=writable)
        self.min_value = min_value
        self.max_value = max_value
        self.raw_min = raw_min
        self.raw_max = raw_max

    def decode(
        self,
        words: list[int],
        scale_exponent: int | None = None,
    ) -> datetime.date | None:
        """Decode ``[DDMM, year]`` into a calendar date."""
        if len(words) != 2 or not self.raw_min <= words[0] <= self.raw_max:
            return None
        value = date_from_ddmm_year(words[0], words[1])
        if value is None or not self.min_value <= value <= self.max_value:
            return None
        return value

    def encode(
        self,
        value: Any,
        scale_exponent: int | None = None,
    ) -> list[int]:
        """Encode a calendar date into ``[DDMM, year]``."""
        try:
            raw_date, year = date_to_ddmm_year(value)
        except (TypeError, ValueError) as err:
            raise TrovisValueValidationError(str(err)) from err
        if not self.min_value <= value <= self.max_value:
            raise TrovisValueValidationError(
                f"Date {value.isoformat()} is outside "
                f"{self.min_value.isoformat()}..{self.max_value.isoformat()}"
            )
        if not self.raw_min <= raw_date <= self.raw_max:
            raise TrovisValueValidationError(
                f"Packed date {raw_date} is outside {self.raw_min}..{self.raw_max}"
            )
        return [raw_date, year]


def _number_validator(
    *,
    min_value: float | int | None = None,
    max_value: float | int | None = None,
    step: float | int | None = None,
) -> Callable[[Any], Any]:
    """Return a write validator for numeric TROVIS values."""

    def validate(value: Any) -> Any:
        number = float(value)
        if min_value is not None and number < min_value:
            raise TrovisValueValidationError(
                f"Value {value} is below minimum {min_value}"
            )
        if max_value is not None and number > max_value:
            raise TrovisValueValidationError(
                f"Value {value} is above maximum {max_value}"
            )
        # Step is primarily UI metadata for now. Avoid hard float-modulo
        # validation until we see invalid writes slipping through.
        return value

    return validate


def _with_number_validator(
    writable: bool | Callable[[Any], Any],
    *,
    min_value: float | int | None,
    max_value: float | int | None,
    step: float | int | None,
) -> bool | Callable[[Any], Any]:
    """Return writable or a validator-backed writable value."""
    if not writable:
        return False
    if callable(writable):
        return writable
    if min_value is None and max_value is None and step is None:
        return True
    return _number_validator(
        min_value=min_value,
        max_value=max_value,
        step=step,
    )


def raw_register(
    hr_number: int,
    *args: Any,
    min_value: float | int | None = None,
    max_value: float | int | None = None,
    step: float | int | None = None,
    digits: int | None = None,
    unit: str | None = None,
    raw_min: float | int | None = None,
    raw_max: float | int | None = None,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
    writable: bool | Callable[[Any], Any] = False,
    **kwargs: Any,
):
    """Create a raw register field from a manufacturer TROVIS HR reference."""
    effective_step = step if step is not None else step_from_digits(digits)
    effective_writable = _with_number_validator(
        writable,
        min_value=min_value,
        max_value=max_value,
        step=effective_step,
    )
    field = _modbus_raw_register(
        register_address(hr_number),
        *args,
        writable=effective_writable,
        **kwargs,
    )
    return attach_metadata(
        field,
        DatapointMetadata(
            value_kind="number",
            maker_reference=hr_number,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=bool(writable),
            number=NumberMetadata(
                min_value=min_value,
                max_value=max_value,
                step=effective_step,
                digits=digits,
                unit=unit,
                raw_min=raw_min,
                raw_max=raw_max,
            ),
        ),
    )


def integer(
    hr_number: int,
    *args: Any,
    min_value: float | int | None = None,
    max_value: float | int | None = None,
    step: float | int | None = None,
    digits: int | None = None,
    unit: str | None = None,
    raw_min: float | int | None = None,
    raw_max: float | int | None = None,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
    writable: bool | Callable[[Any], Any] = False,
    **kwargs: Any,
):
    """Create an integer field from a manufacturer TROVIS HR reference."""
    effective_step = step if step is not None else step_from_digits(digits)
    effective_writable = _with_number_validator(
        writable,
        min_value=min_value,
        max_value=max_value,
        step=effective_step,
    )
    field = _modbus_integer(
        register_address(hr_number),
        *args,
        writable=effective_writable,
        unit=unit,
        **kwargs,
    )
    return attach_metadata(
        field,
        DatapointMetadata(
            value_kind="number",
            maker_reference=hr_number,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=bool(writable),
            number=NumberMetadata(
                min_value=min_value,
                max_value=max_value,
                step=effective_step,
                digits=digits,
                unit=unit,
                raw_min=raw_min,
                raw_max=raw_max,
            ),
        ),
    )


def gauge(
    hr_number: int,
    scale: float,
    *args: Any,
    min_value: float | int | None = None,
    max_value: float | int | None = None,
    step: float | int | None = None,
    digits: int | None = None,
    unit: str | None = None,
    raw_min: float | int | None = None,
    raw_max: float | int | None = None,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
    writable: bool | Callable[[Any], Any] = False,
    **kwargs: Any,
):
    """Create a gauge field from a manufacturer TROVIS HR reference."""
    effective_step = step if step is not None else step_from_digits(digits)
    effective_writable = _with_number_validator(
        writable,
        min_value=min_value,
        max_value=max_value,
        step=effective_step,
    )
    field = _modbus_gauge(
        register_address(hr_number),
        scale,
        *args,
        writable=effective_writable,
        unit=unit,
        **kwargs,
    )
    return attach_metadata(
        field,
        DatapointMetadata(
            value_kind="number",
            maker_reference=hr_number,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=bool(writable),
            number=NumberMetadata(
                min_value=min_value,
                max_value=max_value,
                step=effective_step,
                digits=digits,
                unit=unit,
                raw_min=raw_min,
                raw_max=raw_max,
            ),
        ),
    )


def time_value(
    hr_number: int,
    *,
    min_value: datetime.time,
    max_value: datetime.time,
    raw_min: int,
    raw_max: int,
    writable: bool = False,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
) -> RegisterField[datetime.time]:
    """Create a native minute-resolution time field from a TROVIS HR."""
    field = PackedTimeField(
        register_address(hr_number),
        min_value=min_value,
        max_value=max_value,
        raw_min=raw_min,
        raw_max=raw_max,
        writable=writable,
    )
    return attach_metadata(
        field,
        DatapointMetadata(
            value_kind="time",
            maker_reference=hr_number,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=writable,
            temporal=TemporalMetadata(
                resolution="minute",
                min_value=min_value,
                max_value=max_value,
                raw_min=raw_min,
                raw_max=raw_max,
            ),
        ),
    )


def month_day_value(
    hr_number: int,
    *,
    min_value: MonthDay,
    max_value: MonthDay,
    raw_min: int,
    raw_max: int,
    writable: bool = False,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
) -> RegisterField[MonthDay]:
    """Create a native recurring-date field from a packed TROVIS DDMM HR."""
    field = PackedMonthDayField(
        register_address(hr_number),
        min_value=min_value,
        max_value=max_value,
        raw_min=raw_min,
        raw_max=raw_max,
        writable=writable,
    )
    return attach_metadata(
        field,
        DatapointMetadata(
            value_kind="month_day",
            maker_reference=hr_number,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=writable,
            temporal=TemporalMetadata(
                resolution="day",
                min_value=min_value,
                max_value=max_value,
                raw_min=raw_min,
                raw_max=raw_max,
            ),
        ),
    )


def date_value(
    hr_number: int,
    *,
    min_value: datetime.date,
    max_value: datetime.date,
    raw_min: int,
    raw_max: int,
    writable: bool = False,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
) -> RegisterField[datetime.date]:
    """Create a native date from adjacent TROVIS DDMM and year registers."""
    field = PackedDateField(
        register_address(hr_number),
        min_value=min_value,
        max_value=max_value,
        raw_min=raw_min,
        raw_max=raw_max,
        writable=writable,
    )
    return attach_metadata(
        field,
        DatapointMetadata(
            value_kind="date",
            maker_reference=hr_number,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=writable,
            temporal=TemporalMetadata(
                resolution="day",
                min_value=min_value,
                max_value=max_value,
                raw_min=raw_min,
                raw_max=raw_max,
            ),
        ),
    )


def enum(
    hr_number: int,
    enum_type: type[IntEnum],
    *args: Any,
    options: tuple[OptionMetadata, ...] | None = None,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
    writable: bool | Callable[[Any], Any] = False,
    **kwargs: Any,
):
    """Create an enum field from a manufacturer TROVIS HR reference."""
    field = _modbus_enum(
        register_address(hr_number),
        enum_type,
        *args,
        writable=writable,
        **kwargs,
    )
    resolved_options = options or tuple(
        OptionMetadata(member.name.lower(), int(member), member.name)
        for member in enum_type
    )
    return attach_metadata(
        field,
        DatapointMetadata(
            value_kind="enum",
            maker_reference=hr_number,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=bool(writable),
            enum=EnumMetadata(enum_type=enum_type, options=resolved_options),
        ),
    )


def coil(
    cl_number: int,
    *,
    stride: int = 0,
    writable: bool = False,
    false_key: str = "off",
    true_key: str = "on",
    false_label: str | None = None,
    true_label: str | None = None,
    inverted: bool = False,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
):
    """Create a coil field from a manufacturer TROVIS CL number."""
    field = _modbus_coil(
        coil_address(cl_number),
        stride=stride,
        writable=writable,
    )
    return attach_metadata(
        field,
        DatapointMetadata(
            value_kind="boolean",
            maker_reference=cl_number,
            maker_key=maker_key,
            maker_category=maker_category,
            description=description,
            writable=writable,
            boolean=BooleanMetadata(
                false_key=false_key,
                true_key=true_key,
                false_label=false_label,
                true_label=true_label,
                inverted=inverted,
            ),
        ),
    )


def temperature(
    hr_number: int,
    *,
    stride: int = 0,
    writable: bool = False,
    unit: str = "°C",
    min_value: float | int | None = None,
    max_value: float | int | None = None,
    step: float | int | None = None,
    digits: int | None = None,
    raw_min: float | int | None = None,
    raw_max: float | int | None = None,
    maker_key: str | None = None,
    maker_category: str | None = None,
    description: str | None = None,
) -> RegisterField[float]:
    """A signed 0.1-scaled temperature register with Trovis NaN sentinel."""
    effective_step = 1 if step is None else step

    return gauge(
        hr_number,
        0.1,
        signed=True,
        nan=NAN_INT16,
        stride=stride,
        writable=writable,
        unit=unit,
        min_value=min_value,
        max_value=max_value,
        step=effective_step,
        digits=digits,
        raw_min=raw_min,
        raw_max=raw_max,
        maker_key=maker_key,
        maker_category=maker_category,
        description=description,
    )


async def async_read_writing_enabled(unit: Any) -> bool:
    """Return whether TROVIS write access appears to be active."""
    try:
        return (
            await unit.read_holding_registers(
                register_address(WRITE_ACCESS_REGISTER),
                1,
            )
        )[0] != WRITE_ACCESS_DISABLE_CODE
    except ModbusError as err:
        raise TrovisWriteAccessError(
            "Could not read TROVIS write access state"
        ) from err


async def _async_write_access_state(
    unit: Any,
    value: int,
    *,
    enabled: bool,
    action: str,
) -> None:
    """Write HR40145 and verify the resulting access state.

    A write timeout is ambiguous: the controller may have applied the value and
    only the response may have been lost. Therefore every attempt is followed by
    a targeted readback before another write is sent.
    """
    address = register_address(WRITE_ACCESS_REGISTER)
    last_timeout: ModbusTimeoutError | None = None

    for attempt in range(WRITE_RETRIES + 1):
        # Keep only the failure context from the current/final logical attempt.
        # A timeout from an earlier attempt must not mask a later plain mismatch.
        last_timeout = None
        try:
            await unit.write_register(address, value)
        except ModbusTimeoutError as err:
            last_timeout = err
            _LOGGER.debug(
                "TROVIS write-access %s timed out on attempt %d/%d; "
                "checking HR40145 before retrying",
                action,
                attempt + 1,
                WRITE_RETRIES + 1,
            )
        except ModbusError as err:
            raise TrovisWriteAccessError(
                f"Could not {action} TROVIS write access"
            ) from err

        try:
            (readback,) = await unit.read_holding_registers(address, 1)
        except ModbusTimeoutError as err:
            last_timeout = err
            _LOGGER.debug(
                "TROVIS write-access %s readback timed out on attempt %d/%d",
                action,
                attempt + 1,
                WRITE_RETRIES + 1,
            )
        except ModbusError as err:
            raise TrovisWriteAccessError(
                f"Could not verify TROVIS write access while trying to {action} it"
            ) from err
        else:
            state_matches = (readback != WRITE_ACCESS_DISABLE_CODE) == enabled
            if state_matches:
                if attempt:
                    _LOGGER.debug(
                        "TROVIS write-access %s succeeded on attempt %d/%d",
                        action,
                        attempt + 1,
                        WRITE_RETRIES + 1,
                    )
                return

            last_timeout = None
            _LOGGER.debug(
                "TROVIS write-access %s readback mismatch on attempt %d/%d: %d",
                action,
                attempt + 1,
                WRITE_RETRIES + 1,
                readback,
            )

    message = (
        f"Could not {action} TROVIS write access after {WRITE_RETRIES + 1} attempts"
    )
    if last_timeout is not None:
        raise TrovisWriteAccessError(message) from last_timeout
    raise TrovisWriteAccessError(message)


async def async_enable_writing(
    unit: Any,
    access_code: int = DEFAULT_WRITE_ACCESS_CODE,
) -> None:
    """Enable TROVIS writing globally and verify HR40145."""
    await _async_write_access_state(
        unit,
        access_code,
        enabled=True,
        action="enable",
    )


async def async_disable_writing(unit: Any) -> None:
    """Disable TROVIS writing globally and verify HR40145."""
    await _async_write_access_state(
        unit,
        WRITE_ACCESS_DISABLE_CODE,
        enabled=False,
        action="reset",
    )


async def async_ensure_writing_enabled(
    unit: Any,
    access_code: int = DEFAULT_WRITE_ACCESS_CODE,
) -> None:
    """Refresh and verify the TROVIS access code for the next write."""
    await _async_write_access_state(
        unit,
        access_code,
        enabled=True,
        action="refresh",
    )


class TrovisComponent(Component):
    """A Trovis sub-system with readable ranges and verified writes.

    Some writable values are ignored over Modbus unless their "Ebene" override
    coil is first released to 0 (= GLT / remote control). Subclasses list those
    ordinary datapoints in :attr:`ebene_coils`. Operating-mode ownership is a
    separate protocol concept and is handled by the dedicated mode helpers.
    """

    register_ranges = REGISTER_RANGES
    coil_ranges = COIL_RANGES
    max_span = 50

    # Writable fields whose write must first change an Ebene override coil.
    ebene_coils: dict[str, tuple[int, int]] = {}

    # Optional values that restore autonomous controller operation through an
    # Ebene coil instead of writing the corresponding datapoint. Operating mode
    # deliberately does not use this generic mechanism: external AUTOMATIC=1
    # and AUTARK ownership are distinct controller states.
    ebene_autark_values: dict[str, Any] = {}

    # Command/edge-trigger fields must opt out of automatic write retries.
    # A timed-out response for such a field has an inherently ambiguous
    # outcome and repeating the write could execute the command twice.
    non_retryable_write_fields: frozenset[str] = frozenset()

    def _ensure_read_layout_is_configurable(self) -> None:
        """Reject availability changes after the read layout was built."""
        cached_layout = {"_read_items"} & self.__dict__.keys()
        if self.__dict__.get("_plan") is not None:
            cached_layout.add("_plan")
        if cached_layout:
            names = ", ".join(sorted(cached_layout))
            raise RuntimeError(
                "read availability must be configured before the first read "
                f"layout is built (already cached: {names})"
            )

    def configure_readable_ranges(
        self,
        register_ranges: tuple[tuple[int, int], ...],
        coil_ranges: tuple[tuple[int, int], ...],
    ) -> None:
        """Keep only fields whose complete spans are readable for the model."""
        self._ensure_read_layout_is_configurable()
        self.register_ranges = register_ranges
        self.coil_ranges = coil_ranges

        declared_registers = type(self)._register_fields
        self._register_fields = {
            name: descriptor
            for name, descriptor in declared_registers.items()
            if self._register_field_is_readable(descriptor, register_ranges)
        }

        declared_bits = type(self)._bit_fields
        self._bit_fields = {
            name: descriptor
            for name, descriptor in declared_bits.items()
            if is_span_readable(
                self._address(descriptor),
                getattr(descriptor, "count", 1),
                coil_ranges,
            )
        }

    def configure_readable_fields(self, field_names: Iterable[str]) -> None:
        """Limit one component instance to a declared set of field names.

        Ranges remain the coarse address-availability map. This optional second
        filter removes unsupported logical views that share an otherwise valid
        address, for example model-specific sensor aliases.
        """
        self._ensure_read_layout_is_configurable()
        allowed = frozenset(field_names)
        self._register_fields = {
            name: descriptor
            for name, descriptor in self._register_fields.items()
            if name in allowed
        }
        self._bit_fields = {
            name: descriptor
            for name, descriptor in self._bit_fields.items()
            if name in allowed
        }

    def _register_field_is_readable(
        self,
        descriptor: RegisterField[Any],
        register_ranges: tuple[tuple[int, int], ...],
    ) -> bool:
        """Return whether a register field and its scale register are readable."""
        if not is_span_readable(
            self._address(descriptor),
            descriptor.count,
            register_ranges,
        ):
            return False

        if descriptor.scale_register is None:
            return True
        return is_span_readable(self._scale_address(descriptor), 1, register_ranges)

    @property
    def readable_field_names(self) -> frozenset[str]:
        """Return fields selected by the current model's range profile."""
        return frozenset((*self._register_fields, *self._bit_fields))

    def is_field_readable(self, field: str) -> bool:
        """Return whether ``field`` is part of this instance's read layout."""
        return field in self._register_fields or field in self._bit_fields

    def metadata_for(self, field: str) -> DatapointMetadata | None:
        """Return neutral TROVIS metadata for a declared field."""
        descriptor = type(self).declared_fields.get(field)
        if descriptor is None:
            return None
        return getattr(descriptor, "trovis_metadata", None)

    def require_metadata_for(self, field: str) -> DatapointMetadata:
        """Return TROVIS metadata for a field or raise."""
        metadata = self.metadata_for(field)
        if metadata is None:
            raise AttributeError(f"unknown or untyped TROVIS field {field!r}")
        return metadata

    async def write(self, field: str, value: Any) -> None:
        """Write a field, applying generic field-specific TROVIS preconditions.

        Ordinary overridden fields first switch their Ebene coil to ``GLT`` and
        then write the requested value. Operating modes intentionally bypass
        this mechanism and use :meth:`async_set_operating_mode` instead.
        """
        if (override := self.ebene_coils.get(field)) is not None:
            address, stride = override
            coil = coil_address(address + stride * (self._index - 1))

            if (
                field in self.ebene_autark_values
                and value == self.ebene_autark_values[field]
            ):
                await self._unit.write_coil(coil, LEVEL_AUTARK)
                return

            await self._unit.write_coil(coil, LEVEL_GLT)

        await super().write(field, value)

    def _resolved_field(self, field: str) -> Any:
        """Return one resolved field from this configured component instance."""
        resolved = self.resolved_fields.get(field)
        if resolved is None:
            raise AttributeError(f"unknown field {field!r}")
        return resolved

    def _resolved_write_field(self, field: str) -> Any:
        """Return the resolved writable field used for targeted verification."""
        resolved = self._resolved_field(field)
        if not resolved.field.writable:
            raise AttributeError(f"{field} is read-only")
        return resolved

    @staticmethod
    def _signed_word(word: int) -> int:
        """Decode one 16-bit register word as a signed integer."""
        return word - 0x10000 if word & 0x8000 else word

    async def _read_resolved_field(
        self,
        field: str,
        resolved: Any,
    ) -> tuple[Any, int | None]:
        """Read exactly one resolved field and update its component cache."""
        descriptor = resolved.field

        if isinstance(descriptor, RegisterField):
            scale_exponent: int | None = None
            if resolved.scale_address is not None:
                (scale_word,) = await self._unit.read_holding_registers(
                    resolved.scale_address,
                    1,
                )
                scale_exponent = self._signed_word(scale_word)

            words = await self._unit.read_holding_registers(
                resolved.address,
                descriptor.count,
            )
            actual = descriptor.decode(words, scale_exponent)
            self._values[field] = actual
            return actual, scale_exponent

        (bit,) = await self._unit.read_coils(resolved.address, 1)
        actual = descriptor.decode([bit])
        self._bits[field] = actual
        return actual, None

    async def _read_datapoint_now(
        self,
        field: str,
    ) -> tuple[Any, int | None]:
        """Read one configured datapoint regardless of its writability."""
        return await self._read_resolved_field(field, self._resolved_field(field))

    async def _read_field_for_verification(
        self,
        field: str,
    ) -> tuple[Any, int | None]:
        """Read one writable field for generic targeted verification."""
        return await self._read_resolved_field(
            field,
            self._resolved_write_field(field),
        )

    async def _read_ebene_state(self, field: str) -> bool | None:
        """Read the override/Ebene coil for a field, if it has one."""
        override = self.ebene_coils.get(field)
        if override is None:
            return None

        address, stride = override
        resolved_address = coil_address(address + stride * (self._index - 1))
        (state,) = await self._unit.read_coils(resolved_address, 1)
        return bool(state)

    def _normalized_expected_value(
        self,
        field: str,
        value: Any,
        scale_exponent: int | None,
    ) -> Any:
        """Normalize a requested value through the field's own encode/decode path."""
        resolved = self._resolved_write_field(field)
        descriptor = resolved.field
        normalized = (
            descriptor.writable(value) if callable(descriptor.writable) else value
        )

        if isinstance(descriptor, RegisterField):
            try:
                return descriptor.decode(
                    descriptor.encode(normalized, scale_exponent),
                    scale_exponent,
                )
            except NotImplementedError:
                return normalized

        return bool(normalized)

    async def _verify_written_datapoint(self, field: str, value: Any) -> bool:
        """Read back one datapoint and any required Ebene state."""
        override = self.ebene_coils.get(field)
        autark_value = self.ebene_autark_values.get(field, object())

        if override is not None:
            ebene_state = await self._read_ebene_state(field)
            expected_ebene = LEVEL_AUTARK if value == autark_value else LEVEL_GLT
            if ebene_state is not expected_ebene:
                return False

            if value == autark_value:
                # In AUTARK-like generic overrides the register is deliberately
                # left untouched. Cache the logical requested value after the
                # override coil itself was verified; the next poll remains
                # authoritative.
                resolved = self._resolved_write_field(field)
                if isinstance(resolved.field, RegisterField):
                    self._values[field] = value
                else:
                    self._bits[field] = bool(value)
                return True

        actual, scale_exponent = await self._read_field_for_verification(field)
        expected = self._normalized_expected_value(field, value, scale_exponent)
        return actual == expected

    def _pump_control_mode(
        self,
        output_field: str,
        ownership_field: str,
    ) -> PumpControlMode | None:
        """Return AUTO/ON/OFF from one pump output and its ownership coil."""
        ownership = getattr(self, ownership_field, None)
        if ownership is LEVEL_AUTARK:
            return PumpControlMode.AUTO
        if ownership is not LEVEL_GLT:
            return None

        running = getattr(self, output_field, None)
        if running is None:
            return None
        return PumpControlMode.ON if running else PumpControlMode.OFF

    async def _wait_for_pump_control_state(
        self,
        output_field: str,
        ownership_field: str,
        requested: PumpControlMode,
    ) -> tuple[bool, PumpControlMode | None, ModbusTimeoutError | None]:
        """Poll one pump setting while output and ownership settle."""
        started = monotonic()
        actual: PumpControlMode | None = None
        last_timeout: ModbusTimeoutError | None = None

        while True:
            try:
                ownership, _ = await self._read_datapoint_now(ownership_field)
                if ownership is LEVEL_AUTARK:
                    actual = PumpControlMode.AUTO
                elif ownership is LEVEL_GLT:
                    running, _ = await self._read_datapoint_now(output_field)
                    actual = PumpControlMode.ON if running else PumpControlMode.OFF
                else:
                    actual = None
            except ModbusTimeoutError as err:
                last_timeout = err
                actual = None
            except ModbusError:
                raise

            if actual is requested:
                return True, actual, last_timeout

            elapsed = monotonic() - started
            remaining = PUMP_CONTROL_VERIFY_TIMEOUT - elapsed
            if remaining <= 0:
                return False, actual, last_timeout
            await asyncio.sleep(min(PUMP_CONTROL_VERIFY_INTERVAL, remaining))

    async def _async_set_pump_control_mode(
        self,
        output_field: str,
        ownership_field: str,
        mode: PumpControlMode | str,
        *,
        access_code: int = DEFAULT_WRITE_ACCESS_CODE,
    ) -> None:
        """Set AUTO/ON/OFF for one binary pump output and verify ownership.

        AUTO writes only the pump ownership coil to AUTARK. ON and OFF write
        only the actual output coil. A direct output write is expected to move
        ownership to GLT itself; explicit ownership=GLT pre-writes are avoided.
        """
        try:
            requested = PumpControlMode(mode)
        except (TypeError, ValueError) as err:
            raise TrovisValueValidationError(
                f"Unsupported TROVIS pump control mode: {mode!r}"
            ) from err

        output = self._resolved_write_field(output_field)
        ownership = self._resolved_field(ownership_field)
        await async_ensure_writing_enabled(self._unit, access_code)

        if requested is PumpControlMode.AUTO:
            target_address = ownership.address
            target_value = LEVEL_AUTARK
        else:
            target_address = output.address
            target_value = requested is PumpControlMode.ON

        last_timeout: ModbusTimeoutError | None = None
        last_actual = self._pump_control_mode(output_field, ownership_field)

        for attempt in range(WRITE_RETRIES + 1):
            write_timed_out = False
            try:
                await self._unit.write_coil(target_address, target_value)
            except ModbusTimeoutError as err:
                last_timeout = err
                write_timed_out = True
            except ModbusError:
                raise

            (
                verified,
                last_actual,
                verification_timeout,
            ) = await self._wait_for_pump_control_state(
                output_field,
                ownership_field,
                requested,
            )
            if verification_timeout is not None:
                last_timeout = verification_timeout

            if verified:
                if requested is PumpControlMode.AUTO:
                    try:
                        await self._read_datapoint_now(output_field)
                    except ModbusError:
                        pass
                return

            # An acknowledged write is not repeated merely because the
            # controller did not enter the requested ownership/state.
            if not write_timed_out or attempt >= WRITE_RETRIES:
                break

        message = (
            "Could not verify TROVIS pump control change "
            f"{output_field!r} to {requested.value!r} within "
            f"{PUMP_CONTROL_VERIFY_TIMEOUT:.1f}s "
            f"(actual={getattr(last_actual, 'value', last_actual)})"
        )
        if last_timeout is not None:
            raise TrovisWriteVerificationError(message) from last_timeout
        raise TrovisWriteVerificationError(message)

    async def _write_datapoint_verified(self, field: str, value: Any) -> None:
        """Write one normal state value and verify it before any retry.

        A timeout on the write response does not immediately cause another
        write. The requested datapoint is read back first because the controller
        may already have applied the value. Only if the readback does not match
        (or itself times out) is the logical write attempted again.
        """
        last_timeout: ModbusTimeoutError | None = None

        for attempt in range(WRITE_RETRIES + 1):
            # Keep only the failure context from the current/final logical attempt.
            # A timeout from an earlier attempt must not mask a later plain mismatch.
            last_timeout = None
            readback_timed_out = False
            try:
                await self.write(field, value)
            except ModbusTimeoutError as err:
                last_timeout = err
                _LOGGER.debug(
                    "TROVIS write %s timed out on attempt %d/%d; "
                    "verifying before retrying",
                    field,
                    attempt + 1,
                    WRITE_RETRIES + 1,
                )
            except ModbusError:
                raise

            try:
                verified = await self._verify_written_datapoint(field, value)
            except ModbusTimeoutError as err:
                last_timeout = err
                readback_timed_out = True
                verified = False
                _LOGGER.debug(
                    "TROVIS write %s readback timed out on attempt %d/%d",
                    field,
                    attempt + 1,
                    WRITE_RETRIES + 1,
                )
            except ModbusError:
                raise

            if verified:
                if attempt:
                    _LOGGER.debug(
                        "TROVIS write %s verified on attempt %d/%d",
                        field,
                        attempt + 1,
                        WRITE_RETRIES + 1,
                    )
                return

            if not readback_timed_out:
                _LOGGER.debug(
                    "TROVIS write %s readback mismatch on attempt %d/%d",
                    field,
                    attempt + 1,
                    WRITE_RETRIES + 1,
                )

        message = (
            f"Could not verify TROVIS write {field!r} after "
            f"{WRITE_RETRIES + 1} attempts"
        )
        if last_timeout is not None:
            raise TrovisWriteVerificationError(message) from last_timeout
        raise TrovisWriteVerificationError(message)

    def _validated_operating_mode(self, value: Any) -> OperatingMode:
        """Return a remotely writable operating mode for this component."""
        try:
            mode = OperatingMode(value)
        except (TypeError, ValueError) as err:
            raise TrovisValueValidationError(
                f"Unsupported TROVIS operating mode: {value!r}"
            ) from err

        metadata = self.require_metadata_for("mode")
        if metadata.enum is None:
            raise TrovisValueValidationError(
                "TROVIS operating-mode metadata is unavailable"
            )
        allowed_values = {int(option.value) for option in metadata.enum.options}
        if int(mode) not in allowed_values:
            raise TrovisValueValidationError(
                f"Operating mode {mode.name} is not remotely writable for this circuit"
            )
        return mode

    def _operating_mode_log_context(self) -> tuple[str, str, str, str]:
        """Return human-readable Rk/register labels for operating-mode logs."""
        mode = self._resolved_field("mode")
        active = self._resolved_field("active_mode")
        ownership = self._resolved_field("mode_control_autonomous")

        command_hr = mode.address + 40001
        active_hr = active.address + 40001
        ownership_cl = ownership.address + 1
        label = {
            40106: "Rk1",
            40108: "Rk2",
            40110: "Rk3",
            40112: "Rk4",
        }.get(command_hr, type(self).__name__)
        return (
            label,
            f"HR{command_hr}",
            f"HR{active_hr}",
            f"CL{ownership_cl}",
        )

    @staticmethod
    def _ownership_name(value: Any) -> str:
        """Return a readable GLT/AUTARK label for logging."""
        if value is LEVEL_AUTARK:
            return "AUTARK"
        if value is LEVEL_GLT:
            return "GLT"
        return "unknown"

    async def _refresh_operating_mode_ownership(self) -> bool | None:
        """Refresh and log the mode ownership cache without changing success."""
        label, _, _, ownership_cl = self._operating_mode_log_context()
        try:
            state, _ = await self._read_datapoint_now("mode_control_autonomous")
        except ModbusError as err:
            _LOGGER.info(
                "%s operating-mode ownership refresh failed at %s: %s",
                label,
                ownership_cl,
                err,
            )
            return None

        _LOGGER.info(
            "%s operating-mode ownership: %s=%s",
            label,
            ownership_cl,
            self._ownership_name(state),
        )
        return state

    async def _wait_for_active_operating_mode(
        self,
        requested: OperatingMode,
    ) -> tuple[bool, Any, ModbusTimeoutError | None]:
        """Poll effective mode while the controller settles after one command write."""
        label, _, active_hr, _ = self._operating_mode_log_context()
        started = monotonic()
        poll = 0
        actual: Any = None
        last_timeout: ModbusTimeoutError | None = None

        while True:
            poll += 1
            try:
                actual, _ = await self._read_datapoint_now("active_mode")
            except ModbusTimeoutError as err:
                last_timeout = err
                actual = None
                elapsed = monotonic() - started
                _LOGGER.info(
                    "%s operating-mode verification poll %d at %.2fs: "
                    "%s read timed out while waiting for %s",
                    label,
                    poll,
                    elapsed,
                    active_hr,
                    requested.name,
                )
            except ModbusError:
                raise
            else:
                elapsed = monotonic() - started
                if actual == requested:
                    _LOGGER.info(
                        "%s operating-mode verified: requested=%s actual=%s "
                        "via %s after %.2fs (%d poll%s)",
                        label,
                        requested.name,
                        requested.name,
                        active_hr,
                        elapsed,
                        poll,
                        "" if poll == 1 else "s",
                    )
                    return True, actual, last_timeout

                _LOGGER.info(
                    "%s operating-mode settling: requested=%s actual=%s "
                    "via %s after %.2fs (poll %d)",
                    label,
                    requested.name,
                    getattr(actual, "name", actual),
                    active_hr,
                    elapsed,
                    poll,
                )

            elapsed = monotonic() - started
            remaining = OPERATING_MODE_VERIFY_TIMEOUT - elapsed
            if remaining <= 0:
                return False, actual, last_timeout
            await asyncio.sleep(min(OPERATING_MODE_VERIFY_INTERVAL, remaining))

    async def _wait_for_operating_mode_ownership(
        self,
        expected: bool,
    ) -> tuple[bool, Any, ModbusTimeoutError | None]:
        """Poll the ownership coil while an AUTARK/GLT transition settles."""
        label, _, _, ownership_cl = self._operating_mode_log_context()
        started = monotonic()
        poll = 0
        state: Any = None
        last_timeout: ModbusTimeoutError | None = None

        while True:
            poll += 1
            try:
                state, _ = await self._read_datapoint_now("mode_control_autonomous")
            except ModbusTimeoutError as err:
                last_timeout = err
                state = None
                elapsed = monotonic() - started
                _LOGGER.info(
                    "%s operating-mode ownership verification poll %d at %.2fs: "
                    "%s read timed out while waiting for %s",
                    label,
                    poll,
                    elapsed,
                    ownership_cl,
                    self._ownership_name(expected),
                )
            except ModbusError:
                raise
            else:
                elapsed = monotonic() - started
                if state is expected:
                    _LOGGER.info(
                        "%s operating-mode ownership verified: %s=%s after "
                        "%.2fs (%d poll%s)",
                        label,
                        ownership_cl,
                        self._ownership_name(state),
                        elapsed,
                        poll,
                        "" if poll == 1 else "s",
                    )
                    return True, state, last_timeout

                _LOGGER.info(
                    "%s operating-mode ownership settling: requested=%s "
                    "actual=%s via %s after %.2fs (poll %d)",
                    label,
                    self._ownership_name(expected),
                    self._ownership_name(state),
                    ownership_cl,
                    elapsed,
                    poll,
                )

            elapsed = monotonic() - started
            remaining = OPERATING_MODE_VERIFY_TIMEOUT - elapsed
            if remaining <= 0:
                return False, state, last_timeout
            await asyncio.sleep(min(OPERATING_MODE_VERIFY_INTERVAL, remaining))

    async def async_set_operating_mode(
        self,
        mode: OperatingMode | int,
        *,
        access_code: int = DEFAULT_WRITE_ACCESS_CODE,
    ) -> None:
        """Set an external operating mode and verify the effective mode.

        The controller's command register and effective-mode register are
        intentionally different. A valid external write switches ownership to
        GLT itself, so no ownership coil is written before the command. The
        command register is also not used for verification because real TROVIS
        controllers may normalize its readback.

        A successful command write is sent exactly once. ``active_mode`` is
        then polled while the controller settles. Only a lost write response
        can cause a command retry, and even then the effective mode is checked
        for the complete settling window before another write is sent.
        """
        requested = self._validated_operating_mode(mode)
        label, command_hr, active_hr, ownership_cl = self._operating_mode_log_context()
        active_before = getattr(self, "active_mode", None)
        ownership_before = getattr(self, "mode_control_autonomous", None)

        _LOGGER.info(
            "%s operating-mode change requested: target=%s; active_before=%s; "
            "ownership_before=%s; command=%s; verify=%s; ownership=%s",
            label,
            requested.name,
            getattr(active_before, "name", active_before),
            self._ownership_name(ownership_before),
            command_hr,
            active_hr,
            ownership_cl,
        )

        await async_ensure_writing_enabled(self._unit, access_code)
        _LOGGER.info("%s operating-mode write access confirmed", label)

        last_timeout: ModbusTimeoutError | None = None
        last_actual: Any = active_before

        for attempt in range(WRITE_RETRIES + 1):
            write_timed_out = False
            write_started = monotonic()
            try:
                # Bypass TrovisComponent.write(): operating-mode ownership must
                # not receive the generic Ebene=GLT prewrite.
                await super().write("mode", requested)
            except ModbusTimeoutError as err:
                last_timeout = err
                write_timed_out = True
                _LOGGER.info(
                    "%s operating-mode command %s=%s timed out on write "
                    "attempt %d/%d after %.2fs; polling %s before any retry",
                    label,
                    command_hr,
                    requested.name,
                    attempt + 1,
                    WRITE_RETRIES + 1,
                    monotonic() - write_started,
                    active_hr,
                )
            except ModbusError:
                raise
            else:
                _LOGGER.info(
                    "%s operating-mode command written: %s=%s on attempt %d/%d "
                    "in %.2fs",
                    label,
                    command_hr,
                    requested.name,
                    attempt + 1,
                    WRITE_RETRIES + 1,
                    monotonic() - write_started,
                )

            (
                verified,
                last_actual,
                verification_timeout,
            ) = await self._wait_for_active_operating_mode(requested)
            if verification_timeout is not None:
                last_timeout = verification_timeout

            if verified:
                ownership = await self._refresh_operating_mode_ownership()
                _LOGGER.info(
                    "%s operating-mode change complete: active=%s; ownership=%s",
                    label,
                    requested.name,
                    self._ownership_name(ownership),
                )
                return

            if not write_timed_out:
                _LOGGER.warning(
                    "%s operating-mode command %s=%s was acknowledged, but %s "
                    "remained %s after %.1fs; command will not be repeated",
                    label,
                    command_hr,
                    requested.name,
                    active_hr,
                    getattr(last_actual, "name", last_actual),
                    OPERATING_MODE_VERIFY_TIMEOUT,
                )
                break

            if attempt < WRITE_RETRIES:
                _LOGGER.info(
                    "%s operating-mode write response was lost and target did "
                    "not become effective within %.1fs; retrying command (%d/%d)",
                    label,
                    OPERATING_MODE_VERIFY_TIMEOUT,
                    attempt + 2,
                    WRITE_RETRIES + 1,
                )

        message = (
            f"Could not verify {label} TROVIS operating-mode write through "
            f"active_mode within {OPERATING_MODE_VERIFY_TIMEOUT:.1f}s "
            f"(requested={requested.name}, "
            f"actual={getattr(last_actual, 'name', last_actual)})"
        )
        if last_timeout is not None:
            raise TrovisWriteVerificationError(message) from last_timeout
        raise TrovisWriteVerificationError(message)

    async def async_release_operating_mode_control(
        self,
        *,
        access_code: int = DEFAULT_WRITE_ACCESS_CODE,
    ) -> None:
        """Release operating-mode ownership back to the TROVIS controller.

        AUTARK is an ownership state, not ``OperatingMode.AUTOMATIC``. Only the
        circuit's mode-ownership coil is written to 1 and verified. The command
        register is deliberately left untouched.
        """
        label, command_hr, active_hr, ownership_cl = self._operating_mode_log_context()
        active_before = getattr(self, "active_mode", None)
        ownership_before = getattr(self, "mode_control_autonomous", None)
        _LOGGER.info(
            "%s operating-mode AUTARK release requested: active_before=%s; "
            "ownership_before=%s; ownership=%s; command=%s untouched; "
            "active=%s",
            label,
            getattr(active_before, "name", active_before),
            self._ownership_name(ownership_before),
            ownership_cl,
            command_hr,
            active_hr,
        )

        await async_ensure_writing_enabled(self._unit, access_code)
        _LOGGER.info("%s operating-mode write access confirmed", label)
        ownership = self._resolved_field("mode_control_autonomous")

        last_timeout: ModbusTimeoutError | None = None
        last_state: Any = ownership_before

        for attempt in range(WRITE_RETRIES + 1):
            write_timed_out = False
            write_started = monotonic()
            try:
                await self._unit.write_coil(ownership.address, LEVEL_AUTARK)
            except ModbusTimeoutError as err:
                last_timeout = err
                write_timed_out = True
                _LOGGER.info(
                    "%s operating-mode AUTARK write %s=1 timed out on attempt "
                    "%d/%d after %.2fs; verifying ownership before any retry",
                    label,
                    ownership_cl,
                    attempt + 1,
                    WRITE_RETRIES + 1,
                    monotonic() - write_started,
                )
            except ModbusError:
                raise
            else:
                _LOGGER.info(
                    "%s operating-mode AUTARK command written: %s=1 on attempt "
                    "%d/%d in %.2fs",
                    label,
                    ownership_cl,
                    attempt + 1,
                    WRITE_RETRIES + 1,
                    monotonic() - write_started,
                )

            (
                verified,
                last_state,
                verification_timeout,
            ) = await self._wait_for_operating_mode_ownership(LEVEL_AUTARK)
            if verification_timeout is not None:
                last_timeout = verification_timeout

            if verified:
                try:
                    active, _ = await self._read_datapoint_now("active_mode")
                except ModbusError as err:
                    _LOGGER.info(
                        "%s operating-mode AUTARK verified, but %s refresh failed: %s",
                        label,
                        active_hr,
                        err,
                    )
                else:
                    _LOGGER.info(
                        "%s operating-mode AUTARK release complete: "
                        "ownership=AUTARK; active=%s",
                        label,
                        getattr(active, "name", active),
                    )
                return

            if not write_timed_out:
                _LOGGER.warning(
                    "%s operating-mode AUTARK command was acknowledged, but %s "
                    "remained %s after %.1fs; command will not be repeated",
                    label,
                    ownership_cl,
                    self._ownership_name(last_state),
                    OPERATING_MODE_VERIFY_TIMEOUT,
                )
                break

            if attempt < WRITE_RETRIES:
                _LOGGER.info(
                    "%s operating-mode AUTARK write response was lost and "
                    "ownership did not settle within %.1fs; retrying (%d/%d)",
                    label,
                    OPERATING_MODE_VERIFY_TIMEOUT,
                    attempt + 2,
                    WRITE_RETRIES + 1,
                )

        message = (
            f"Could not verify {label} TROVIS AUTARK operating-mode ownership "
            f"within {OPERATING_MODE_VERIFY_TIMEOUT:.1f}s "
            f"(actual={self._ownership_name(last_state)})"
        )
        if last_timeout is not None:
            raise TrovisWriteVerificationError(message) from last_timeout
        raise TrovisWriteVerificationError(message)

    async def async_write_datapoint(
        self,
        field: str,
        value: Any,
        *,
        access_code: int = DEFAULT_WRITE_ACCESS_CODE,
    ) -> bool:
        """Write a TROVIS data point and return whether it was read back.

        Normal state-setting fields are verified by a targeted read and retry
        up to two times on a timeout or mismatch. A ``False`` result is reserved
        for explicitly non-retryable command/trigger fields; callers should then
        keep their normal full-refresh path because no cache-safe verification
        was performed.
        """
        if field == "mode":
            await self.async_set_operating_mode(value, access_code=access_code)
            return True

        await async_ensure_writing_enabled(self._unit, access_code)

        if field in self.non_retryable_write_fields:
            try:
                await self.write(field, value)
            except ModbusTimeoutError as err:
                raise TrovisWriteVerificationError(
                    f"TROVIS command write {field!r} timed out; outcome is "
                    "unknown and the command was deliberately not retried"
                ) from err
            return False

        await self._write_datapoint_verified(field, value)
        return True
