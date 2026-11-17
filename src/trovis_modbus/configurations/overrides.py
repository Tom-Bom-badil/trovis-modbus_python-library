"""Verified firmware/model deviations from standard TROVIS field definitions.

Only put actual override definitions in this file.  Field cloning, metadata,
validation, address-span handling and installation live in ``data_model.py``.
An override ``None`` removes a field; a dictionary adjusts named properties;
a complete descriptor replaces or adds a field.  Factory arguments use SAMSON
one-based HR/CL references, while partial address overrides use zero-based PDU
addresses (the same convention as the framework's field descriptors).

CO5-F05 (falling) and CO5-F06 (rising) use a SHARED delay parameter, HR40118;
their individual enable switches are CL134 and CL135.  The manufacturer
register list calls HR40118 "CO5,Fb05/CO5,Fb06".  Thus the one numeric override
below covers both functions; no undocumented second register is assumed.
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

    # CO5-F05 / CO5-F06, HR40118: SAMSON firmware revision history says
    # delayed outdoor-temperature adaptation became adjustable in 0.1 K/h
    # increments from firmware 2.51 (older firmwares used 1.0 K/h steps).
    # Both falling and rising adaptations share this setting; activation is
    # controlled independently by CL134 / CL135 and is not altered here.
    if firmware >= 251:
        overrides["controller.outdoor_temperature_delay"] = {
            "min_value": 0.2,
            "step": 0.1,
            "digits": 1,
            "raw_min": 2,
        }

    return overrides
