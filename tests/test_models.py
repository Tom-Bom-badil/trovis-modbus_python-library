"""Tests for static TROVIS controller-model definitions."""

import pytest

from trovis_modbus.configurations import (
    COMMON_SENSOR_KEYS,
    MODEL_DEFINITIONS,
    TROVIS_5573,
    TROVIS_5573_1,
    TROVIS_5575,
    TROVIS_5576,
    TROVIS_5578,
    TROVIS_5578_E,
    TROVIS_5579,
    ControllerModel as ModelsControllerModel,
    ModelCorrection,
    ModelDefinition,
    SensorVariant,
    get_model_definition,
    get_model_definition_for_reported_model,
    model_candidates_for_reported_model,
    resolve_reported_model,
    sensor_variant,
)
from trovis_modbus.configurations.trovis_models import (
    ControllerModel as DefinitionsControllerModel,
)
from trovis_modbus.enums import ControllerModel


def _variant_keys(definition: ModelDefinition) -> set[tuple[str, ...]]:
    return {variant.sensor_keys for variant in definition.sensor_variants}


def test_controller_model_import_paths_share_the_canonical_enum() -> None:
    assert ModelsControllerModel is ControllerModel
    assert DefinitionsControllerModel is ControllerModel


@pytest.mark.parametrize(
    ("definition", "expected_control_circuits"),
    (
        (TROVIS_5573, 2),
        (TROVIS_5573_1, 2),
        (TROVIS_5575, 2),
        (TROVIS_5576, 2),
        (TROVIS_5578, 3),
        (TROVIS_5578_E, 3),
        (TROVIS_5579, 3),
    ),
)
def test_model_definitions_have_unique_sensor_keys(
    definition: ModelDefinition,
    expected_control_circuits: int,
) -> None:
    assert definition.control_circuits == expected_control_circuits
    assert len(definition.sensor_keys) == len(set(definition.sensor_keys))
    assert definition.measurement_keys == definition.sensor_keys


def test_registry_contains_all_supported_model_designations() -> None:
    assert set(MODEL_DEFINITIONS) == set(ControllerModel)
    assert get_model_definition("5573-1") is TROVIS_5573_1
    assert get_model_definition("5578-E") is TROVIS_5578_E


@pytest.mark.parametrize(
    ("reported_model", "expected_definition"),
    (
        (5573, TROVIS_5573),
        (55731, TROVIS_5573_1),
        (5575, TROVIS_5575),
        (5576, TROVIS_5576),
        (5578, TROVIS_5578),
        (55781, TROVIS_5578_E),
        (5579, TROVIS_5579),
    ),
)
def test_reported_model_values_resolve_exactly(
    reported_model: int,
    expected_definition: ModelDefinition,
) -> None:
    assert model_candidates_for_reported_model(reported_model) == (expected_definition,)


def test_unknown_reported_model_has_no_candidates() -> None:
    assert model_candidates_for_reported_model(9999) == ()


def test_unique_reported_model_definition_lookup() -> None:
    assert get_model_definition_for_reported_model(55731) is TROVIS_5573_1
    assert get_model_definition_for_reported_model(55781) is TROVIS_5578_E

    with pytest.raises(KeyError, match="unsupported reported TROVIS model"):
        get_model_definition_for_reported_model(9999)


@pytest.mark.parametrize(
    ("firmware", "expected_model"),
    ((265, 5578), (266, 5578), (300, 5578), (301, 55781)),
)
def test_model_override_inclusive_bounds_and_builtin_fallback(
    firmware: int, expected_model: int
) -> None:
    overrides = (
        ModelCorrection(
            reported_model=5578,
            minimum_firmware=266,
            maximum_firmware=300,
            model=5578,
        ),
    )
    assert (
        resolve_reported_model(5578, firmware, model_overrides=iter(overrides))
        == expected_model
    )


def test_model_overrides_use_first_match_without_chaining() -> None:
    first = ModelCorrection(reported_model=5578, minimum_firmware=266, model=5576)
    second = ModelCorrection(reported_model=5578, minimum_firmware=266, model=5579)
    chained = ModelCorrection(reported_model=5576, minimum_firmware=266, model=5573)

    assert (
        resolve_reported_model(5578, 300, model_overrides=(first, second, chained))
        == 5576
    )
    assert (
        resolve_reported_model(5578, 300, model_overrides=(second, first, chained))
        == 5579
    )


def test_model_override_can_map_unknown_reported_model() -> None:
    rule = ModelCorrection(reported_model=9999, minimum_firmware=1, model=5573)
    assert resolve_reported_model(9999, 100, model_overrides=(rule,)) == 5573
    assert resolve_reported_model(9998, 100, model_overrides=(rule,)) == 9998


@pytest.mark.parametrize(
    ("reported_model", "minimum_firmware", "model", "maximum_firmware", "message"),
    (
        (0, 266, 55781, None, "reported_model"),
        (True, 266, 55781, None, "reported_model"),
        (5578, 0, 55781, None, "minimum_firmware"),
        (5578, True, 55781, None, "minimum_firmware"),
        (5578, 266, 0, None, "model"),
        (5578, 266, 9999, None, "unsupported correction target"),
        (5578, 266, 55781, 0, "maximum_firmware"),
        (5578, 266, 55781, True, "maximum_firmware"),
        (5578, 266, 55781, 265, "below minimum_firmware"),
    ),
)
def test_model_correction_rejects_invalid_rules(
    reported_model: int,
    minimum_firmware: int,
    model: int,
    maximum_firmware: int | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ModelCorrection(
            reported_model=reported_model,
            minimum_firmware=minimum_firmware,
            model=model,
            maximum_firmware=maximum_firmware,
        )


@pytest.mark.parametrize("definition", MODEL_DEFINITIONS.values())
def test_every_model_uses_the_common_557x_sensor_base(
    definition: ModelDefinition,
) -> None:
    assert set(COMMON_SENSOR_KEYS) <= set(definition.sensor_keys)


@pytest.mark.parametrize("definition", MODEL_DEFINITIONS.values())
def test_model_definitions_use_only_supported_sensor_variants(
    definition: ModelDefinition,
) -> None:
    variant_sensor_keys = [
        sensor_key
        for variant in definition.sensor_variants
        for sensor_key in variant.sensor_keys
    ]
    assert set(variant_sensor_keys) <= set(definition.sensor_keys)
    assert len(variant_sensor_keys) == len(set(variant_sensor_keys))


def test_sensor_variant_may_describe_one_configurable_sensor() -> None:
    variant = sensor_variant("fg1")
    assert variant == SensorVariant(sensor_keys=("fg1",))
    assert variant.contains("fg1")
    assert not variant.contains("fg2")


def test_model_definition_exposes_fixed_and_variant_sensor_keys() -> None:
    assert TROVIS_5573.sensor_variant_for("sf2") == sensor_variant("sf2", "rf2")
    assert TROVIS_5573.sensor_variant_for("af1") is None
    assert "sf2" in TROVIS_5573.variant_sensor_keys
    assert "af1" in TROVIS_5573.fixed_sensor_keys
    assert TROVIS_5573.supports_sensor("analog_input_voltage")
    assert not TROVIS_5573.supports_sensor("rf3")


def test_5573_family_uses_the_reduced_sensor_variants() -> None:
    expected = {
        ("sf2", "rf2"),
        ("vf2", "vf3", "vf4"),
        ("fg1",),
        ("fg2",),
    }
    assert _variant_keys(TROVIS_5573) == expected
    assert _variant_keys(TROVIS_5573_1) == expected


def test_5575_keeps_the_multi_purpose_sensor_variant() -> None:
    assert _variant_keys(TROVIS_5575) == {
        ("sf2", "rf2", "analog_input_voltage", "pulse_rate"),
        ("vf2", "vf3", "vf4"),
        ("fg1",),
        ("fg2",),
    }


def test_5576_adds_af2_and_sf3_without_a_third_control_circuit() -> None:
    assert TROVIS_5576.control_circuits == 2
    assert TROVIS_5576.supports_sensor("af2")
    assert TROVIS_5576.supports_sensor("sf3")
    assert not TROVIS_5576.supports_sensor("rf3")
    assert ("sf3", "analog_input_voltage", "pulse_rate") in _variant_keys(TROVIS_5576)


def test_5578_has_no_ruef4_sensor_key() -> None:
    assert TROVIS_5578.supports_sensor("af2")
    assert not TROVIS_5578.supports_sensor("ruef4")
    assert ("sf3", "fg3", "pulse_rate") in _variant_keys(TROVIS_5578)


def test_5578_e_keeps_separate_ae_and_fg_sensor_keys() -> None:
    for sensor_key in ("ae1", "ae2", "ae3", "fg1", "fg2", "fg3"):
        assert TROVIS_5578_E.supports_sensor(sensor_key)

    assert ("ae1", "fg1") in _variant_keys(TROVIS_5578_E)
    assert ("ae2", "fg2") in _variant_keys(TROVIS_5578_E)
    assert ("ae3", "fg3", "sf3", "pulse_rate") in _variant_keys(TROVIS_5578_E)
    assert not TROVIS_5578_E.supports_sensor("ruef4")


def test_5579_keeps_the_multifunctional_input_17_variant() -> None:
    assert TROVIS_5579.supports_sensor("analog_input_voltage")
    assert TROVIS_5579.supports_sensor("analog_input_current")
    assert (
        "sf3",
        "fg3",
        "analog_input_voltage",
        "analog_input_current",
        "pulse_rate",
    ) in _variant_keys(TROVIS_5579)


def test_pulse_rate_is_supported_only_by_documented_models() -> None:
    for definition in (
        TROVIS_5575,
        TROVIS_5576,
        TROVIS_5578,
        TROVIS_5578_E,
        TROVIS_5579,
    ):
        assert definition.supports_sensor("pulse_rate")

    assert not TROVIS_5573.supports_sensor("pulse_rate")
    assert not TROVIS_5573_1.supports_sensor("pulse_rate")


@pytest.mark.parametrize("definition", MODEL_DEFINITIONS.values())
def test_model_definitions_use_only_canonical_logical_sensor_names(
    definition: ModelDefinition,
) -> None:
    combined_keys = {
        "ae1_fg1",
        "ae2_fg2",
        "ae3_fg3",
        "af2_ruef4",
        "sf2_rf2",
        "sf3_fg3",
        "vf2_3_4",
    }
    assert not (set(definition.sensor_keys) & combined_keys)


def test_invalid_sensor_variant_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        sensor_variant()

    with pytest.raises(ValueError, match="unique"):
        sensor_variant("fg1", "fg1")


def test_model_rejects_an_unsupported_variant_sensor() -> None:
    with pytest.raises(ValueError, match="unsupported sensor keys"):
        ModelDefinition(
            model=ControllerModel.TROVIS_5573,
            control_circuits=2,
            sensor_keys=("af1",),
            sensor_variants=(sensor_variant("fg1"),),
        )


@pytest.mark.parametrize("definition", MODEL_DEFINITIONS.values())
def test_every_model_supports_analog_output_voltage(
    definition: ModelDefinition,
) -> None:
    """AA1 is part of the common TROVIS 557x measurement set."""
    assert definition.supports_sensor("analog_output_voltage")
