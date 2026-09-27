"""The domestic hot-water control circuit Rk4."""

from __future__ import annotations

from datetime import time

from ..data_model import (
    DEFAULT_WRITE_ACCESS_CODE,
    TrovisComponent,
    coil,
    enum,
    gauge,
    integer,
    temperature,
    time_value,
)
from ..enums import (
    DHW_OPERATING_MODE_OPTIONS,
    WEEKDAY_OPTIONS,
    OperatingMode,
    PumpControlMode,
    StorageStatus,
    Weekday,
)
from ..utils import TemperatureRange


class DomesticHotWater(TrovisComponent):
    """Domestic hot water, storage-tank charging and thermal disinfection."""

    ### registers

    setpoint_day = temperature(
        41800,
        writable=True,
        min_value=5,
        max_value=90,
        raw_min=50,
        raw_max=900,
        digits=1,
        maker_key="TW_Sollw",
        maker_category="SOL-WW",
        description="Trinkwasser Sollwert",
    )

    setpoint_max = temperature(
        41801,
        writable=True,
        min_value=5,
        max_value=90,
        raw_min=50,
        raw_max=900,
        digits=1,
        maker_key="MaxTW_Sollw",
        maker_category="SOL-WW",
        description="Maximale Einstellgrenztemperatur Trinkwassersollwert",
    )

    setpoint_min = temperature(
        41802,
        writable=True,
        min_value=5,
        max_value=90,
        raw_min=50,
        raw_max=900,
        digits=1,
        maker_key="MinTW_Sollw",
        maker_category="SOL-WW",
        description="Minimale Einstellgrenztemperatur Trinkwassersollwert",
    )

    hysteresis = gauge(
        41803,
        0.1,
        signed=False,
        writable=True,
        min_value=0,
        max_value=30,
        raw_min=0,
        raw_max=300,
        digits=1,
        unit="K",
        maker_key="Schaltdiff_TW",
        maker_category="SOL-WW",
        description="Schaltdifferenz Trinkwasser",
    )

    charging_temperature_boost = gauge(
        41804,
        0.1,
        signed=False,
        writable=True,
        min_value=0,
        max_value=50,
        raw_min=0,
        raw_max=500,
        digits=1,
        unit="K",
        maker_key="LadTempdiff_TW",
        maker_category="SOL-WW",
        description="Ladetemperaturüberhöhung",
    )

    storage_tank_charging_pump_lag_factor = gauge(
        41805,
        0.1,
        signed=False,
        writable=True,
        min_value=0.1,
        max_value=10,
        raw_min=1,
        raw_max=100,
        digits=1,
        maker_key="Nachlauf_SLP",
        maker_category="SOL-WW",
        description="Nachlauffaktor der Speicherladepumpe",
    )

    maximum_charging_temperature = temperature(
        41806,
        writable=True,
        min_value=0,
        max_value=90,
        raw_min=0,
        raw_max=900,
        digits=1,
        maker_key="Max_Lade_TW",
        maker_category="SOL-WW",
        description="Maximale Ladetemperatur Trinkwasser",
    )

    setpoint_night = temperature(
        41807,
        writable=True,
        min_value=5,
        max_value=90,
        raw_min=50,
        raw_max=900,
        digits=1,
        maker_key="TW_Haltewert",
        maker_category="SOL-WW",
        description="Haltewert Trinkwasser",
    )

    setpoint_active = temperature(
        41808,
        min_value=5,
        max_value=90,
        raw_min=50,
        raw_max=900,
        digits=1,
        maker_key="Aktiver_TW_Sollw",
        maker_category="SOL-WW",
        description="Aktiver Trinkwassersollwert",
    )

    special_setpoint = temperature(
        41809,
        writable=True,
        min_value=5,
        max_value=90,
        raw_min=50,
        raw_max=900,
        digits=1,
        maker_key="Sonder_TW_Sollw",
        maker_category="SOL-WW",
        description="Sonder-Trinkwassersollwert",
    )

    active_mode = enum(
        40077,
        OperatingMode,
        description="Effektive Betriebsart Trinkwasser",
    )

    mode = enum(
        40112,
        OperatingMode,
        writable=True,
        options=DHW_OPERATING_MODE_OPTIONS,
        maker_key="BetriebsArt_TW",
        maker_category="ALG-BTR",
        description="Externe Betriebsartvorgabe Trinkwasser",
    )

    storage_status = enum(
        41827,
        StorageStatus,
        maker_key="Speicherstatus",
        maker_category="ALG-BTR",
        description="Betriebszustand der Trinkwasserspeicherung",
    )

    maximum_return_flow_temperature = temperature(
        41828,
        writable=True,
        min_value=5,
        max_value=90,
        raw_min=50,
        raw_max=900,
        digits=1,
        maker_key="RücklSollw_TW",
        maker_category="SOL-RL",
        description="Maximale Rücklauftemperatur Trinkwasser",
    )

    disinfection_temperature = temperature(
        41830,
        writable=True,
        min_value=60,
        max_value=90,
        raw_min=600,
        raw_max=900,
        digits=1,
        maker_key="ThermDes_Sollw",
        maker_category="SOL-WW",
        description="Desinfektionstemperatur",
    )

    disinfection_weekday = enum(
        41831,
        Weekday,
        writable=True,
        options=WEEKDAY_OPTIONS,
        maker_key="ThermDes_Tag",
        maker_category="SOL-WW",
        description="Wochentag der thermischen Desinfektion",
    )

    disinfection_start = time_value(
        41832,
        writable=True,
        min_value=time(0, 0),
        max_value=time(23, 45),
        raw_min=0,
        raw_max=2345,
        maker_key="ThermDes_Start",
        maker_category="SOL-WW",
        description="Startzeit der thermischen Desinfektion",
    )

    disinfection_stop = time_value(
        41833,
        writable=True,
        min_value=time(0, 0),
        max_value=time(23, 45),
        raw_min=0,
        raw_max=2345,
        maker_key="ThermDes_Stop",
        maker_category="SOL-WW",
        description="Stoppzeit der thermischen Desinfektion",
    )

    active_charging_setpoint = temperature(
        41838,
        min_value=20,
        max_value=90,
        raw_min=200,
        raw_max=900,
        digits=1,
        maker_key="Aktiver_Lade_Soll",
        maker_category="SOL-WW",
        description="Aktiver Ladetemperatur-Sollwert",
    )

    disinfection_hold_time = integer(
        41839,
        signed=False,
        writable=True,
        min_value=0,
        max_value=255,
        raw_min=0,
        raw_max=255,
        digits=0,
        unit="min",
        maker_key="ThermDes_Halte",
        maker_category="SOL-WW",
        description="Haltezeit der Desinfektionstemperatur",
    )

    control_deviation = gauge(
        41863,
        0.1,
        signed=True,
        min_value=-100,
        max_value=100,
        raw_min=-1000,
        raw_max=1000,
        digits=1,
        unit="K",
        maker_key="Regeldiff_TW",
        maker_category="RPA-SON",
        description="Regeldifferenz Trinkwasserkreis",
    )

    control_parameter_kp = gauge(
        41865,
        0.1,
        writable=True,
        min_value=0.1,
        max_value=50.0,
        raw_min=1,
        raw_max=500,
        digits=1,
        maker_key="KpTW",
        description="Proportionalverstärkung Trinkwasserkreis",
    )

    control_parameter_tn = integer(
        41866,
        writable=True,
        min_value=1,
        max_value=999,
        raw_min=1,
        raw_max=999,
        digits=0,
        unit="s",
        maker_key="TnTW",
        description="Nachstellzeit Trinkwasserkreis",
    )

    control_parameter_ty = integer(
        41867,
        writable=True,
        min_value=15,
        max_value=240,
        raw_min=15,
        raw_max=240,
        digits=0,
        unit="s",
        maker_key="TyTW",
        description="Laufzeit Stellantrieb Trinkwasserkreis (bei 3-Punkt)",
    )

    control_parameter_tv = integer(
        41868,
        writable=True,
        min_value=0,
        max_value=999,
        raw_min=0,
        raw_max=999,
        digits=0,
        unit="s",
        maker_key="TvTW",
        description="Vorhaltezeit Trinkwasserkreis (bei 0-10V)",
    )

    control_parameter_hysteresis = gauge(
        41869,
        0.1,
        writable=True,
        min_value=1.0,
        max_value=30.0,
        raw_min=10,
        raw_max=300,
        step=1,
        digits=1,
        unit="K",
        maker_key="SchaltdiffTW2P",
        description="Schaltdifferenz Trinkwasserkreis (bei 2-Punkt)",
    )

    control_parameter_minimum_on_time = integer(
        41870,
        writable=True,
        min_value=0,
        max_value=10,
        raw_min=0,
        raw_max=10,
        digits=0,
        unit="min",
        maker_key="MinEinTW",
        description="Minimale Einschaltzeit Trinkwasserkreis (bei 2-Punkt)",
    )

    control_parameter_minimum_off_time = integer(
        41871,
        writable=True,
        min_value=0,
        max_value=10,
        raw_min=0,
        raw_max=10,
        digits=0,
        unit="min",
        maker_key="MinAusTW",
        description="Minimale Ausschaltzeit Trinkwasserkreis (bei 2-Punkt)",
    )

    ### coils

    manual_active = coil(8)

    storage_tank_charging_pump_running = coil(60, writable=True)

    circulation_pump_running = coil(61, writable=True)

    storage_tank_charging_pump_control_autonomous = coil(
        99,
        false_key="glt",
        true_key="autonomous",
        false_label="GLT",
        true_label="Autark",
        maker_key="EBN_Binär_BA4",
        maker_category="EBN-BA",
        description="Steuerungsebene Speicherladepumpe",
    )

    mode_control_autonomous = coil(
        95,
        false_key="glt",
        true_key="autonomous",
        false_label="GLT",
        true_label="Autark",
        maker_key="EBN_BetrArt_TW",
        maker_category="EBN-BTR",
        description="Steuerungsebene Betriebsart Trinkwasser",
    )

    circulation_pump_control_autonomous = coil(
        100,
        false_key="glt",
        true_key="autonomous",
        false_label="GLT",
        true_label="Autark",
        maker_key="EBN_Binär_BA5",
        maker_category="EBN-BA",
        description="Steuerungsebene Zirkulationspumpe",
    )

    special_setpoint_control_autonomous = coil(
        112,
        false_key="glt",
        true_key="autonomous",
        false_label="GLT",
        true_label="Autark",
        maker_key="EBN_Son_TW_Sollw",
        maker_category="EBN-VL",
        description="Steuerungsebene Sonder-Trinkwassersollwert",
    )

    three_point_control_enabled = coil(
        412,
        writable=True,
        false_key="two_point",
        true_key="three_point",
        false_label="Zweipunkt",
        true_label="3-Punkt",
        description="FB12: Regelungsart 3-Punkt Trinkwasserkreis",
    )

    intermediate_heating_function_enabled = coil(
        407,
        writable=True,
        maker_key="FB07_Zwischenhzg",
        maker_category="CON-WW",
        description="Funktionsblock CO4-FB07 Zwischenheizbetrieb",
    )

    disinfection_enabled = coil(
        414,
        writable=True,
        maker_key="FB14_ThermDes",
        maker_category="CON-WW",
        description="Funktionsblock CO4-FB14 Thermische Desinfektion",
    )

    automatic = coil(1800)

    disinfection_active = coil(1801)

    priority = coil(1802)

    maximum_charging_temperature_limit_active = coil(1803)

    return_limit_active = coil(1804)

    standby = coil(1805)

    frost_protection = coil(1806)

    # IMPORTANT: CL1807 is treated as a command/trigger, not as an ordinary
    # persistent state coil. The historical API explicitly describes it as
    # "Trigger a one-off storage charge". Until real-controller/sniffer
    # tests prove that repeating CL1807 is harmless, a missing Modbus write
    # response must therefore remain ambiguous: the controller may already
    # have accepted the trigger even though the response was lost. Blindly
    # retrying could start the action twice, restart it, or extend its effect.
    # For that reason CL1807 is EXPLICITLY excluded from the generic
    # write -> targeted readback -> retry mechanism below. A timeout is
    # surfaced to the caller without a second CL1807 write. This exception
    # must not be removed merely because ordinary writable coils are safe to
    # retry; change it only after the command semantics have been verified on
    # real hardware.
    forced_charging = coil(1807, writable=True)

    forced_charging_uses_storage_tank_sensor_2 = coil(
        1809,
        writable=True,
        false_key="inactive",
        true_key="active",
        false_label="Inaktiv",
        true_label="Aktiv",
        maker_key="SF2_anstatt_SF1",
        maker_category="ALG-BTR",
        description="Zwangsladung durch Umschaltung von SF1 auf SF2",
    )

    storage_tank_charging_active = coil(
        1810,
        false_key="inactive",
        true_key="active",
        false_label="Inaktiv",
        true_label="Aktiv",
        maker_key="Speicherlad_TW",
        maker_category="ALG-SON",
        description="Speicherladung aktiv",
    )

    storage_tank_charging_enabled = coil(
        1811,
        writable=True,
        false_key="inactive",
        true_key="active",
        false_label="Inaktiv",
        true_label="Aktiv",
        maker_key="Speicherlad_En",
        maker_category="ALG-SON",
        description="Freigabe Speicherladung",
    )

    storage_tank_charging_locked = coil(
        1812,
        false_key="inactive",
        true_key="active",
        false_label="Inaktiv",
        true_label="Aktiv",
        maker_key="SpeicherladSperr",
        maker_category="ALG-SON",
        description="Speicherladung durch Entladeschutz gesperrt",
    )

    intermediate_heating_operation = coil(
        1831,
        writable=True,
        maker_key="FB07_Zwischenhzg",
        maker_category="CON-WW",
        description=(
            "Zwischenheizbetrieb; von der 55Pro-App und der bewährten "
            "Legacy-Konfiguration verwendeter Spiegelpunkt"
        ),
    )

    # See the CL1807 warning above: command/edge-trigger writes are not
    # automatically repeated when their response is lost.
    non_retryable_write_fields = frozenset({"forced_charging"})

    # Pump ownership is handled by dedicated AUTO/ON/OFF helpers. The special
    # setpoint keeps the ordinary generic Ebene pre-write behavior.
    ebene_coils = {"special_setpoint": (112, 0)}

    @property
    def storage_tank_charging_pump_control_mode(self) -> PumpControlMode | None:
        """Return AUTO/ON/OFF for the storage-tank charging pump."""
        return self._pump_control_mode(
            "storage_tank_charging_pump_running",
            "storage_tank_charging_pump_control_autonomous",
        )

    async def async_set_storage_tank_charging_pump_control_mode(
        self,
        mode: PumpControlMode | str,
        *,
        access_code: int = DEFAULT_WRITE_ACCESS_CODE,
    ) -> None:
        """Set the storage-tank charging pump to AUTO, ON, or OFF."""
        await self._async_set_pump_control_mode(
            "storage_tank_charging_pump_running",
            "storage_tank_charging_pump_control_autonomous",
            mode,
            access_code=access_code,
        )

    @property
    def circulation_pump_control_mode(self) -> PumpControlMode | None:
        """Return AUTO/ON/OFF for the DHW circulation pump."""
        return self._pump_control_mode(
            "circulation_pump_running",
            "circulation_pump_control_autonomous",
        )

    async def async_set_circulation_pump_control_mode(
        self,
        mode: PumpControlMode | str,
        *,
        access_code: int = DEFAULT_WRITE_ACCESS_CODE,
    ) -> None:
        """Set the DHW circulation pump to AUTO, ON, or OFF."""
        await self._async_set_pump_control_mode(
            "circulation_pump_running",
            "circulation_pump_control_autonomous",
            mode,
            access_code=access_code,
        )

    @property
    def day_temperature_range(self) -> TemperatureRange | None:
        """Day setpoint range implied by setpoint and hysteresis."""
        if self.setpoint_day is None or self.hysteresis is None:
            return None
        return TemperatureRange(
            minimum=self.setpoint_day,
            maximum=round(self.setpoint_day + self.hysteresis, 1),
        )

    @property
    def night_temperature_range(self) -> TemperatureRange | None:
        """Night/holding range implied by hold value and hysteresis."""
        if self.setpoint_night is None or self.hysteresis is None:
            return None
        return TemperatureRange(
            minimum=self.setpoint_night,
            maximum=round(self.setpoint_night + self.hysteresis, 1),
        )

    async def set_setpoint(self, celsius: float) -> None:
        """Set the domestic hot-water day setpoint (°C)."""
        await self.async_write_datapoint("setpoint_day", celsius)

    async def set_mode(self, mode: OperatingMode) -> None:
        """Set one external operating mode and verify the effective mode."""
        await self.async_set_operating_mode(mode)

    async def release_mode_control(self) -> None:
        """Release operating-mode ownership back to the controller (AUTARK)."""
        await self.async_release_operating_mode_control()

    async def set_disinfection_start(self, value: time) -> None:
        """Set the start of the thermal-disinfection window."""
        await self.async_write_datapoint("disinfection_start", value)

    async def set_disinfection_stop(self, value: time) -> None:
        """Set the end of the thermal-disinfection window."""
        await self.async_write_datapoint("disinfection_stop", value)

    async def start_forced_charging(self) -> None:
        """Trigger a one-off storage charge."""
        await self.async_write_datapoint("forced_charging", True)
