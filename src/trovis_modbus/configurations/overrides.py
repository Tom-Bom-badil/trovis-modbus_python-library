"""Verified firmware/model deviations from standard TROVIS field definitions.

Only put actual override definitions in this file.  Field cloning, metadata,
validation, address-span handling and installation live in ``data_model.py``.
An override ``None`` removes a field; a dictionary adjusts named properties;
a complete descriptor replaces or adds a field.  Factory arguments use SAMSON
one-based HR/CL references, while partial address overrides use zero-based PDU
addresses (the same convention as the framework's field descriptors).

Examples for usage:

    if firmware >= 300:
        overrides["controller.some_old_field"] = None    # for removed items

    if model == 5573 and firmware >= 248:                # for changed items
        overrides["rk*.valve_setpoint"] = {
            "min_value": 10,
            "max_value": 20,
        }

    if model in (5573, 5578) and firmware <= 220:        # for additional items
        overrides["controller.new_feature"] = gauge(
            40199,
            0.1,
            writable=True,
            min_value=0,
            max_value=100,
            digits=1,
        )

Note: Major changes seem to have happened at least in the steps 2.48 -> 2.52 and
2.63 (EOL-Version) -> 3.00.

"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def get_overrides(model: int, firmware: int) -> Mapping[str, Any]:
    """Return documented overrides keyed by ``component.field`` or ``rk*.field``.

    ``firmware`` is the integer hundredths value read from HR40003.
    ``model`` can constrain future rules where model differences are verified.
    """
    overrides: dict[str, Any] = {}

    # === start override definition ====================================

    # 2.51+: Outdoor temperature adaptation delay (CO5-F05/F06, HR40118)
    # Range 0.2..6.0 K/h, resolution 0.1 K/h.
    # Old / until 2.48:  Range 1..6 K/h, resolution 1 K/h.
    if firmware >= 251:
        overrides["controller.outdoor_temperature_delay"] = {
            "min_value": 0.2,
            "step": 0.1,
            "digits": 1,
            "raw_min": 2,
        }

    # === end override definitions =====================================

    return overrides
