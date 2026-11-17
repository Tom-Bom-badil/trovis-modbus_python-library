"""New firmware identity and strict Modbus 0x02 diagnostic contract tests."""

from __future__ import annotations

import pytest
from modbus_connection import IllegalDataAddressError, ModbusTimeoutError, ReadBlock
from modbus_connection.mock import MockModbusUnit

from trovis_modbus import Trovis557x
from trovis_modbus.utils import (
    MAX_DIAGNOSTIC_BLOCK_SIZE,
    async_confirm_illegal_addresses,
    async_read_identity,
    illegal_address_block,
)

from .conftest import HOLDING


async def test_safe_identity_before_first_poll(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    identity = await async_read_identity(mock_modbus_unit)
    assert (identity.model, identity.firmware) == (5579, 305)
    assert len(mock_modbus_unit.read_events) == 2
    assert [(e.address, e.count) for e in mock_modbus_unit.read_events] == [
        (0, 1),
        (2, 1),
    ]
    probe = await Trovis557x.async_probe(mock_modbus_unit)
    assert probe.model == 5579
    assert probe.firmware == 305


async def test_async_factory_rejects_mismatching_identity(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    with pytest.raises(ValueError, match="reconfigure"):
        await Trovis557x.async_create(mock_modbus_unit, model=5578)
    device = await Trovis557x.async_create(mock_modbus_unit, model=5579)
    assert device.firmware_reference == 305


def test_diagnostic_accepts_only_clean_single_space_0x02() -> None:
    block = ReadBlock("holding", 100, 6)
    assert illegal_address_block(IllegalDataAddressError(block=block)) == block
    assert illegal_address_block(ModbusTimeoutError("timeout")) is None
    assert illegal_address_block(IllegalDataAddressError()) is None
    assert (
        illegal_address_block(
            IllegalDataAddressError(
                block=ReadBlock("holding", 0, MAX_DIAGNOSTIC_BLOCK_SIZE + 1)
            )
        )
        is None
    )
    assert (
        illegal_address_block(
            IllegalDataAddressError(block=ReadBlock("discrete", 5, 2))
        )
        is None
    )


async def test_diagnostic_only_excludes_confirmed_addresses() -> None:
    class Unit:
        def __init__(self):
            self.seen = []

        async def read_holding_registers(self, address: int, count: int):
            self.seen.append(("holding", address, count))
            if address in {21, 24}:
                raise IllegalDataAddressError()
            return [0]

        async def read_coils(self, address: int, count: int):
            self.seen.append(("coil", address, count))
            return [False]

    unit = Unit()
    confirmed = await async_confirm_illegal_addresses(unit, ReadBlock("holding", 20, 5))
    assert confirmed == {21, 24}
    assert unit.seen == [("holding", address, 1) for address in range(20, 25)]
    assert not await async_confirm_illegal_addresses(unit, ReadBlock("coil", 50, 2))


async def test_diagnostic_aborts_without_learning_from_timeouts() -> None:
    class Unit:
        async def read_holding_registers(self, address: int, count: int):
            raise ModbusTimeoutError("lost link")

    with pytest.raises(ModbusTimeoutError):
        await async_confirm_illegal_addresses(Unit(), ReadBlock("holding", 0, 2))
