"""New firmware identity and strict Modbus 0x02 diagnostic contract tests."""

from __future__ import annotations

import pytest
from modbus_connection import IllegalDataAddressError, ModbusTimeoutError, ReadBlock
from modbus_connection.mock import MockModbusUnit

from trovis_modbus import ModelCorrection, Trovis557x
from trovis_modbus.configurations import get_model_definition_for_reported_model
from trovis_modbus.utils import (
    MAX_DIAGNOSTIC_BLOCK_SIZE,
    async_confirm_illegal_addresses,
    async_read_identity,
    illegal_address_block,
)

from .conftest import HOLDING


@pytest.mark.parametrize(
    ("reported_model", "firmware", "expected_model"),
    (
        (5578, 265, 5578),
        (5578, 266, 55781),
        (5578, 305, 55781),
        (55781, 266, 55781),
        (5579, 305, 5579),
    ),
)
async def test_probe_resolves_model_before_sensor_discovery(
    mock_modbus_unit: MockModbusUnit,
    reported_model: int,
    firmware: int,
    expected_model: int,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding.update({0: reported_model, 2: firmware})

    probe = await Trovis557x.async_probe(mock_modbus_unit)

    assert probe.model == expected_model
    assert probe.firmware == firmware
    assert ("ae1" in probe.detected_sensors) == (expected_model == 55781)


@pytest.mark.parametrize(
    ("firmware", "expected_model"), ((265, 5578), (266, 55781), (305, 55781))
)
async def test_factory_uses_resolved_model(
    mock_modbus_unit: MockModbusUnit, firmware: int, expected_model: int
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding.update({0: 5578, 2: firmware})

    device = await Trovis557x.async_create(mock_modbus_unit)

    assert device.model == expected_model
    assert device.model_definition is get_model_definition_for_reported_model(
        expected_model
    )
    assert device.firmware_reference == firmware
    assert [(e.address, e.count) for e in mock_modbus_unit.read_events] == [
        (0, 1),
        (2, 1),
    ]


@pytest.mark.parametrize(("firmware", "expected_model"), ((266, 55781), (267, 5576)))
async def test_probe_and_factory_share_caller_overrides(
    mock_modbus_unit: MockModbusUnit, firmware: int, expected_model: int
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding.update({0: 5578, 2: firmware})
    overrides = (
        ModelCorrection(reported_model=5578, minimum_firmware=267, model=5576),
    )

    probe = await Trovis557x.async_probe(mock_modbus_unit, model_overrides=overrides)
    device = await Trovis557x.async_create(
        mock_modbus_unit, model=probe.model, model_overrides=overrides
    )

    assert probe.model == device.model == expected_model
    assert probe.firmware == device.firmware_reference == firmware
    assert ("ae1" in probe.detected_sensors) == (expected_model == 55781)
    assert device.model_definition is get_model_definition_for_reported_model(
        expected_model
    )


@pytest.mark.parametrize("model", (5578, 5579))
async def test_factory_rejects_model_mismatching_corrected_identity(
    mock_modbus_unit: MockModbusUnit, model: int
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding.update({0: 5578, 2: 266})
    with pytest.raises(ValueError, match="reported 5578 .*resolved to 55781"):
        await Trovis557x.async_create(mock_modbus_unit, model=model)


async def test_identity_apis_preserve_raw_model(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.holding.update({0: 5578, 2: 266})

    identity = await async_read_identity(mock_modbus_unit)
    identified = await Trovis557x.async_identify(mock_modbus_unit)

    assert identity == identified
    assert (identity.model, identity.firmware) == (5578, 266)
    assert len(mock_modbus_unit.read_events) == 4


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
