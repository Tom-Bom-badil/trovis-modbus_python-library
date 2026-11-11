"""Static M-Bus heat-meter slots exposed by each TROVIS controller model."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from types import MappingProxyType

from ..enums import ControllerModel

HEAT_METER_SLOTS = (1, 2, 3)


@dataclass(frozen=True, slots=True)
class HeatMeterConfiguration:
    """Heat-meter slots (WMZ1..WMZ3) exposed by one controller model."""

    model: ControllerModel
    heat_meter_indices: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        for index in self.heat_meter_indices:
            if (
                isinstance(index, bool)
                or not isinstance(index, int)
                or index not in HEAT_METER_SLOTS
            ):
                raise ValueError("heat meter index must be in range 1..3")
        if len(set(self.heat_meter_indices)) != len(self.heat_meter_indices):
            raise ValueError(
                f"duplicate heat meter indices in model {self.model.value}"
            )

    def supports_heat_meter(self, index: int) -> bool:
        """Return whether the model exposes heat meter ``index``."""
        return index in self.heat_meter_indices

    def with_heat_meter_indices(
        self, heat_meter_indices: Iterable[int]
    ) -> HeatMeterConfiguration:
        """Select active slots from this model's supported heat-meter slots."""
        selected = tuple(heat_meter_indices)
        if any(
            isinstance(index, bool)
            or not isinstance(index, int)
            or index not in HEAT_METER_SLOTS
            for index in selected
        ):
            raise ValueError("heat meter index must be in range 1..3")
        if not set(selected).issubset(self.heat_meter_indices):
            raise ValueError(f"heat meter slot not supported by {self.model.value}")
        return HeatMeterConfiguration(
            model=self.model,
            heat_meter_indices=tuple(sorted(set(selected))),
        )


# Known model support; this is NOT the default polling configuration.
# Only explicitly enabled slots will be polled. Other models expose no slots.
HEAT_METER_CONFIGURATIONS = MappingProxyType(
    {
        configuration.model: configuration
        for configuration in (
            HeatMeterConfiguration(
                model=ControllerModel.TROVIS_5578,
                heat_meter_indices=HEAT_METER_SLOTS,
            ),
        )
    }
)


def get_heat_meter_configuration(
    model: ControllerModel | str,
) -> HeatMeterConfiguration:
    """Return the heat-meter configuration for a controller model."""
    try:
        controller_model = ControllerModel(model)
    except ValueError as err:
        raise KeyError(f"unsupported TROVIS model: {model!r}") from err

    return HEAT_METER_CONFIGURATIONS.get(
        controller_model,
        HeatMeterConfiguration(model=controller_model),
    )
