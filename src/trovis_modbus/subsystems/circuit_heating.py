"""The technical control circuits Rk1 through Rk3."""

from __future__ import annotations

from typing import Literal

from ..data_model import (
    DEFAULT_WRITE_ACCESS_CODE,
    TrovisComponent,
    coil,
    enum,
    gauge,
    integer,
    temperature,
)
from ..enums import (
    HEATING_OPERATING_MODE_OPTIONS,
    HeatingCircuitControlMode,
    OperatingMode,
    PumpControlMode,
)
from ..heating_curve import HeatingCurveParameters, calculate_heating_curve


class HeatingCircuit(TrovisComponent):
    """One technical Rk1-Rk3 control circuit. Construct with ``index`` 1, 2 or 3.
    Addresses follow the controller's offset pattern: the 1000-block steps by
    200 per circuit, mode/control-signal by 2, pumps/manual status by 1. Because
    those per-field strides differ, each circuit stays a per-``index`` instance
    with a field-level ``stride`` — not a ``repeating_group`` / ``base_offset``
    block, which shifts every address of an instance by one uniform amount and
    so can't express the 200/2/1 mix.
    """

    ### registers
    active_mode = enum(
        40074,
        OperatingMode,
        stride=1,
        description="Effektive Betriebsart Rk",
    )
    mode = enum(
        40106,
        OperatingMode,
        stride=2,
        writable=True,
        options=HEATING_OPERATING_MODE_OPTIONS,
        maker_key="BetriebsArt_Rk1",
        maker_category="ALG-BTR",
        description="Externe Betriebsartvorgabe Rk",
    )
    valve_setpoint = integer(
        40107,
        signed=False,
        stride=2,
        min_value=0,
        max_value=100,
        raw_min=0,
        raw_max=100,
        digits=0,
        unit="%",
        maker_key="Stellsignal_Rk1",
        maker_category="ALG-BTR",
        description="Stellsignal Rk",
    )
    flow_setpoint = temperature(
        41000,
        stride=200,
        min_value=5,
        max_value=150,
        raw_min=50,
        raw_max=1500,
        digits=1,
        maker_key="VorlSollw_Rk1",
        maker_category="SOL-VL",
        description="Vorlaufsollwert Rk",
    )
    maximum_flow_temperature = temperature(
        41001,
        stride=200,
        writable=True,
        min_value=5,
        max_value=150,
        raw_min=50,
        raw_max=1500,
        digits=1,
        maker_key="MaxVorl_Rk1",
        maker_category="SOL-VL",
        description="Maximale Vorlauftemperatur Rk",
    )
    minimum_flow_temperature = temperature(
        41002,
        stride=200,
        writable=True,
        min_value=-5,
        max_value=150,
        raw_min=-50,
        raw_max=1500,
        digits=1,
        maker_key="MinVorl_Rk1",
        maker_category="SOL-VL",
        description="Minimale Vorlauftemperatur Rk",
    )
    room_setpoint_day = temperature(
        41003,
        stride=200,
        writable=True,
        min_value=0,
        max_value=40,
        raw_min=0,
        raw_max=400,
        digits=1,
        maker_key="Tag_Soll_Rk1",
        maker_category="SOL-RT",
        description="Raumsollwert Tag",
    )
    room_setpoint_night = temperature(
        41004,
        stride=200,
        writable=True,
        min_value=0,
        max_value=40,
        raw_min=0,
        raw_max=400,
        digits=1,
        maker_key="Nacht_Soll_Rk1",
        maker_category="SOL-RT",
        description="Raumsollwert Nacht",
    )
    # HR41005 is present in the established device model but not described in
    # the final 5578 register table. Do not invent manufacturer limits here.
    room_setpoint_active = temperature(41005, stride=200)
    gradient = gauge(
        41006,
        0.1,
        stride=200,
        writable=True,
        min_value=0.2,
        max_value=3.2,
        raw_min=2,
        raw_max=32,
        digits=1,
        maker_key="Steig_HeizKL_Rk1",
        maker_category="KNL-VL",
        description="Steigung VL Heizkennlinie",
    )
    level = gauge(
        41007,
        0.1,
        stride=200,
        writable=True,
        min_value=-30,
        max_value=30,
        raw_min=-300,
        raw_max=300,
        digits=1,
        unit="K",
        maker_key="Niv_HeizKL_Rk1",
        maker_category="KNL-VL",
        description="Niveau VL Heizkennlinie",
    )
    return_flow_gradient = gauge(
        41009,
        0.1,
        stride=200,
        writable=True,
        min_value=0.2,
        max_value=3.2,
        raw_min=2,
        raw_max=32,
        digits=1,
        maker_key="Stg_RücklKL_Rk1",
        maker_category="KNL-RL",
        description="Steigung Rücklaufkennlinie",
    )
    return_flow_level = gauge(
        41010,
        0.1,
        stride=200,
        writable=True,
        min_value=-30,
        max_value=30,
        raw_min=-300,
        raw_max=300,
        digits=1,
        unit="K",
        maker_key="Niv_RücklKL_Rk1",
        maker_category="KNL-RL",
        description="Niveau Rücklaufkennlinie",
    )
    maximum_return_flow_temperature = temperature(
        41011,
        stride=200,
        writable=True,
        min_value=5,
        max_value=90,
        raw_min=50,
        raw_max=900,
        digits=1,
        maker_key="MaxRückl_Rk1",
        maker_category="SOL-RL",
        description="Maximale Rücklauftemperatur Rk",
    )
    return_flow_base_point = temperature(
        41012,
        stride=200,
        writable=True,
        min_value=5,
        max_value=90,
        raw_min=50,
        raw_max=900,
        digits=1,
        maker_key="Fuß_Rückl_Rk1",
        maker_category="SOL-RL",
        description="Fußpunkt Rücklauftemperatur Rk",
    )
    four_point_outdoor_temperature_1 = temperature(
        41013,
        stride=200,
        writable=True,
        min_value=-50,
        max_value=50,
        raw_min=-500,
        raw_max=500,
        digits=1,
        maker_key="AT1_HeizKL_Rk1",
        maker_category="KNL-AT",
        description="Außentemperatur Punkt 1 der 4-Punkte-Kennlinie",
    )
    four_point_outdoor_temperature_2 = temperature(
        41014,
        stride=200,
        writable=True,
        min_value=-50,
        max_value=50,
        raw_min=-500,
        raw_max=500,
        digits=1,
        maker_key="AT2_HeizKL_Rk1",
        maker_category="KNL-AT",
        description="Außentemperatur Punkt 2 der 4-Punkte-Kennlinie",
    )
    four_point_outdoor_temperature_3 = temperature(
        41015,
        stride=200,
        writable=True,
        min_value=-50,
        max_value=50,
        raw_min=-500,
        raw_max=500,
        digits=1,
        maker_key="AT3_HeizKL_Rk1",
        maker_category="KNL-AT",
        description="Außentemperatur Punkt 3 der 4-Punkte-Kennlinie",
    )
    four_point_outdoor_temperature_4 = temperature(
        41016,
        stride=200,
        writable=True,
        min_value=-50,
        max_value=50,
        raw_min=-500,
        raw_max=500,
        digits=1,
        maker_key="AT4_HeizKL_Rk1",
        maker_category="KNL-AT",
        description="Außentemperatur Punkt 4 der 4-Punkte-Kennlinie",
    )
    four_point_flow_temperature_day_1 = temperature(
        41017,
        stride=200,
        writable=True,
        min_value=-5,
        max_value=150,
        raw_min=-50,
        raw_max=1500,
        digits=1,
        maker_key="VT1_T_HeizKL_Rk1",
        maker_category="KNL-VL",
        description="Vorlauftemperatur Tag Punkt 1 der 4-Punkte-Kennlinie",
    )
    four_point_flow_temperature_day_2 = temperature(
        41018,
        stride=200,
        writable=True,
        min_value=-5,
        max_value=150,
        raw_min=-50,
        raw_max=1500,
        digits=1,
        maker_key="VT2_T_HeizKL_Rk1",
        maker_category="KNL-VL",
        description="Vorlauftemperatur Tag Punkt 2 der 4-Punkte-Kennlinie",
    )
    four_point_flow_temperature_day_3 = temperature(
        41019,
        stride=200,
        writable=True,
        min_value=-5,
        max_value=150,
        raw_min=-50,
        raw_max=1500,
        digits=1,
        maker_key="VT3_T_HeizKL_Rk1",
        maker_category="KNL-VL",
        description="Vorlauftemperatur Tag Punkt 3 der 4-Punkte-Kennlinie",
    )
    four_point_flow_temperature_day_4 = temperature(
        41020,
        stride=200,
        writable=True,
        min_value=-5,
        max_value=150,
        raw_min=-50,
        raw_max=1500,
        digits=1,
        maker_key="VT4_T_HeizKL_Rk1",
        maker_category="KNL-VL",
        description="Vorlauftemperatur Tag Punkt 4 der 4-Punkte-Kennlinie",
    )
    four_point_flow_temperature_night_1 = temperature(
        41021,
        stride=200,
        writable=True,
        min_value=-5,
        max_value=150,
        raw_min=-50,
        raw_max=1500,
        digits=1,
        maker_key="VT1_N_HeizKL_Rk1",
        maker_category="KNL-VL",
        description="Vorlauftemperatur Nacht Punkt 1 der 4-Punkte-Kennlinie",
    )
    four_point_flow_temperature_night_2 = temperature(
        41022,
        stride=200,
        writable=True,
        min_value=-5,
        max_value=150,
        raw_min=-50,
        raw_max=1500,
        digits=1,
        maker_key="VT2_N_HeizKL_Rk1",
        maker_category="KNL-VL",
        description="Vorlauftemperatur Nacht Punkt 2 der 4-Punkte-Kennlinie",
    )
    four_point_flow_temperature_night_3 = temperature(
        41023,
        stride=200,
        writable=True,
        min_value=-5,
        max_value=150,
        raw_min=-50,
        raw_max=1500,
        digits=1,
        maker_key="VT3_N_HeizKL_Rk1",
        maker_category="KNL-VL",
        description="Vorlauftemperatur Nacht Punkt 3 der 4-Punkte-Kennlinie",
    )
    four_point_flow_temperature_night_4 = temperature(
        41024,
        stride=200,
        writable=True,
        min_value=-5,
        max_value=150,
        raw_min=-50,
        raw_max=1500,
        digits=1,
        maker_key="VT4_N_HeizKL_Rk1",
        maker_category="KNL-VL",
        description="Vorlauftemperatur Nacht Punkt 4 der 4-Punkte-Kennlinie",
    )
    four_point_return_flow_temperature_1 = temperature(
        41025,
        stride=200,
        writable=True,
        min_value=5,
        max_value=90,
        raw_min=50,
        raw_max=900,
        digits=1,
        maker_key="RL1_HeizKL_Rk1",
        maker_category="KNL-RL",
        description="Rücklauftemperatur Punkt 1 der 4-Punkte-Kennlinie",
    )
    four_point_return_flow_temperature_2 = temperature(
        41026,
        stride=200,
        writable=True,
        min_value=5,
        max_value=90,
        raw_min=50,
        raw_max=900,
        digits=1,
        maker_key="RL2_HeizKL_Rk1",
        maker_category="KNL-RL",
        description="Rücklauftemperatur Punkt 2 der 4-Punkte-Kennlinie",
    )
    four_point_return_flow_temperature_3 = temperature(
        41027,
        stride=200,
        writable=True,
        min_value=5,
        max_value=90,
        raw_min=50,
        raw_max=900,
        digits=1,
        maker_key="RL3_HeizKL_Rk1",
        maker_category="KNL-RL",
        description="Rücklauftemperatur Punkt 3 der 4-Punkte-Kennlinie",
    )
    four_point_return_flow_temperature_4 = temperature(
        41028,
        stride=200,
        writable=True,
        min_value=5,
        max_value=90,
        raw_min=50,
        raw_max=900,
        digits=1,
        maker_key="RL4_HeizKL_Rk1",
        maker_category="KNL-RL",
        description="Rücklauftemperatur Punkt 4 der 4-Punkte-Kennlinie",
    )
    return_flow_temperature_setpoint = temperature(
        41033,
        stride=200,
        min_value=5,
        max_value=90,
        raw_min=50,
        raw_max=900,
        digits=1,
        maker_key="RücklSollw_Rk1",
        maker_category="SOL-RL",
        description="Rücklaufsollwert Rk",
    )
    fixed_setpoint_day = temperature(
        41042,
        stride=200,
        writable=True,
        min_value=-5,
        max_value=130,
        raw_min=-50,
        raw_max=1300,
        digits=1,
        maker_key="TagSoll_FW_Rk1",
        maker_category="SOL-SON",
        description="Sollwert Tagbetrieb bei Festwertregelung",
    )
    fixed_setpoint_night = temperature(
        41043,
        stride=200,
        writable=True,
        min_value=-5,
        max_value=130,
        raw_min=-50,
        raw_max=1300,
        digits=1,
        maker_key="NachtSoll_FW_Rk1",
        maker_category="SOL-SON",
        description="Sollwert Nachtbetrieb bei Festwertregelung",
    )
    control_parameter_kp = gauge(
        41065,
        0.1,
        stride=200,
        writable=True,
        min_value=0.1,
        max_value=50.0,
        raw_min=1,
        raw_max=500,
        digits=1,
        maker_key="KpRk1Y1",
        description="Proportionalverstärkung Rk",
    )
    control_parameter_tn = integer(
        41066,
        stride=200,
        writable=True,
        min_value=1,
        max_value=999,
        raw_min=1,
        raw_max=999,
        digits=0,
        unit="s",
        maker_key="TnRk1Y1",
        description="Nachstellzeit Rk",
    )
    control_parameter_ty = integer(
        41067,
        stride=200,
        writable=True,
        min_value=15,
        max_value=240,
        raw_min=15,
        raw_max=240,
        digits=0,
        unit="s",
        maker_key="TyRk1",
        description="Laufzeit Stellantrieb Rk (bei 3-Punkt)",
    )
    control_parameter_tv = integer(
        41068,
        stride=200,
        writable=True,
        min_value=0,
        max_value=999,
        raw_min=0,
        raw_max=999,
        digits=0,
        unit="s",
        maker_key="TvY1",
        description="Vorhaltezeit Rk (bei 0-10V)",
    )
    control_parameter_hysteresis = gauge(
        41069,
        0.1,
        stride=200,
        writable=True,
        min_value=1.0,
        max_value=30.0,
        raw_min=10,
        raw_max=300,
        step=1,
        digits=1,
        unit="K",
        maker_key="SchaltdiffRk1",
        description="Schaltdifferenz Rk (bei 2-Punkt)",
    )
    control_parameter_minimum_on_time = integer(
        41070,
        stride=200,
        writable=True,
        min_value=0,
        max_value=10,
        raw_min=0,
        raw_max=10,
        digits=0,
        unit="min",
        maker_key="MinEinRk1",
        description="Minimale Einschaltzeit Rk (bei 2-Punkt)",
    )
    control_parameter_minimum_off_time = integer(
        41071,
        stride=200,
        writable=True,
        min_value=0,
        max_value=10,
        raw_min=0,
        raw_max=10,
        digits=0,
        unit="min",
        maker_key="MinAusRk1",
        description="Minimale Ausschaltzeit Rk (bei 2-Punkt)",
    )
    flow_control_deviation = gauge(
        41063,
        0.1,
        stride=200,
        signed=True,
        min_value=-100,
        max_value=100,
        raw_min=-1000,
        raw_max=1000,
        digits=1,
        unit="K",
        maker_key="Regeldiff_Vorl_Rk1",
        maker_category="RPA-SON",
        description="Regeldifferenz Vorlauf Rk",
    )

    ### coils
    three_point_control_enabled = coil(
        1036,
        stride=200,
        writable=True,
        false_key="two_point",
        true_key="three_point",
        false_label="Zweipunkt",
        true_label="3-Punkt",
        maker_key="FB123PktRegRk1",
        description="FB12: Regelungsart 3-Punkt Rk",
    )

    manual_active = coil(5, stride=1)

    pump_running = coil(57, stride=1, writable=True)
    valve_closing = coil(
        62,
        stride=2,
        false_key="stopped",
        true_key="closing",
        false_label="Halt",
        true_label="Zu",
        maker_key="Binärausg_BA6",
        maker_category="BEA-BA",
        description="Dreipunkt-Stellsignal Schließen",
    )
    valve_opening = coil(
        63,
        stride=2,
        false_key="stopped",
        true_key="opening",
        false_label="Halt",
        true_label="Auf",
        maker_key="Binärausg_BA7",
        maker_category="BEA-BA",
        description="Dreipunkt-Stellsignal Öffnen",
    )
    mode_control_autonomous = coil(
        89,
        stride=2,
        false_key="glt",
        true_key="autonomous",
        false_label="GLT",
        true_label="Autark",
        maker_key="EBN_BetrArt_Rk1",
        maker_category="EBN-BTR",
        description="Steuerungsebene Betriebsart",
    )
    valve_control_autonomous = coil(
        90,
        stride=2,
        false_key="glt",
        true_key="autonomous",
        false_label="GLT",
        true_label="Autark",
        maker_key="EBN_Stellsig_Rk1",
        maker_category="EBN-BTR",
        description="Steuerungsebene Stellsignal",
    )
    pump_control_autonomous = coil(
        96,
        stride=1,
        false_key="glt",
        true_key="autonomous",
        false_label="GLT",
        true_label="Autark",
        maker_key="EBN_Binär_BA1",
        maker_category="EBN-BA",
        description="Steuerungsebene Umwälzpumpe",
    )
    flow_setpoint_control_autonomous = coil(
        116,
        stride=2,
        false_key="glt",
        true_key="autonomous",
        false_label="GLT",
        true_label="Autark",
        maker_key="EBN_VorlSoll_Rk1",
        maker_category="EBN-VL",
        description="Steuerungsebene Vorlaufsollwert",
    )
    return_flow_temperature_setpoint_control_autonomous = coil(
        117,
        stride=2,
        false_key="glt",
        true_key="autonomous",
        false_label="GLT",
        true_label="Autark",
        maker_key="EBN_RückSoll_Rk1",
        maker_category="EBN-RL",
        description="Steuerungsebene Rücklaufsollwert",
    )
    room_setpoint_control_autonomous = coil(
        122,
        stride=1,
        false_key="glt",
        true_key="autonomous",
        false_label="GLT",
        true_label="Autark",
        maker_key="EBN_RaumSoll_Rk1",
        maker_category="EBN-RT",
        description="Steuerungsebene aktiver Raumsollwert",
    )
    trovis_5570_room_control_unit = coil(
        703,
        stride=1,
        writable=True,
        maker_key="FB03_RaumleitRk1",
        maker_category="CON-SON",
        description="TROVIS 5570 room control unit on device bus",
    )

    automatic = coil(1000, stride=200)

    day_active = coil(1001, stride=200)

    night_active = coil(1002, stride=200)

    hold_active = coil(1003, stride=200)

    setback_active = coil(1004, stride=200)

    heat_up_active = coil(1005, stride=200)
    return_limit_active = coil(1006, stride=200)

    outdoor_temperature_deactivation = coil(1007, stride=200)

    standby = coil(1008, stride=200)

    frost_protection = coil(1009, stride=200)

    optimization = coil(
        2107,
        stride=100,
        writable=True,
        maker_key="FB07_Optimierung_Rk1",
        description="Optimierung Rk",
    )
    adaptation = coil(
        2108,
        stride=100,
        writable=True,
        maker_key="FB08_Adaption_Rk1",
        description="Adaption Rk",
    )

    # Pump ownership is handled by the dedicated AUTO/ON/OFF API below.
    ebene_coils: dict[str, tuple[int, int]] = {}

    @property
    def pump_control_mode(self) -> PumpControlMode | None:
        """Return AUTO/ON/OFF for this circuit's circulation pump."""
        return self._pump_control_mode("pump_running", "pump_control_autonomous")

    async def async_set_pump_control_mode(
        self,
        mode: PumpControlMode | str,
        *,
        access_code: int = DEFAULT_WRITE_ACCESS_CODE,
    ) -> None:
        """Set this circuit's circulation pump to AUTO, ON, or OFF."""
        await self._async_set_pump_control_mode(
            "pump_running",
            "pump_control_autonomous",
            mode,
            access_code=access_code,
        )

    def heating_curve_parameters(self) -> HeatingCurveParameters:
        """Return a detached snapshot of all heating-curve input values."""
        return HeatingCurveParameters(
            day_active=self.day_active,
            minimum_flow_temperature=self.minimum_flow_temperature,
            maximum_flow_temperature=self.maximum_flow_temperature,
            room_setpoint_day=self.room_setpoint_day,
            room_setpoint_night=self.room_setpoint_night,
            gradient=self.gradient,
            level=self.level,
            return_flow_gradient=self.return_flow_gradient,
            return_flow_level=self.return_flow_level,
            maximum_return_flow_temperature=self.maximum_return_flow_temperature,
            return_flow_base_point=self.return_flow_base_point,
            return_flow_temperature_setpoint=self.return_flow_temperature_setpoint,
            four_point_outdoor_temperature_1=self.four_point_outdoor_temperature_1,
            four_point_outdoor_temperature_2=self.four_point_outdoor_temperature_2,
            four_point_outdoor_temperature_3=self.four_point_outdoor_temperature_3,
            four_point_outdoor_temperature_4=self.four_point_outdoor_temperature_4,
            four_point_flow_temperature_day_1=self.four_point_flow_temperature_day_1,
            four_point_flow_temperature_day_2=self.four_point_flow_temperature_day_2,
            four_point_flow_temperature_day_3=self.four_point_flow_temperature_day_3,
            four_point_flow_temperature_day_4=self.four_point_flow_temperature_day_4,
            four_point_flow_temperature_night_1=(
                self.four_point_flow_temperature_night_1
            ),
            four_point_flow_temperature_night_2=(
                self.four_point_flow_temperature_night_2
            ),
            four_point_flow_temperature_night_3=(
                self.four_point_flow_temperature_night_3
            ),
            four_point_flow_temperature_night_4=(
                self.four_point_flow_temperature_night_4
            ),
            four_point_return_flow_temperature_1=(
                self.four_point_return_flow_temperature_1
            ),
            four_point_return_flow_temperature_2=(
                self.four_point_return_flow_temperature_2
            ),
            four_point_return_flow_temperature_3=(
                self.four_point_return_flow_temperature_3
            ),
            four_point_return_flow_temperature_4=(
                self.four_point_return_flow_temperature_4
            ),
            fixed_setpoint_day=self.fixed_setpoint_day,
            fixed_setpoint_night=self.fixed_setpoint_night,
        )

    def heating_curve(
        self,
        mode: Literal["active", "day", "night"] = "active",
        *,
        operating_mode: HeatingCircuitControlMode = (
            HeatingCircuitControlMode.HEATING_CURVE
        ),
        curve: Literal["flow", "return"] = "flow",
    ) -> list[float] | None:
        """Calculate one characteristic from the circuit's current values."""
        return calculate_heating_curve(
            self.heating_curve_parameters(),
            mode,
            operating_mode=operating_mode,
            curve=curve,
        )

    async def set_mode(self, mode: OperatingMode) -> None:
        """Set one external operating mode and verify the effective mode."""
        await self.async_set_operating_mode(mode)

    async def release_mode_control(self) -> None:
        """Release operating-mode ownership back to the controller (AUTARK)."""
        await self.async_release_operating_mode_control()

    async def set_room_setpoint_day(self, celsius: float) -> None:
        """Set the day room setpoint (°C)."""
        await self.async_write_datapoint("room_setpoint_day", celsius)

    async def set_room_setpoint_night(self, celsius: float) -> None:
        """Set the night room setpoint (°C)."""
        await self.async_write_datapoint("room_setpoint_night", celsius)
