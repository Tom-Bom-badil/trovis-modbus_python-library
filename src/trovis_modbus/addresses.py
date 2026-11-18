"""Address helpers for TROVIS controller references.

Modbus register addresses are commonly written in two different ways:
-   Protocol addresses start at 0. This is the format expected by most
    Modbus libraries.
-   Register references such as 40001 are often used in device manuals.
    These are human-readable reference numbers and are not sent directly
    in a Modbus request.
-   Both address 0 as well as reference 40001 are pointing to the same register.

For the library and sniffer reports, holding-register references always use
one continuous 5-digit convention: HR = 40001 + zero-based PDU address.
This supports PDU addresses 0..59998 without six-digit references:

    HR40001 -> Modbus holding register 0
    HR49999 -> register 9998
    HR50000 -> register 9999
    HR51000 -> register 10999 (HK11-HK13)
    HR52000 -> register 11999 (default sniffer window limit)
    CL1 -> Modbus coil 0, CL2 -> coil 1 ...

Historical SAMSON documents sometimes use a six-digit 4-prefixed ordinal,
e.g. HR411000 for PDU 10999. This is NOT the representation accepted by
``register_address``; use HR51000 instead. The on-wire PDU addresses do not
change. Five-digit notation cannot represent the complete 16-bit PDU space.
"""

from __future__ import annotations

from collections.abc import Iterable

REGISTER_REFERENCE_BASE = 40001
REGISTER_REFERENCE_MAX = 99999  # Highest 5-digit reference; PDU 59998


def register_address(hr_number: int) -> int:
    """Convert a 5-digit HR reference to a zero-based Modbus address.

    The library uses HR = 40001 + PDU, including HR50000..HR99999.
    Six-digit SAMSON ordinals are deliberately not accepted here.
    """
    if isinstance(hr_number, bool) or not isinstance(hr_number, int):
        raise ValueError(f"Invalid TROVIS holding-register reference: {hr_number}")
    if not REGISTER_REFERENCE_BASE <= hr_number <= REGISTER_REFERENCE_MAX:
        raise ValueError(f"Invalid TROVIS holding-register reference: {hr_number}")
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
