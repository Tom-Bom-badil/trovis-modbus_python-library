"""Static logical capabilities of supported TROVIS controller models."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import chain
from types import MappingProxyType

from ..enums import ControllerModel


@dataclass(frozen=True, slots=True)
class SensorVariant:
    """Logical sensors whose meaning depends on controller configuration.

    A one-key variant is available only in one configurable input mode. Another
    mode may use the same input for a non-sensor function such as a binary
    input.

    A multi-key variant describes alternative logical meanings of one input.
    The sensor-variant resolver selects the active key from the controller's
    functions, parameters, and relevant coils.
    """

    sensor_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.sensor_keys:
            raise ValueError("sensor variant must contain at least one sensor key")
        if any(not sensor_key for sensor_key in self.sensor_keys):
            raise ValueError("sensor variant keys must not be empty")
        if len(set(self.sensor_keys)) != len(self.sensor_keys):
            raise ValueError("sensor variant keys must be unique")

    def contains(self, sensor_key: str) -> bool:
        """Return whether this variant contains ``sensor_key``."""
        return sensor_key in self.sensor_keys


@dataclass(frozen=True, slots=True)
class ModelDefinition:
    """Static logical sensor capabilities of one TROVIS controller model."""

    model: ControllerModel
    control_circuits: int
    sensor_keys: tuple[str, ...]
    sensor_variants: tuple[SensorVariant, ...] = ()

    def __post_init__(self) -> None:
        if self.control_circuits not in (2, 3):
            raise ValueError("control_circuits must be 2 or 3")
        if not self.sensor_keys:
            raise ValueError("a model definition must contain sensor keys")
        if any(not sensor_key for sensor_key in self.sensor_keys):
            raise ValueError("sensor keys must not be empty")
        if len(set(self.sensor_keys)) != len(self.sensor_keys):
            raise ValueError(f"duplicate sensor keys in model {self.model.value}")

        supported_sensor_keys = set(self.sensor_keys)
        variant_sensor_keys: set[str] = set()
        variant_signatures: set[tuple[str, ...]] = set()

        for variant in self.sensor_variants:
            unsupported = set(variant.sensor_keys) - supported_sensor_keys
            if unsupported:
                raise ValueError(
                    f"sensor variant in model {self.model.value} contains "
                    f"unsupported sensor keys: {sorted(unsupported)}"
                )

            signature = variant.sensor_keys
            if signature in variant_signatures:
                raise ValueError(
                    f"duplicate sensor variant in model {self.model.value}: "
                    f"{signature!r}"
                )
            variant_signatures.add(signature)

            duplicate_membership = variant_sensor_keys & set(variant.sensor_keys)
            if duplicate_membership:
                raise ValueError(
                    f"sensor keys occur in several variants in model "
                    f"{self.model.value}: {sorted(duplicate_membership)}"
                )
            variant_sensor_keys.update(variant.sensor_keys)

    @property
    def measurement_keys(self) -> tuple[str, ...]:
        """Return the supported logical sensor keys.

        ``measurement_keys`` remains as a neutral read-only alias while callers
        move to the more precise :attr:`sensor_keys` name.
        """
        return self.sensor_keys

    @property
    def variant_sensor_keys(self) -> frozenset[str]:
        """Return sensor keys whose meaning or availability is configurable."""
        return frozenset(
            sensor_key
            for variant in self.sensor_variants
            for sensor_key in variant.sensor_keys
        )

    @property
    def fixed_sensor_keys(self) -> frozenset[str]:
        """Return sensor keys that are not part of a configurable variant."""
        return frozenset(self.sensor_keys) - self.variant_sensor_keys

    def supports_sensor(self, sensor_key: str) -> bool:
        """Return whether the controller model exposes ``sensor_key``."""
        return sensor_key in self.sensor_keys

    def sensor_variant_for(self, sensor_key: str) -> SensorVariant | None:
        """Return the configurable variant containing ``sensor_key``."""
        return next(
            (
                variant
                for variant in self.sensor_variants
                if variant.contains(sensor_key)
            ),
            None,
        )


def sensor_variant(*sensor_keys: str) -> SensorVariant:
    """Create one concise immutable sensor variant."""
    return SensorVariant(sensor_keys=sensor_keys)


# Logical measurement registers available throughout the supported 557x family.
# Physical terminals deliberately remain outside the model definition.
COMMON_SENSOR_KEYS = (
    "af1",
    "vf1",
    "vf2",
    "vf3",
    "vf4",
    "ruef1",
    "ruef2",
    "rf1",
    "rf2",
    "sf1",
    "sf2",
    "fg1",
    "fg2",
    "analog_input_voltage",
    "analog_output_voltage",
)

# Additional logical sensors used by the three-control-circuit models.
THREE_CIRCUIT_SENSOR_KEYS = COMMON_SENSOR_KEYS + (
    "af2",
    "ruef3",
    "rf3",
    "sf3",
    "fg3",
)

# Individually configurable sensors of the larger controller family. A one-key
# variant means that another input mode is not a sensor exposed by the library.
COMMON_INDIVIDUAL_SENSOR_VARIANTS: tuple[SensorVariant, ...] = tuple(
    sensor_variant(sensor_key)
    for sensor_key in (
        "rf2",
        "vf2",
        "vf3",
        "vf4",
        "sf2",
        "fg1",
        "fg2",
    )
)

# TROVIS 5573 and 5573-1 share the same reduced logical sensor matrix.
TROVIS_5573_FAMILY_SENSOR_VARIANTS = (
    sensor_variant("sf2", "rf2"),
    sensor_variant("vf2", "vf3", "vf4"),
    sensor_variant("fg1"),
    sensor_variant("fg2"),
)


TROVIS_5573 = ModelDefinition(
    model=ControllerModel.TROVIS_5573,
    control_circuits=2,
    sensor_keys=COMMON_SENSOR_KEYS,
    sensor_variants=TROVIS_5573_FAMILY_SENSOR_VARIANTS,
)

TROVIS_5573_1 = ModelDefinition(
    model=ControllerModel.TROVIS_5573_1,
    control_circuits=2,
    sensor_keys=COMMON_SENSOR_KEYS,
    sensor_variants=TROVIS_5573_FAMILY_SENSOR_VARIANTS,
)

TROVIS_5575 = ModelDefinition(
    model=ControllerModel.TROVIS_5575,
    control_circuits=2,
    sensor_keys=COMMON_SENSOR_KEYS + ("pulse_rate",),
    sensor_variants=(
        sensor_variant("sf2", "rf2", "analog_input_voltage", "pulse_rate"),
        sensor_variant("vf2", "vf3", "vf4"),
        sensor_variant("fg1"),
        sensor_variant("fg2"),
    ),
)

TROVIS_5576 = ModelDefinition(
    model=ControllerModel.TROVIS_5576,
    control_circuits=2,
    sensor_keys=COMMON_SENSOR_KEYS + ("af2", "sf3", "pulse_rate"),
    sensor_variants=COMMON_INDIVIDUAL_SENSOR_VARIANTS
    + (sensor_variant("sf3", "analog_input_voltage", "pulse_rate"),),
)

TROVIS_5578 = ModelDefinition(
    model=ControllerModel.TROVIS_5578,
    control_circuits=3,
    sensor_keys=THREE_CIRCUIT_SENSOR_KEYS + ("pulse_rate",),
    sensor_variants=COMMON_INDIVIDUAL_SENSOR_VARIANTS
    + (sensor_variant("sf3", "fg3", "pulse_rate"),),
)

TROVIS_5578_E = ModelDefinition(
    model=ControllerModel.TROVIS_5578_E,
    control_circuits=3,
    sensor_keys=THREE_CIRCUIT_SENSOR_KEYS
    + (
        "ae1",
        "ae2",
        "ae3",
        "pulse_rate",
    ),
    sensor_variants=(
        sensor_variant("rf2"),
        sensor_variant("vf2"),
        sensor_variant("vf3"),
        sensor_variant("vf4"),
        sensor_variant("sf2"),
        sensor_variant("ae1", "fg1"),
        sensor_variant("ae2", "fg2"),
        sensor_variant("ae3", "fg3", "sf3", "pulse_rate"),
    ),
)

TROVIS_5579 = ModelDefinition(
    model=ControllerModel.TROVIS_5579,
    control_circuits=3,
    sensor_keys=THREE_CIRCUIT_SENSOR_KEYS + ("analog_input_current", "pulse_rate"),
    sensor_variants=COMMON_INDIVIDUAL_SENSOR_VARIANTS
    + (
        sensor_variant(
            "sf3",
            "fg3",
            "analog_input_voltage",
            "analog_input_current",
            "pulse_rate",
        ),
    ),
)


MODEL_DEFINITIONS = MappingProxyType(
    {
        definition.model: definition
        for definition in (
            TROVIS_5573,
            TROVIS_5573_1,
            TROVIS_5575,
            TROVIS_5576,
            TROVIS_5578,
            TROVIS_5578_E,
            TROVIS_5579,
        )
    }
)

# Register 40002 reports the concrete raw model values below. 55731 identifies
# TROVIS 5573-1 and 55781 identifies TROVIS 5578-E.
_REPORTED_MODEL_CANDIDATES = MappingProxyType(
    {
        5573: (TROVIS_5573,),
        55731: (TROVIS_5573_1,),
        5575: (TROVIS_5575,),
        5576: (TROVIS_5576,),
        5578: (TROVIS_5578,),
        55781: (TROVIS_5578_E,),
        5579: (TROVIS_5579,),
    }
)


def get_model_definition(model: ControllerModel | str) -> ModelDefinition:
    """Return the exact static definition for a controller model."""
    try:
        controller_model = ControllerModel(model)
    except ValueError as err:
        raise KeyError(f"unsupported TROVIS model: {model!r}") from err

    try:
        return MODEL_DEFINITIONS[controller_model]
    except KeyError as err:
        raise KeyError(
            f"model definition not implemented yet: {controller_model.value}"
        ) from err


def model_candidates_for_reported_model(
    reported_model: int,
) -> tuple[ModelDefinition, ...]:
    """Return static candidates for the raw model value from register 40002."""
    return _REPORTED_MODEL_CANDIDATES.get(reported_model, ())


def get_model_definition_for_reported_model(
    reported_model: int,
) -> ModelDefinition:
    """Return the unique definition for the reported raw model value."""
    candidates = model_candidates_for_reported_model(reported_model)
    if not candidates:
        raise KeyError(f"unsupported reported TROVIS model: {reported_model}")
    if len(candidates) != 1:
        raise KeyError(
            f"reported TROVIS model is ambiguous: {reported_model} "
            f"({len(candidates)} candidates)"
        )
    return candidates[0]


@dataclass(frozen=True, slots=True)
class ModelCorrection:
    """Map a reported model and inclusive firmware interval to a supported model."""

    reported_model: int
    minimum_firmware: int
    model: int
    maximum_firmware: int | None = None

    def __post_init__(self) -> None:
        values = (
            ("reported_model", self.reported_model),
            ("minimum_firmware", self.minimum_firmware),
            ("model", self.model),
        )
        if self.maximum_firmware is not None:
            values += (("maximum_firmware", self.maximum_firmware),)
        for name, value in values:
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if (
            self.maximum_firmware is not None
            and self.maximum_firmware < self.minimum_firmware
        ):
            raise ValueError("maximum_firmware must not be below minimum_firmware")
        if self.model not in _REPORTED_MODEL_CANDIDATES:
            raise ValueError(f"unsupported correction target model: {self.model}")


MODEL_CORRECTIONS = (
    ModelCorrection(reported_model=5578, minimum_firmware=266, model=55781),
)


def resolve_reported_model(
    reported_model: int,
    firmware: int,
    *,
    model_overrides: Iterable[ModelCorrection] = (),
) -> int:
    """Apply the first caller or built-in rule to the raw identity, without chaining."""
    for rule in chain(model_overrides, MODEL_CORRECTIONS):
        if (
            rule.reported_model == reported_model
            and firmware >= rule.minimum_firmware
            and (rule.maximum_firmware is None or firmware <= rule.maximum_firmware)
        ):
            return rule.model
    return reported_model


__all__ = [
    "COMMON_INDIVIDUAL_SENSOR_VARIANTS",
    "COMMON_SENSOR_KEYS",
    "MODEL_DEFINITIONS",
    "MODEL_CORRECTIONS",
    "THREE_CIRCUIT_SENSOR_KEYS",
    "TROVIS_5573",
    "TROVIS_5573_1",
    "TROVIS_5573_FAMILY_SENSOR_VARIANTS",
    "TROVIS_5575",
    "TROVIS_5576",
    "TROVIS_5578",
    "TROVIS_5578_E",
    "TROVIS_5579",
    "ControllerModel",
    "ModelDefinition",
    "ModelCorrection",
    "SensorVariant",
    "get_model_definition",
    "get_model_definition_for_reported_model",
    "model_candidates_for_reported_model",
    "resolve_reported_model",
    "sensor_variant",
]
