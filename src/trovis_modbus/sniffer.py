"""Read-only TROVIS FC03/FC01 address discovery, independent of model read maps.

A successful block read proves readability of every address inside that block.
A genuine 0x02 response triggers bisection; only a rejected single-address
request proves an address unreadable. Other errors remain *unknown*.

The short report merges adjacent readable addresses for sharing. Do NOT feed
those merged ranges into a pooled read plan: ``register_blocks`` / ``coil_blocks``
retain the exact independently successful requests for future analysis.
"""

from __future__ import annotations

from asyncio import to_thread
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from time import monotonic
from typing import Literal, Protocol

from modbus_connection import ModbusError, ModbusExceptionError

ScanSpace = Literal["registers", "coils"]
AddressRange = tuple[int, int]

REGISTER_COUNT = 12_000  # HR40001..HR52000 (includes HK11/HK12/HK13)
COIL_COUNT = 10_000  # CL1..CL10000
DEFAULT_BLOCK_SIZE = 32


class ReadOnlyModbusUnit(Protocol):
    """Subset of the existing consumer-local ModbusUnit used for FC03/FC01."""

    async def read_holding_registers(self, address: int, count: int) -> list[int]: ...

    async def read_coils(self, address: int, count: int) -> list[bool]: ...


@dataclass(frozen=True)
class ScanProgress:
    """Number of uniquely classified addresses in the active scan phase."""

    space: ScanSpace
    analyzed: int
    total: int
    requests: int


@dataclass(frozen=True)
class AddressScanResult:
    """One completed two-space scan; no Modbus values or personal IDs."""

    model: int
    firmware: str
    hardware: str | None
    system_code: str | None
    register_blocks: tuple[AddressRange, ...]
    coil_blocks: tuple[AddressRange, ...]
    unknown_registers: tuple[AddressRange, ...]
    unknown_coils: tuple[AddressRange, ...]
    register_count: int
    coil_count: int
    requests: int
    elapsed_seconds: float
    timestamp_utc: str
    library_version: str

    @property
    def status(self) -> Literal["Completed", "Incomplete"]:
        """An invalid/unreadable address is NOT an incomplete scan."""
        if self.unknown_registers or self.unknown_coils:
            return "Incomplete"
        return "Completed"

    @property
    def readable_register_ranges(self) -> tuple[AddressRange, ...]:
        """Contiguous readable addresses, NOT guaranteed safe bulk-read blocks."""
        return _merge_contiguous(self.register_blocks)

    @property
    def readable_coil_ranges(self) -> tuple[AddressRange, ...]:
        """Contiguous readable addresses, NOT guaranteed safe bulk-read blocks."""
        return _merge_contiguous(self.coil_blocks)

    @property
    def report(self) -> str:
        """Compact, copyable GitHub report; preserve tested blocks separately."""
        lines = [
            (
                f"# TROVIS {self.model} | FW {self.firmware} | "
                f"HW {self.hardware or 'unknown'} | "
                f"System {self.system_code or 'unknown'} | {self.status}"
            ),
            (
                f"# UTC {self.timestamp_utc} | "
                f"Scanned HR {self.register_count}, CL {self.coil_count} | "
                f"Reads {self.requests} | {self.elapsed_seconds:.1f} s | "
                f"trovis-modbus {self.library_version}"
            ),
            (
                "# Readable address spans only; merged spans are "
                "NOT proven bulk-read blocks."
            ),
            (
                "# For registers >= 50.000, add 360.000 to get the "
                "original SAMSON address."
            ),
            _format_ranges(
                "REGISTER_RANGES",
                "_hr_ranges",
                self.readable_register_ranges,
                hr=True,
            ),
            _format_ranges(
                "COIL_RANGES",
                "_cl_ranges",
                self.readable_coil_ranges,
                hr=False,
            ),
        ]
        if self.unknown_registers or self.unknown_coils:
            lines.append(
                "# Unresolved (communication failure, NOT confirmed unreadable):"
            )
            lines.append(
                _format_ranges(
                    "UNKNOWN_REGISTERS",
                    "_hr_ranges",
                    self.unknown_registers,
                    hr=True,
                )
            )
            lines.append(
                _format_ranges(
                    "UNKNOWN_COILS",
                    "_cl_ranges",
                    self.unknown_coils,
                    hr=False,
                )
            )
        return "\n".join(lines) + "\n"


def _format_ranges(
    label: str, constructor: str, ranges: tuple[AddressRange, ...], *, hr: bool
) -> str:
    """Print 5-digit HR references (40001 + PDU) or one-based coils."""

    def reference(address: int) -> str:
        return str(40001 + address) if hr else str(address + 1)

    pairs = ", ".join(f"({reference(low)}, {reference(high)})" for low, high in ranges)
    return f"{label} = {constructor}({pairs})"


def _merge_contiguous(ranges: Iterable[AddressRange]) -> tuple[AddressRange, ...]:
    """Merge adjacent readable addresses for the report, not for read plans."""
    merged: list[AddressRange] = []
    for low, high in sorted(ranges):
        if merged and low <= merged[-1][1] + 1:
            merged[-1] = merged[-1][0], max(high, merged[-1][1])
        else:
            merged.append((low, high))
    return tuple(merged)


async def async_scan_datapoints(
    unit: ReadOnlyModbusUnit,
    *,
    model: int,
    firmware: str,
    hardware: str | None = None,
    system_code: str | None = None,
    register_count: int = REGISTER_COUNT,
    coil_count: int = COIL_COUNT,
    block_size: int = DEFAULT_BLOCK_SIZE,
    retries: int = 2,
    progress: Callable[[ScanProgress], None] | None = None,
) -> AddressScanResult:
    """Probe FC03 then FC01, without reading values into the report or writing.

    Each address within the configured 0-based windows is classified exactly
    once. Exceptions other than Modbus 0x02 are retried and become unresolved.
    ``retries`` is additional to any retries already supplied by the unit.
    Cancellation propagates to the caller; the HA coordinator owns cleanup.
    """
    if not 1 <= register_count <= 59999:
        raise ValueError("register_count must be 1..59999 for five-digit HR references")
    if not 1 <= coil_count <= 0x10000:
        raise ValueError("coil_count must be 1..65536")
    if not 1 <= block_size <= 125:
        raise ValueError("block_size must be 1..125")
    if not 0 <= retries <= 5:
        raise ValueError("retries must be 0..5")

    started = monotonic()
    requests = 0

    async def scan_one_space(
        space: ScanSpace, total: int
    ) -> tuple[tuple[AddressRange, ...], tuple[AddressRange, ...]]:
        nonlocal requests
        read = unit.read_holding_registers if space == "registers" else unit.read_coils
        found: list[AddressRange] = []
        unknown: list[AddressRange] = []
        analyzed = 0

        def update() -> None:
            if progress is not None:
                progress(ScanProgress(space, analyzed, total, requests))

        update()
        for offset in range(0, total, block_size):
            count = min(block_size, total - offset)
            # Stack is LIFO: push upper half first to visit ascending addresses.
            pending = [(offset, count)]
            while pending:
                address, n = pending.pop()
                outcome = "unknown"
                for _ in range(retries + 1):
                    requests += 1
                    try:
                        values = await read(address, n)
                        if len(values) < n or (
                            space == "registers" and len(values) != n
                        ):
                            # An incomplete successful response is not proof.
                            outcome = "unknown"
                            continue
                    except ModbusExceptionError as error:
                        if error.exception_code == 0x02:
                            outcome = "illegal"
                            break
                        outcome = "unknown"
                        continue
                    except (ModbusError, OSError, TimeoutError):
                        outcome = "unknown"
                        continue
                    else:
                        outcome = "readable"
                        break

                if outcome == "illegal" and n > 1:
                    lower = n // 2
                    pending.append((address + lower, n - lower))
                    pending.append((address, lower))
                    continue
                if outcome == "readable":
                    found.append((address, address + n - 1))
                elif outcome == "unknown":
                    unknown.append((address, address + n - 1))
                analyzed += n
                update()
        return tuple(found), _merge_contiguous(unknown)

    register_blocks, unknown_registers = await scan_one_space(
        "registers", register_count
    )
    coil_blocks, unknown_coils = await scan_one_space("coils", coil_count)
    try:
        # Importlib metadata traverses dist-info on disk: never run on HA loop.
        installed_version = await to_thread(version, "trovis-modbus")
    except PackageNotFoundError:
        installed_version = "unknown"
    return AddressScanResult(
        model=model,
        firmware=firmware,
        hardware=hardware,
        system_code=system_code,
        register_blocks=register_blocks,
        coil_blocks=coil_blocks,
        unknown_registers=unknown_registers,
        unknown_coils=unknown_coils,
        register_count=register_count,
        coil_count=coil_count,
        requests=requests,
        elapsed_seconds=monotonic() - started,
        timestamp_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        library_version=installed_version,
    )
