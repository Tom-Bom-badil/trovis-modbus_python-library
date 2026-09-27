"""Fixtures: a Trovis557x over modbus-connection's in-memory mock backend.

The mock backend and its fixtures ship with ``modbus-connection``. They are
imported explicitly below so the test suite does not depend on pytest entry-point
autoloading. There is no real server, socket, or backend here — just an
address-keyed store loaded with TROVIS-shaped register and coil values.
"""

from __future__ import annotations

import pytest
from modbus_connection.mock import MockModbusUnit
from modbus_connection.pytest_plugin import (
    mock_modbus_connection as mock_modbus_connection,
    mock_modbus_unit as mock_modbus_unit,
)

from trovis_modbus import Trovis557x

# run: PYTHONPATH=src:/config/dev/modbus-connection/src python -m pytest

# Raw register words keyed by their (protocol) address; decoded view inline.
HOLDING: dict[int, int] = {
    0: 5579,  # model
    1: 21,  # system -> 2.1
    2: 305,  # firmware -> 3.05
    3: 110,  # hardware -> 1.10
    5: 12345,  # serial
    9: 0x10000 - 50,  # sensors.af1 -> -5.0 (signed, outdoor temperature)
    12: 300,  # sensors.vf1 -> 30.0 -> unsigned, the water in your pipes
    19: 200,  # sensors.rf1 -> 20.0
    22: 450,  # sensors.sf1 -> 45.0
    23: 0x7FFF,  # sensors.sf2 -> NaN -> None
    24: 650,  # sensors.sf3 -> 65.0
    25: 952,  # sensors.ae1 / sensors.fg1 -> 95.2
    26: 3250,  # sensors.ae2 / sensors.fg2 -> 325.0
    27: 125,  # sensors.ae3 / sensors.fg3 -> 12.5
    28: 240,  # sensors.pulse_rate -> 240 Imp/h
    41: 735,  # sensors.analog_input_voltage -> 7.35 V / current view -> 147.0 mA
    42: 185,  # sensors.summer_outdoor_temperature_average -> 18.5 °C
    73: 1,  # HR40074 / Rk1 active operating mode -> AUTOMATIC
    74: 1,  # HR40075 / Rk2 active operating mode -> AUTOMATIC
    75: 1,  # HR40076 / Rk3 active operating mode -> AUTOMATIC
    76: 1,  # HR40077 / Rk4 active operating mode -> AUTOMATIC
    98: 900,  # max flow setpoint -> 90.0
    99: 1430,  # time -> 14:30
    100: 2106,  # date -> 21.06
    101: 2026,  # year
    102: 1,  # switch_top -> AUTOMATIC
    105: 1,  # HR40106 / Rk1 external mode command -> AUTOMATIC
    106: 42,  # rk1 control signal -> 42 %
    107: 1,  # HR40108 / Rk2 external mode command -> AUTOMATIC
    109: 1,  # HR40110 / Rk3 external mode command -> AUTOMATIC
    111: 1,  # HR40112 / Rk4 external mode command -> AUTOMATIC
    112: 1505,  # summer start -> 15.05
    113: 3009,  # summer end -> 30.09
    114: 2,  # summer_days_on
    115: 3,  # summer_days_off
    120: 50,  # temperature monitoring deviation -> 5.0 K
    121: 30,  # temperature monitoring window -> 30 min
    123: 0x10000 - 200,  # 0 V outdoor-temperature range -> -20.0 °C
    124: 500,  # 10 V outdoor-temperature range -> 50.0 °C
    149: 0,  # error status
    999: 550,  # rk1 flow_setpoint -> 55.0
    1000: 800,  # rk1 maximum_flow_temperature -> 80.0
    1001: 200,  # rk1 minimum_flow_temperature -> 20.0
    1002: 210,  # rk1 room_setpoint_day -> 21.0
    1003: 180,  # rk1 room_setpoint_night -> 18.0
    1004: 210,  # rk1 room_setpoint_active -> 21.0
    1005: 12,  # rk1 gradient -> 1.2
    1006: 0,  # rk1 level -> 0.0
    1008: 5,  # rk1 return gradient -> 0.5
    1009: 20,  # rk1 return level -> 2.0 K
    1010: 550,  # rk1 maximum return temperature -> 55.0 °C
    1011: 300,  # rk1 return base point -> 30.0 °C
    1012: 0xFF6A,  # rk1 four-point outdoor P1 -> -15.0 °C
    1013: 0xFFCE,  # rk1 four-point outdoor P2 -> -5.0 °C
    1014: 50,  # rk1 four-point outdoor P3 -> 5.0 °C
    1015: 150,  # rk1 four-point outdoor P4 -> 15.0 °C
    1016: 700,  # rk1 four-point flow day P1 -> 70.0 °C
    1017: 550,  # rk1 four-point flow day P2 -> 55.0 °C
    1018: 400,  # rk1 four-point flow day P3 -> 40.0 °C
    1019: 250,  # rk1 four-point flow day P4 -> 25.0 °C
    1020: 600,  # rk1 four-point flow night P1 -> 60.0 °C
    1021: 400,  # rk1 four-point flow night P2 -> 40.0 °C
    1022: 200,  # rk1 four-point flow night P3 -> 20.0 °C
    1023: 200,  # rk1 four-point flow night P4 -> 20.0 °C
    1024: 650,  # rk1 four-point return P1 -> 65.0 °C
    1025: 650,  # rk1 four-point return P2 -> 65.0 °C
    1026: 650,  # rk1 four-point return P3 -> 65.0 °C
    1027: 650,  # rk1 four-point return P4 -> 65.0 °C
    1032: 450,  # rk1 current return setpoint -> 45.0 °C
    1041: 600,  # rk1 fixed setpoint day -> 60.0 °C
    1042: 500,  # rk1 fixed setpoint night -> 50.0 °C
    1199: 480,  # rk2 flow_setpoint -> 48.0
    1799: 500,  # rk4 setpoint_day -> 50.0
    1802: 50,  # rk4 hysteresis -> 5.0 K
    1806: 450,  # rk4 setpoint_night -> 45.0 °C
    1807: 500,  # rk4 setpoint_active -> 50.0
    1809: 100,  # solar pump on temperature difference -> 10.0 K
    1810: 30,  # solar pump off temperature difference -> 3.0 K
    1811: 800,  # solar maximum storage temperature -> 80.0 °C
    1812: 1234,  # solar operating hours
    1837: 670,  # rk4 active_charging_setpoint -> 67.0
    1830: 3,  # disinfection weekday -> WEDNESDAY
    1831: 1900,  # disinfection start -> 19:00
    1832: 2100,  # disinfection stop -> 21:00
    1838: 30,  # disinfection hold -> 30 min
    2001: 5,  # HR42002 / AE selection -> AE1 + AE3
    2002: 15,  # HR42003 / SLP sensor input -> input 15
}

COILS: dict[int, bool] = {
    138: False,  # CL139 / FB10 / pulse input inactive
    3: True,  # CL4 / Sammel_Ebenenbit -> AUTARK by default
    56: True,  # rk1 pump
    88: True,  # CL89 / Rk1 operating-mode ownership -> AUTARK
    90: True,  # CL91 / Rk2 operating-mode ownership -> AUTARK
    92: True,  # CL93 / Rk3 operating-mode ownership -> AUTARK
    94: True,  # CL95 / Rk4 operating-mode ownership -> AUTARK
    95: True,  # CL96 / Rk1 pump ownership -> AUTARK
    96: True,  # CL97 / Rk2 pump ownership -> AUTARK
    97: True,  # CL98 / Rk3 pump ownership -> AUTARK
    98: True,  # CL99 / Rk4 SLP ownership -> AUTARK
    99: True,  # CL100 / Rk4 ZP ownership -> AUTARK
    158: False,  # CL159 / GLT timeout inactive
    999: True,  # rk1 automatic
    1000: True,  # rk1 day active
    # Rk1 heating configuration
    1024: True,  # CL1025 / CO1 -> F01: room-temperature feedback enabled
    1025: True,  # CL1026 / CO1 -> F02: outdoor sensor enabled
    1034: False,  # CL1035 / CO1 -> F11: gradient characteristic
    # Rk2 heating configuration
    1224: True,  # CL1225 / CO2 -> F01: room-temperature feedback enabled
    1225: True,  # CL1226 / CO2 -> F02: outdoor sensor enabled
    1234: False,  # CL1235 / CO2 -> F11: gradient characteristic
    # Rk3 heating configuration
    1424: True,  # CL1425 / CO3 -> F01: room-temperature feedback enabled
    1425: True,  # CL1426 / CO3 -> F02: outdoor sensor enabled
    1434: False,  # CL1435 / CO3 -> F11: gradient characteristic
    1799: True,  # rk4 automatic
    1807: True,  # CL1808 / solar circuit pump active
    59: True,  # WW storage tank charging pump
    401: False,  # CL402 / FB02 / SF2 inactive -> RF2
    404: False,  # CL405 / FB05 / VF4 inactive
    413: True,  # CL414 / CO4 -> F14 / thermal disinfection enabled
    800: False,  # CL801 / input 1 configured as sensor input
    801: True,  # CL802 / input 2 configured as binary input
    802: False,  # CL803 / input 3 configured as sensor input
    803: False,  # CL804 / input 4 configured as sensor input
    805: False,  # CL806 / input 6 configured as sensor input
    808: False,  # CL809 / input 9 configured as sensor input
    809: False,  # CL810 / input 10 configured as sensor input
    810: False,  # CL811 / input 11 configured as sensor input
    814: False,  # CL815 / input 15 configured as sensor input
    815: True,  # CL816 / input 16 configured as binary input
    816: False,  # CL817 / input 17 configured as sensor input
    904: True,  # CL905 / 0-10 V setpoint correction enabled
    906: False,  # CL907 / FB07 / VF2 inactive
    1828: False,  # CL1829 / FB05 / VF4 inactive
    2124: False,  # CL2125 / CO1 F25 / SF3 buffer bottom sensor inactive
}


@pytest.fixture
def trovis(mock_modbus_unit: MockModbusUnit) -> Trovis557x:
    """A Trovis557x over the mock unit, preloaded with device values."""
    mock_modbus_unit.holding.update(HOLDING)
    mock_modbus_unit.coil.update(COILS)
    return Trovis557x(mock_modbus_unit)


@pytest.fixture
def unit(mock_modbus_unit: MockModbusUnit) -> MockModbusUnit:
    """The mock unit the ``trovis`` fixture reads and writes through.

    Request it alongside ``trovis`` to assert on the register and coil stores a
    write landed in, rather than reaching for the unit a component holds.
    """
    return mock_modbus_unit
