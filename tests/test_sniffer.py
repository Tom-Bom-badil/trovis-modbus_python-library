"""Read-only datapoint sniffer: classification, 0x02, boundaries, errors, cancel."""

from __future__ import annotations

import asyncio

import pytest
from modbus_connection import IllegalDataAddressError, ModbusTimeoutError

from trovis_modbus.addresses import register_address
from trovis_modbus.sniffer import ScanProgress, async_scan_datapoints


class Unit:
    def __init__(
        self,
        *,
        illegal_registers: set[int] | None = None,
        illegal_coils: set[int] | None = None,
        unknown_registers: set[int] | None = None,
        boundary: int | None = None,
    ) -> None:
        self.illegal_registers = illegal_registers or set()
        self.illegal_coils = illegal_coils or set()
        self.unknown_registers = unknown_registers or set()
        self.boundary = boundary
        self.calls: list[tuple[str, int, int]] = []

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        self.calls.append(("holding", address, count))
        if any(a in self.unknown_registers for a in range(address, address + count)):
            raise ModbusTimeoutError("transient device timeout")
        if self.boundary is not None and address < self.boundary < address + count:
            raise IllegalDataAddressError()
        if any(a in self.illegal_registers for a in range(address, address + count)):
            raise IllegalDataAddressError()
        return list(range(address, address + count))

    async def read_coils(self, address: int, count: int) -> list[bool]:
        self.calls.append(("coil", address, count))
        if any(a in self.illegal_coils for a in range(address, address + count)):
            raise IllegalDataAddressError()
        # Some backends return a byte-padded coil response.
        return [False] * (((count + 7) // 8) * 8)


async def test_classify_every_address_and_print_five_digit_hr_references() -> None:
    unit = Unit(illegal_registers={2, 10999}, illegal_coils={0, 4})
    progress: list[ScanProgress] = []
    result = await async_scan_datapoints(
        unit,
        model=5578,
        firmware="2.63",
        hardware="1.00",
        system_code="2.1",
        register_count=11002,
        coil_count=7,
        block_size=32,
        progress=progress.append,
    )
    assert result.status == "Completed"
    assert not result.unknown_registers
    assert not result.unknown_coils
    assert sum(high - low + 1 for low, high in result.register_blocks) == 11000
    assert sum(high - low + 1 for low, high in result.coil_blocks) == 5
    assert any(low <= 11000 <= high for low, high in result.register_blocks)
    assert "(51001," in result.report or "51001" in result.report
    registers = result.report.split("REGISTER_RANGES =", 1)[1].split(
        "COIL_RANGES =", 1
    )[0]
    assert "411000" not in registers
    assert "(51000, 51000)" not in registers
    assert "(2, 4)" in result.report
    assert "(4, 4)" not in result.report
    assert result.report.startswith("# TROVIS 5578 | FW 2.63 | HW 1.00")
    assert result.report.count("\n") == 6
    assert progress[-1].space == "coils" and progress[-1].analyzed == 7
    assert all("write" not in event[0] for event in unit.calls)


async def test_non_02_errors_are_incomplete_not_unreadable() -> None:
    result = await async_scan_datapoints(
        Unit(illegal_registers={1}, unknown_registers={5}),
        model=5579,
        firmware="3.05",
        register_count=8,
        coil_count=3,
        block_size=1,
        retries=1,
    )
    assert result.status == "Incomplete"
    assert result.unknown_registers == ((5, 5),)
    assert "UNKNOWN_REGISTERS = _hr_ranges(" in result.report
    assert "(40006, 40006)" in result.report
    assert not any(low <= 1 <= high for low, high in result.register_blocks)


async def test_failed_combined_read_never_forces_unreadable_single_address() -> None:
    result = await async_scan_datapoints(
        Unit(boundary=3),
        model=5573,
        firmware="2.54",
        register_count=6,
        coil_count=1,
        block_size=6,
    )
    assert result.status == "Completed"
    # The boundary remains, even though both sides are individually readable.
    assert result.register_blocks == ((0, 2), (3, 5))
    assert result.readable_register_ranges == ((0, 5),)
    assert "(40001, 40006)" in result.report
    assert "(40004, 40006)" not in result.report
    assert "NOT proven bulk-read blocks" in result.report


async def test_rejected_single_addresses_are_not_errors() -> None:
    result = await async_scan_datapoints(
        Unit(illegal_registers={0, 1, 2}, illegal_coils={0, 1}),
        model=5573,
        firmware="2.63",
        register_count=3,
        coil_count=2,
        block_size=2,
    )
    assert result.status == "Completed"
    assert result.register_blocks == ()
    assert result.coil_blocks == ()


async def test_cancellation_is_not_swallowed() -> None:
    entered = asyncio.Event()

    class HangingUnit(Unit):
        async def read_holding_registers(self, address: int, count: int) -> list[int]:
            entered.set()
            await asyncio.sleep(3600)
            return [0] * count

    task = asyncio.create_task(
        async_scan_datapoints(
            HangingUnit(),
            model=5578,
            firmware="2.63",
            register_count=4,
            coil_count=4,
        )
    )
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.parametrize("invalid", [0, 60000, 65536, 65537, -1])
async def test_invalid_scan_windows_are_rejected(invalid: int) -> None:
    with pytest.raises(ValueError):
        await async_scan_datapoints(
            Unit(), model=5573, firmware="2.63", register_count=invalid
        )


def test_five_digit_hr_conversion_preserves_old_references() -> None:
    assert register_address(40001) == 0
    assert register_address(49999) == 9998
    assert register_address(50000) == 9999
    assert register_address(50272) == 10271
    assert register_address(50500) == 10499
    assert register_address(51000) == 10999
    assert register_address(51372) == 11371
    assert register_address(52000) == 11999
    assert register_address(99999) == 59998
    for invalid in (40000, 410000, 411000, 412000, 465536, 100000, True):
        with pytest.raises(ValueError):
            register_address(invalid)


def test_all_scanned_five_digit_hr_references_are_roundtrip_safe() -> None:
    for address in range(12000):
        assert register_address(40001 + address) == address


def test_compact_report_uses_only_five_digit_references() -> None:
    from trovis_modbus.sniffer import AddressScanResult

    result = AddressScanResult(
        model=5578,
        firmware="2.63",
        hardware="1.00",
        system_code="6.1",
        register_blocks=((6469, 10271), (10499, 10559), (10999, 11039)),
        coil_blocks=(),
        unknown_registers=((11299, 11371),),
        unknown_coils=(),
        register_count=12000,
        coil_count=10000,
        requests=26082,
        elapsed_seconds=3262.4,
        timestamp_utc="2026-11-17T23:07:21+00:00",
        library_version="3.1.3",
    )
    report = result.report
    assert "(46470, 50272)" in report
    assert "(50500, 50560)" in report
    assert "(51000, 51040)" in report
    assert "(51300, 51372)" in report
    assert "411000" not in report


async def test_version_metadata_lookup_runs_off_event_loop(monkeypatch) -> None:
    """HA rejects importlib.metadata disk reads directly in its event loop."""
    import threading

    from trovis_modbus import sniffer

    caller = threading.current_thread()
    invoked: list[threading.Thread] = []

    def fake_version(_name: str) -> str:
        invoked.append(threading.current_thread())
        return "test-version"

    monkeypatch.setattr(sniffer, "version", fake_version)
    result = await async_scan_datapoints(
        Unit(), model=5578, firmware="2.63", register_count=1, coil_count=1
    )
    assert invoked and invoked[0] is not caller
    assert "trovis-modbus test-version" in result.report
