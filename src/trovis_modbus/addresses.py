"""Address helpers for TROVIS manufacturer references.

Modbus register addresses are commonly written in two different ways:
-   Protocol addresses start at 0. This is the format expected by most
    Modbus libraries.
-   Register references such as 40001 are often used in device manuals.
    These are human-readable reference numbers and are not sent directly
    in a Modbus request.
-   Both address 0 as well as reference 40001 are pointing to the same register.

The TROVIS manufacturer documentation uses its own labels, for example:
-   HR40102 for a holding register
-   CL137 for a coil

This module converts these manufacturer references into the zero-based
protocol addresses expected by the Modbus library. This allows the component
definitions to use the same references as the TROVIS documentation:

-   Examples:
    HR40001 -> Modbus holding register 0, HR40002 -> register 1 ...
    CL1 -> Modbus coil 0, CL2 -> coil 1 ...
"""

from __future__ import annotations

from collections.abc import Iterable

REGISTER_REFERENCE_BASE = 40001
REGISTER_REFERENCE_MAX = 49999


def register_address(hr_number: int) -> int:
    """Return the zero-based Modbus address for a TROVIS HR reference."""
    if hr_number < REGISTER_REFERENCE_BASE or hr_number > REGISTER_REFERENCE_MAX:
        raise ValueError(
            f"Expected TROVIS holding-register reference like 40102, got {hr_number}"
        )
    return hr_number - REGISTER_REFERENCE_BASE


def coil_address(cl_number: int) -> int:
    """Return the zero-based Modbus address for a TROVIS CL number."""
    if cl_number < 1:
        raise ValueError(f"Invalid TROVIS coil number: {cl_number}")
    return cl_number - 1


def hr_range(start_hr: int, end_hr: int) -> tuple[int, int]:
    """Create an inclusive readable register range from HR references."""
    if end_hr < start_hr:
        raise ValueError(f"Invalid TROVIS register range: {start_hr}..{end_hr}")
    return register_address(start_hr), register_address(end_hr)


def cl_range(start_cl: int, end_cl: int) -> tuple[int, int]:
    """Create an inclusive readable coil range from CL references."""
    if end_cl < start_cl:
        raise ValueError(f"Invalid TROVIS coil range: {start_cl}..{end_cl}")
    return coil_address(start_cl), coil_address(end_cl)


# --- Validated per-device excluded address handling ------------------------

MODBUS_ADDRESS_MIN = 0
MODBUS_ADDRESS_MAX = 0xFFFF

AddressRange = tuple[int, int]
AddressRanges = tuple[AddressRange, ...]


def normalize_excluded_addresses(addresses: Iterable[int]) -> frozenset[int]:
    """Return validated zero-based Modbus addresses."""
    normalized: set[int] = set()

    for address in addresses:
        if isinstance(address, bool) or not isinstance(address, int):
            raise ValueError("excluded Modbus addresses must be integers")
        if not MODBUS_ADDRESS_MIN <= address <= MODBUS_ADDRESS_MAX:
            raise ValueError(
                "excluded Modbus addresses must be in range "
                f"{MODBUS_ADDRESS_MIN}..{MODBUS_ADDRESS_MAX}"
            )
        normalized.add(address)

    return frozenset(normalized)


def ranges_excluding_addresses(
    ranges: AddressRanges,
    excluded_addresses: frozenset[int],
) -> AddressRanges:
    """Split inclusive readable ranges around excluded zero-based addresses."""
    if not excluded_addresses:
        return ranges

    excluded = sorted(excluded_addresses)
    result: list[AddressRange] = []

    for low, high in ranges:
        start = low

        for address in excluded:
            if address < start:
                continue
            if address > high:
                break

            if start < address:
                result.append((start, address - 1))
            start = address + 1

        if start <= high:
            result.append((start, high))

    return tuple(result)
