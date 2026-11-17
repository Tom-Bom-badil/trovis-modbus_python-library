"""Synthetic override cases; none of these are claimed firmware facts."""

from __future__ import annotations

import pytest
from modbus_connection.mock import MockModbusUnit

from trovis_modbus import Trovis557x
from trovis_modbus.configurations import overrides
from trovis_modbus.data_model import coil, gauge, integer
from trovis_modbus.exceptions import TrovisValueValidationError
from trovis_modbus.subsystems.circuit_heating import HeatingCircuit
from trovis_modbus.trovis import _union_readable_ranges


def test_preserve_existing_model_range_boundaries() -> None:
    original = ((0, 5), (6, 10), (15, 25))
    assert _union_readable_ranges(original, ()) == original
    assert _union_readable_ranges(original, ((3, 4),)) == original
    assert _union_readable_ranges(original, ((9, 17),)) == (
        (0, 5),
        (6, 10),
        (11, 14),
        (15, 25),
    )
    assert _union_readable_ranges(original, ((30, 31),)) == (*original, (30, 31))


def test_firmware_instance_isolation_remove_partial_add(
    mock_modbus_unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same model on different firmwares must never share modified fields."""

    def rules(model: int, firmware: int):
        if firmware < 300:
            return {}
        assert model == 5579
        return {
            "controller.summer_days_on": None,
            "rk*.valve_setpoint": {"min_value": 10, "max_value": 20},
            "rk2.maximum_flow_temperature": {"min_value": 10, "max_value": 20},
            "controller.added_sensor": integer(
                49940, signed=False, description="Synthetic new diagnostic value"
            ),
            "rk2.added_coil": coil(5000, description="Synthetic new boolean state"),
        }

    monkeypatch.setattr(overrides, "get_overrides", rules)
    earlier = Trovis557x(mock_modbus_unit, model=5579, firmware_reference=299)
    latest = Trovis557x(mock_modbus_unit, model=5579, firmware_reference=305)
    assert earlier.controller.is_field_readable("summer_days_on")
    assert not latest.controller.is_field_readable("summer_days_on")
    assert latest.controller.metadata_for("summer_days_on") is None
    assert earlier.controller.metadata_for("summer_days_on") is not None
    assert "added_sensor" not in earlier.controller.readable_field_names
    assert "added_sensor" in latest.controller.readable_field_names
    assert "added_coil" in latest.rk2.readable_field_names
    assert "added_coil" not in earlier.rk2.readable_field_names
    assert latest.added_override_fields["controller"] == {"added_sensor"}
    assert latest.added_override_fields["rk2"] == {"added_coil"}
    assert not hasattr(HeatingCircuit, "added_coil")

    for index in (1, 2, 3):
        old = getattr(earlier, f"rk{index}")
        new = getattr(latest, f"rk{index}")
        assert old.require_metadata_for("valve_setpoint").number.min_value == 0
        assert new.require_metadata_for("valve_setpoint").number.min_value == 10
        assert new.require_metadata_for("valve_setpoint").number.max_value == 20
        assert (
            old.resolved_fields["valve_setpoint"].address
            == new.resolved_fields["valve_setpoint"].address
        )
        assert (
            old._register_fields["valve_setpoint"]
            is not new._register_fields["valve_setpoint"]
        )

    # A partial override must replace old default numeric validation, not stack
    # old firmware limits onto new ones.  The bounded writer never touches a
    # real controller in this test.
    constrained = latest.rk2._register_fields["maximum_flow_temperature"].writable
    assert callable(constrained)
    assert constrained(15) == 15
    with pytest.raises(TrovisValueValidationError):
        constrained(21)


def test_full_replacement_uses_new_address_and_stride(
    mock_modbus_unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def rules(_model, _firmware):
        return {
            "rk2.flow_setpoint": gauge(
                49940, 0.1, stride=7, description="Synthetic replacement"
            )
        }

    monkeypatch.setattr(overrides, "get_overrides", rules)
    device = Trovis557x(mock_modbus_unit, model=5579, firmware_reference=305)
    # PDU 9939 + (Rk2 index-1)*7
    assert device.rk2.resolved_fields["flow_setpoint"].address == 9946
    assert device.rk1.resolved_fields["flow_setpoint"].address == 999
    assert device.rk3.resolved_fields["flow_setpoint"].address == 1399


def test_reject_unknown_colliding_or_unsafe_rules(
    mock_modbus_unit: MockModbusUnit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    examples = (
        {"rk*.valve_setpoint": None, "rk2.valve_setpoint": None},
        {"controller.missing_field": {"min_value": 3}},
        {"controller.added_writable": integer(49941, writable=True)},
        {"controller.duplicate_address": integer(40103, description="Collision")},
        {"controller.summer_days_on": {"unknown_property": 7}},
    )
    for rule_set in examples:
        monkeypatch.setattr(
            overrides, "get_overrides", lambda _m, _f, rules=rule_set: rules
        )
        with pytest.raises(ValueError):
            Trovis557x(mock_modbus_unit, model=5579, firmware_reference=305)


def test_co5_f05_and_f06_share_delay_override_from_firmware_251(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    """Both adaptation directions retain their coils and share HR40118."""
    old = Trovis557x(mock_modbus_unit, model=5579, firmware_reference=248)
    new = Trovis557x(mock_modbus_unit, model=5579, firmware_reference=251)
    newer = Trovis557x(mock_modbus_unit, model=5579, firmware_reference=308)

    key = "outdoor_temperature_delay"
    for device, minimum, step, digits, raw_min in (
        (old, 1, 1, 0, 10),
        (new, 0.2, 0.1, 1, 2),
        (newer, 0.2, 0.1, 1, 2),
    ):
        field = device.controller.require_metadata_for(key)
        assert field.number is not None
        assert field.number.min_value == minimum
        assert field.number.max_value == 6
        assert field.number.step == step
        assert field.number.digits == digits
        assert field.number.raw_min == raw_min
        assert field.number.raw_max == 60
        descriptor = device.controller._register_fields[key]
        assert descriptor.address == 117  # HR40118, one shared F05/F06 setting
        assert descriptor.decode([30]) == pytest.approx(3.0)
        assert descriptor.encode(3.0) == [30]

        # Both function-block switches retain their old addresses/capability.
        for name, zero_based in (
            ("delayed_outdoor_temperature_adaptation_falling", 133),
            ("delayed_outdoor_temperature_adaptation_rising", 134),
        ):
            assert device.controller._bit_fields[name].address == zero_based

    old_writer = old.controller._register_fields[key].writable
    new_writer = new.controller._register_fields[key].writable
    assert callable(old_writer) and callable(new_writer)
    with pytest.raises(TrovisValueValidationError):
        old_writer(0.2)
    assert new_writer(0.2) == 0.2
    with pytest.raises(TrovisValueValidationError):
        new_writer(0.1)

    # Per-instance definitions must not leak into another firmware's metadata.
    assert old.controller.require_metadata_for(key).number.min_value == 1
