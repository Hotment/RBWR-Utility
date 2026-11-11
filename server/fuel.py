"""
RBWR Core Fuel Level Estimation & Refueling Detection Engine

Provides multi-snapshot rolling evaluation, non-linear core physics modeling,
window-based settling steadiness checks, 1D Kalman state-space filtering,
RTS backward smoothing, and change-point refueling outage detection for
Unit 1 and Unit 2 in Roblox RBWR.

Reactor Model Context:
- Different reactor modes only alter how control rods, recirculation flow, and fuel burnup determine APRM (core reactivity).
- Refueling detection and fuel level formulas are calibrated specifically for Classic mode physics.
- The ratio between APRM, electric power, and grid demand is constant across all modes.

Physical Mechanisms & Modeling:
1. Non-linear S-shaped integral control rod worth curve (flux profile weighting).
2. Power-to-flow coupled steam void fraction with natural circulation base flow.
3. Steam dome pressure reactivity feedback compensation.
4. Xenon-135 neutron poison saturation dampening near boundary.
5. Water moderator density curve from reactor temperature.
6. Inverse-variance measurement sensitivity weighting via the Delta Method.
7. Energy-integrated depletion dynamics (state prediction via Effective Full Power Hours).
8. 1D Kalman Filter and Rauch-Tung-Striebel (RTS) backward smoother.
9. Statistical change-point jump scoring for refueling outage verification.
"""

import datetime
import math
import statistics
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from server.models import (
        UnitConfig,
        ConfirmedRefuel,
        SteadySample,
        UnitFuelAssessment,
        ServerFuelAssessment,
        UnitState,
    )
except ImportError:
    from models import (
        UnitConfig,
        ConfirmedRefuel,
        SteadySample,
        UnitFuelAssessment,
        ServerFuelAssessment,
        UnitState,
    )

__all__ = [
    "CALIBRATION_CONST_U1",
    "CALIBRATION_CONST_U2",
    "VOID_COEFF_U1",
    "VOID_COEFF_U2",
    "REFUEL_DOWNTIME_MIN_U1",
    "REFUEL_DOWNTIME_MAX_U1",
    "REFUEL_DOWNTIME_MIN_U2",
    "REFUEL_DOWNTIME_MAX_U2",
    "REFUEL_PRE_FUEL_MAX",
    "REFUEL_POST_FUEL_MIN_U1",
    "REFUEL_POST_FUEL_MIN_U2",
    "MAX_D_APRM_DT",
    "MAX_D_ROD_DT",
    "MAX_D_TEMP_DT",
    "MAX_D_RECIRC_DT",
    "MAX_D_XE_DT",
    "MAX_GAP_STEP_SEC",
    "OUTAGE_VERIFY_TIMEOUT_SEC",
    "MIN_STEADY_SAMPLES_FOR_TREND",
    "MIN_TIME_SPAN_FOR_TREND_SEC",
    "FUEL_BOUND_LOWER",
    "FUEL_BOUND_UPPER",
    "UNIT_CONFIGS",
    "UnitConfig",
    "resolve_unit_name",
    "rod_worth_factor",
    "core_void_factor",
    "pressure_factor",
    "xenon_factor",
    "fuel_level",
    "calculate_measurement_variance",
    "calculate_u1_fuel_level",
    "calculate_u2_fuel_level",
    "calculate_unit_fuel_level",
    "parse_iso_timestamp",
    "parse_and_sort_snapshots",
    "detect_refuel_events",
    "run_kalman_smoother",
    "approximate_fuel_from_snapshots",
    "evaluate_server_fuel",
    "get_refuel_info_by_epoch",
]

# Calibrated core reactivity constants (Joint empirical fit across Classic mode ground truth)
CALIBRATION_CONST_U1 = 44.7987
CALIBRATION_CONST_U2 = 41.4260

# Void coefficients
VOID_COEFF_U1 = 0.25
VOID_COEFF_U2 = 0.25

# Refueling detection physical thresholds
REFUEL_DOWNTIME_MIN_U1 = 300.0    # At least 5 minutes offline
REFUEL_DOWNTIME_MAX_U1 = 1260.0   # At most 20 minutes (with 1-minute buffer)
REFUEL_DOWNTIME_MIN_U2 = 3000.0   # At least 50 minutes offline
REFUEL_DOWNTIME_MAX_U2 = None     # Unit 2 prolonged outages decay via scoring rather than hard cutoff

# Pre-outage fuel level below 67.0% (in-game 65% threshold with 2% measurement margin)
REFUEL_PRE_FUEL_MAX = 67.0
REFUEL_POST_FUEL_MIN_U1 = 88.0    # Post-refuel fresh core threshold for Unit 1
REFUEL_POST_FUEL_MIN_U2 = 90.0    # Post-refuel fresh core threshold for Unit 2
REFUEL_EXPECTED_U1 = 96.5         # Automatic refuel baseline for Unit 1 (range 95-97%)
REFUEL_EXPECTED_U2 = 97.0         # Manual rod replacement baseline for Unit 2 (range 96-99%, most often 97%)

# Steady-state rate-of-change derivative limits (units per second)
MAX_D_APRM_DT = 0.08    # Max APRM change rate: 0.08 %/sec (~4.8%/min)
MAX_D_ROD_DT = 0.04     # Max rod change rate: 0.04 %/sec (~2.4%/min)
MAX_D_TEMP_DT = 0.20    # Max temperature change rate: 0.20 C/sec (~12 C/min)
MAX_D_RECIRC_DT = 0.15  # Max core recirc change rate: 0.15 %/sec (~9 %/min)
MAX_D_XE_DT = 0.005     # Max xenon change rate: 0.005 %/sec (~0.3%/min)

# Operational filtering thresholds
MIN_ON_GRID_OUTPUT_MW = 0.0       # Must be positive generation to reflect on-grid boiling regime
MIN_OPERATING_APRM = 20.0         # Baseline envelope APRM threshold
SETTLING_TIME_SEC = 15.0          # Empirical core settling duration (U1 ~10s, U2 ~15s)
WINDOW_STEADY_SAMPLES = 2         # Consecutive close samples required to establish stability

# Timing windows
MAX_GAP_STEP_SEC = 180.0             # Samples spaced wider than 3 minutes cannot prove steadiness
OUTAGE_VERIFY_TIMEOUT_SEC = 7200.0   # 2 hours post-restart to observe fresh core before discarding candidate
MIN_STEADY_SAMPLES_FOR_TREND = 6     # Minimum steady points for linear burnup regression
MIN_TIME_SPAN_FOR_TREND_SEC = 900.0  # 15 minutes span required for burnup trend line

# Fuel physical plausibility bounds
FUEL_BOUND_LOWER = 10.0
FUEL_BOUND_UPPER = 125.0

# Unit configuration catalog
UNIT_CONFIGS = {
    "Unit1": UnitConfig(
        name="Unit1",
        calibration=CALIBRATION_CONST_U1,
        void_coeff=VOID_COEFF_U1,
        downtime_min=REFUEL_DOWNTIME_MIN_U1,
        downtime_max=REFUEL_DOWNTIME_MAX_U1,
        post_fuel_min=REFUEL_POST_FUEL_MIN_U1,
        rod_alpha=0.55,
        recirc_coeff=0.25,
        pressure_coeff=0.25,
        natural_flow_fraction=0.25,
        nominal_pressure_kpa=7000.0,
        expected_refuel_fuel=REFUEL_EXPECTED_U1,
        default_burn_rate_per_efph=2.40,
    ),
    "Unit2": UnitConfig(
        name="Unit2",
        calibration=CALIBRATION_CONST_U2,
        void_coeff=VOID_COEFF_U2,
        downtime_min=REFUEL_DOWNTIME_MIN_U2,
        downtime_max=REFUEL_DOWNTIME_MAX_U2,
        post_fuel_min=REFUEL_POST_FUEL_MIN_U2,
        rod_alpha=0.55,
        recirc_coeff=0.25,
        pressure_coeff=0.25,
        natural_flow_fraction=0.25,
        nominal_pressure_kpa=7000.0,
        expected_refuel_fuel=REFUEL_EXPECTED_U2,
        default_burn_rate_per_efph=2.40,
    ),
}

ParsedSnapshot = Tuple[float, str, Dict[str, Any]]


def resolve_unit_name(unit_name: str) -> str:
    cleaned = str(unit_name).strip().upper().replace(" ", "").replace("_", "")
    if cleaned in ("UNIT1", "U1", "1"):
        return "Unit1"
    if cleaned in ("UNIT2", "U2", "2"):
        return "Unit2"
    raise ValueError(f"Unknown reactor unit: {unit_name}. Expected 'Unit1' or 'Unit2'.")


def _water_density(temp: float) -> float:
    """Calculates water moderator density factor (g/cm^3) from reactor temperature in Celsius."""
    return (
        -4.468e-6 * (temp ** 3)
        - 5.603e-4 * (temp ** 2)
        - 0.4291 * temp
        + 1010.04
    ) / 1000.0


def rod_worth_factor(rods: float, alpha: float = 0.30) -> float:
    """
    Calculates control rod reactivity worth factor for Classic mode.
    Follows linear scaling calibrated to game core physics: alpha + (1 - alpha) * (rods / 100).
    """
    r_frac = min(1.0, max(0.0, rods / 100.0))
    return alpha + (1.0 - alpha) * r_frac


def core_void_factor(aprm: float, void_coeff: float = 0.42) -> float:
    """
    Calculates steam void negative reactivity feedback factor for Classic mode.
    f_void = 1.0 - void_coeff * (APRM / 100.0).
    """
    aprm_frac = max(0.0, aprm / 100.0)
    f_void = 1.0 - void_coeff * min(1.5, aprm_frac)
    return max(0.10, f_void)


def pressure_factor(pressure_kpa: float, pressure_coeff: float = 0.15, nominal_kpa: float = 7000.0) -> float:
    """Calculates steam dome pressure reactivity feedback factor."""
    if pressure_kpa < 1000.0:
        return 1.0
    delta_frac = (pressure_kpa - nominal_kpa) / nominal_kpa
    clamped_delta = max(-0.5, min(0.5, delta_frac))
    return 1.0 + pressure_coeff * clamped_delta


def xenon_factor(xenon: float) -> Optional[float]:
    """Calculates Xenon-135 neutron poison factor with boundary saturation dampening."""
    if xenon >= 4.40:
        return None
    f_xe = 1.0 - (xenon / 4.5)
    return max(0.05, f_xe)


def fuel_level(state: UnitState, cfg: UnitConfig) -> Optional[float]:
    """
    Calculates estimated core fuel percentage for a reactor unit under steady-state conditions.
    Returns None if reactor is offline, rods inserted, xenon poisoned, or physical denominator is invalid.
    """
    if state.rods <= 1.0 or state.aprm < 1.0:
        return None

    f_xe = xenon_factor(state.xenon)
    if f_xe is None:
        return None

    f_rod = rod_worth_factor(state.rods, cfg.rod_alpha)
    f_recirc = 1.0 + cfg.recirc_coeff * (min(100.0, max(0.0, state.recirc)) / 100.0)
    f_void = core_void_factor(state.aprm, cfg.void_coeff)
    rho = _water_density(state.temp)
    f_level = 1.0 if state.level >= -0.5 else max(0.1, 1.0 + (state.level + 0.5) * 0.25)
    f_press = pressure_factor(state.pressure, cfg.pressure_coeff, cfg.nominal_pressure_kpa)

    denom = f_rod * f_recirc * f_void * f_xe * rho * f_level * f_press
    if denom <= 0.0:
        return None

    val = cfg.calibration / denom
    return round(val, 2)


def calculate_measurement_variance(state: UnitState, cfg: UnitConfig, fuel_val: float) -> float:
    """
    Computes measurement error variance R_k for a snapshot using the Delta Method (error propagation).
    High-sensitivity or edge-of-envelope samples receive high variance (down-weighting in Kalman filter),
    while optimal, steady nominal generation points receive minimal variance.
    """
    if fuel_val <= 0.0:
        return 100.0

    f_rod = rod_worth_factor(state.rods, cfg.rod_alpha)
    d_frod_dr = (1.0 - cfg.rod_alpha) / 100.0
    sens_rod = (d_frod_dr / max(0.1, f_rod)) * fuel_val

    f_void = core_void_factor(state.aprm, cfg.void_coeff)
    sens_aprm = (cfg.void_coeff / (100.0 * max(0.1, f_void))) * fuel_val

    f_xe = max(0.05, 1.0 - state.xenon / 4.5)
    sens_xe = (1.0 / (4.5 * f_xe)) * fuel_val

    sens_temp = 0.0025 * fuel_val

    sigma_rod = 0.25     # +/- 0.25% rod position uncertainty
    sigma_aprm = 0.35    # +/- 0.35% APRM noise
    sigma_xe = 0.01      # +/- 0.01% xenon computation
    sigma_temp = 0.25    # +/- 0.25 C temperature fluctuation

    base_model_variance = 0.35
    total_var = (
        (sens_rod * sigma_rod) ** 2
        + (sens_aprm * sigma_aprm) ** 2
        + (sens_xe * sigma_xe) ** 2
        + (sens_temp * sigma_temp) ** 2
        + base_model_variance
    )
    return max(0.30, min(100.0, total_var))


def calculate_u1_fuel_level(u1_data: Union[Dict[str, Any], UnitState]) -> Optional[float]:
    if isinstance(u1_data, UnitState):
        state = u1_data
    elif isinstance(u1_data, dict):
        state = UnitState.from_dict(u1_data, "Unit1")
    else:
        return None
    return fuel_level(state, UNIT_CONFIGS["Unit1"])


def calculate_u2_fuel_level(u2_data: Union[Dict[str, Any], UnitState]) -> Optional[float]:
    if isinstance(u2_data, UnitState):
        state = u2_data
    elif isinstance(u2_data, dict):
        state = UnitState.from_dict(u2_data, "Unit2")
    else:
        return None
    return fuel_level(state, UNIT_CONFIGS["Unit2"])


def calculate_unit_fuel_level(unit_name: str, unit_data: Union[Dict[str, Any], UnitState]) -> Optional[float]:
    clean_unit = resolve_unit_name(unit_name)
    cfg = UNIT_CONFIGS[clean_unit]
    if isinstance(unit_data, UnitState):
        state = unit_data
    elif isinstance(unit_data, dict):
        state = UnitState.from_dict(unit_data, clean_unit)
    else:
        return None
    return fuel_level(state, cfg)


def parse_iso_timestamp(ts: Any) -> Optional[float]:
    if not ts or not isinstance(ts, str):
        return None
    try:
        clean_ts = ts.strip().replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(clean_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def parse_and_sort_snapshots(
    snapshots: Union[Dict[str, Any], List[ParsedSnapshot]]
) -> Tuple[List[ParsedSnapshot], int]:
    if isinstance(snapshots, list):
        sorted_list = sorted(snapshots, key=lambda x: x[0])
        return sorted_list, 0

    if not isinstance(snapshots, dict):
        return [], 0

    parsed: List[ParsedSnapshot] = []
    malformed_count = 0
    for ts_key, snap_data in snapshots.items():
        if str(ts_key).startswith("_"):
            continue
        if not isinstance(snap_data, dict):
            continue
        epoch = parse_iso_timestamp(str(ts_key))
        if epoch is None:
            malformed_count += 1
            continue
        parsed.append((epoch, str(ts_key), snap_data))

    parsed.sort(key=lambda x: x[0])
    return parsed, malformed_count


@dataclass
class RefuelEventRecord:
    downtime_minutes: float
    pre_fuel: Optional[float]
    post_fuel: float
    restart_time: Optional[str]
    cutoff_epoch: float
    start_epoch: float
    end_epoch: float
    jump_z_score: Optional[float] = None


@dataclass
class RefuelDetectionResult:
    events: List[RefuelEventRecord]
    latest_confirmed: Optional[ConfirmedRefuel]
    refuel_map_by_epoch: Dict[float, Tuple[bool, float]]
    steady_samples: List[SteadySample]
    latest_unit_state: UnitState
    latest_instantaneous_fuel: Optional[float]
    latest_timestamp: Optional[str]
    detected_mode: Optional[str]


def detect_refuel_events(
    parsed_snapshots: List[ParsedSnapshot],
    cfg: UnitConfig,
) -> RefuelDetectionResult:
    if not parsed_snapshots:
        return RefuelDetectionResult(
            events=[],
            latest_confirmed=None,
            refuel_map_by_epoch={},
            steady_samples=[],
            latest_unit_state=UnitState(),
            latest_instantaneous_fuel=None,
            latest_timestamp=None,
            detected_mode=None,
        )

    refuel_map: Dict[float, Tuple[bool, float]] = {}
    steady_samples: List[SteadySample] = []
    confirmed_events: List[RefuelEventRecord] = []

    last_valid_epoch: Optional[float] = None
    last_steady_fuel: Optional[float] = None
    last_steady_epoch: Optional[float] = None
    kf_x: Optional[float] = None
    kf_p: float = 9.0
    kf_prev_epoch: Optional[float] = None

    recent_history: List[Tuple[float, UnitState]] = []

    in_outage: bool = False
    outage_start: Optional[float] = None
    outage_pre_fuel: Optional[float] = None
    is_refuel_candidate: bool = False
    current_outage_epochs: List[float] = []

    pending_verification: Optional[Dict[str, Any]] = None
    detected_mode: Optional[str] = None

    latest_unit_st = UnitState()
    latest_inst_fuel: Optional[float] = None
    latest_ts: Optional[str] = None

    for epoch, ts, snap_data in parsed_snapshots:
        latest_ts = ts
        unit_raw = snap_data.get(cfg.name) if isinstance(snap_data, dict) else {}
        unit_st = UnitState.from_dict(unit_raw if isinstance(unit_raw, dict) else {}, cfg.name)
        latest_unit_st = unit_st

        mode_val = unit_st.mode or (snap_data.get("Mode") if isinstance(snap_data, dict) else None)
        if mode_val and not detected_mode:
            detected_mode = str(mode_val).strip()

        is_running = (unit_st.aprm >= 5.0 or unit_st.rods > 1.0 or unit_st.output_mw > 0.0)
        if is_running:
            last_valid_epoch = epoch

        fuel_val = fuel_level(unit_st, cfg)
        latest_inst_fuel = fuel_val

        if kf_x is not None and kf_prev_epoch is not None:
            dt_kf = max(0.0, epoch - kf_prev_epoch)
            if dt_kf > 0.0:
                delta_efph = (max(0.0, unit_st.aprm) / 100.0) * (dt_kf / 3600.0)
                kf_x = max(0.0, kf_x - cfg.default_burn_rate_per_efph * delta_efph)
                kf_p = min(50.0, kf_p + 0.25 * max(0.02, delta_efph) + 0.015)
        kf_prev_epoch = epoch

        is_steady = False
        if unit_st.is_operating_envelope:
            if recent_history and (epoch - recent_history[-1][0]) > MAX_GAP_STEP_SEC:
                recent_history.clear()
            recent_history.append((epoch, unit_st))
            if len(recent_history) > 5:
                recent_history.pop(0)

            if len(recent_history) >= WINDOW_STEADY_SAMPLES:
                window_ok = True
                for i in range(1, len(recent_history)):
                    t_prev, st_prev = recent_history[i - 1]
                    t_curr, st_curr = recent_history[i]
                    dt_step = t_curr - t_prev
                    if dt_step <= 0.0 or dt_step > MAX_GAP_STEP_SEC:
                        window_ok = False
                        break
                    d_aprm = abs(st_curr.aprm - st_prev.aprm) / dt_step
                    d_rod = abs(st_curr.rods - st_prev.rods) / dt_step
                    d_temp = abs(st_curr.temp - st_prev.temp) / dt_step
                    d_recirc = abs(st_curr.recirc - st_prev.recirc) / dt_step
                    d_xe = abs(st_curr.xenon - st_prev.xenon) / dt_step
                    if (
                        d_aprm > MAX_D_APRM_DT
                        or d_rod > MAX_D_ROD_DT
                        or d_temp > MAX_D_TEMP_DT
                        or d_recirc > MAX_D_RECIRC_DT
                        or d_xe > MAX_D_XE_DT
                    ):
                        window_ok = False
                        break
                if window_ok:
                    is_steady = True
        else:
            recent_history.clear()

        if is_steady and fuel_val is not None and FUEL_BOUND_LOWER <= fuel_val <= FUEL_BOUND_UPPER:
            r_var = calculate_measurement_variance(unit_st, cfg, fuel_val)
            if kf_x is None:
                kf_x = fuel_val
                kf_p = min(25.0, r_var)
            else:
                k_gain = kf_p / (kf_p + r_var) if (kf_p + r_var) > 0.0 else 0.5
                kf_x = kf_x + k_gain * (fuel_val - kf_x)
                kf_p = max(0.05, (1.0 - k_gain) * kf_p)
            kf_x = max(FUEL_BOUND_LOWER, min(FUEL_BOUND_UPPER, kf_x))
            steady_samples.append(
                SteadySample(epoch=epoch, timestamp=ts, fuel_val=fuel_val, aprm=unit_st.aprm, rods=unit_st.rods)
            )
            last_steady_fuel = round(kf_x, 2)
            last_steady_epoch = epoch

        rods_inserted = unit_st.is_rods_inserted

        if rods_inserted:
            if not in_outage:
                in_outage = True
                outage_start = epoch
                outage_pre_fuel = last_steady_fuel
                current_outage_epochs = [epoch]
                is_refuel_candidate = (outage_pre_fuel is not None and outage_pre_fuel < REFUEL_PRE_FUEL_MAX)
            else:
                current_outage_epochs.append(epoch)

            if is_refuel_candidate:
                elapsed_min = max(0.0, (epoch - (outage_start or epoch)) / 60.0)
                refuel_map[epoch] = (True, elapsed_min)
            else:
                refuel_map[epoch] = (False, 0.0)
        else:
            if in_outage:
                in_outage = False
                restart_epoch = epoch
                dt_outage = max(0.0, restart_epoch - (outage_start or epoch))
                dt_valid = (dt_outage >= cfg.downtime_min) and (
                    cfg.downtime_max is None or dt_outage <= cfg.downtime_max
                )

                if dt_valid and is_refuel_candidate:
                    pending_verification = {
                        "epochs": list(current_outage_epochs),
                        "start": outage_start,
                        "restart": restart_epoch,
                        "restart_ts": ts,
                        "downtime_sec": dt_outage,
                        "pre_fuel": outage_pre_fuel,
                    }
                else:
                    for ep in current_outage_epochs:
                        refuel_map[ep] = (False, 0.0)
                    pending_verification = None
                current_outage_epochs = []
            elif (
                pending_verification is None
                and last_valid_epoch is not None
                and (epoch - last_valid_epoch) >= cfg.downtime_min
            ):
                dt_gap = epoch - last_valid_epoch
                dt_valid = (cfg.downtime_max is None or dt_gap <= cfg.downtime_max)
                is_cand = (last_steady_fuel is not None and last_steady_fuel < REFUEL_PRE_FUEL_MAX)
                if dt_valid and is_cand:
                    pending_verification = {
                        "epochs": [],
                        "start": last_valid_epoch,
                        "restart": epoch,
                        "restart_ts": ts,
                        "downtime_sec": dt_gap,
                        "pre_fuel": last_steady_fuel,
                    }

            if pending_verification is not None:
                if fuel_val is not None:
                    pre_f = pending_verification.get("pre_fuel")
                    jump_ok = (fuel_val >= cfg.post_fuel_min) or (
                        pre_f is not None and (fuel_val - pre_f) >= 15.0 and fuel_val >= 85.0
                    )
                    if jump_ok:
                        z_score = None
                        if pre_f is not None:
                            jump_std = math.sqrt(max(1.0, kf_p + 2.0))
                            z_score = round((fuel_val - pre_f) / jump_std, 2)
                        event = RefuelEventRecord(
                            downtime_minutes=round(pending_verification["downtime_sec"] / 60.0, 1),
                            pre_fuel=round(pre_f, 2) if pre_f is not None else None,
                            post_fuel=round(fuel_val, 2),
                            restart_time=pending_verification["restart_ts"],
                            cutoff_epoch=pending_verification["restart"],
                            start_epoch=pending_verification["start"],
                            end_epoch=pending_verification["restart"],
                            jump_z_score=z_score,
                        )
                        confirmed_events.append(event)
                        pending_verification = None
                        kf_x = float(fuel_val)
                        kf_p = 3.0
                        last_steady_fuel = round(kf_x, 2)
                    elif (epoch - pending_verification["restart"]) > OUTAGE_VERIFY_TIMEOUT_SEC:
                        for ep in pending_verification.get("epochs", []):
                            refuel_map[ep] = (False, 0.0)
                        pending_verification = None

            refuel_map[epoch] = (False, 0.0)

    latest_confirmed: Optional[ConfirmedRefuel] = None
    if confirmed_events:
        latest_event = confirmed_events[-1]
        discarded_count = sum(1 for s in steady_samples if s.epoch < latest_event.cutoff_epoch)
        steady_samples = [s for s in steady_samples if s.epoch >= latest_event.cutoff_epoch]
        latest_confirmed = ConfirmedRefuel(
            downtime_minutes=latest_event.downtime_minutes,
            pre_fuel=latest_event.pre_fuel,
            post_fuel=latest_event.post_fuel,
            restart_time=latest_event.restart_time,
            cutoff_epoch=latest_event.cutoff_epoch,
            discarded_samples=discarded_count,
        )

    return RefuelDetectionResult(
        events=confirmed_events,
        latest_confirmed=latest_confirmed,
        refuel_map_by_epoch=refuel_map,
        steady_samples=steady_samples,
        latest_unit_state=latest_unit_st,
        latest_instantaneous_fuel=latest_inst_fuel,
        latest_timestamp=latest_ts,
        detected_mode=detected_mode,
    )


@dataclass
class KalmanSmoothedResult:
    headline_fuel: float
    uncertainty: float
    confidence_interval: Tuple[float, float]
    burn_rate_efph: float
    smoothed_trajectory: List[Tuple[float, float, float]]  # (epoch, state, variance)


def run_kalman_smoother(
    parsed_snapshots: List[ParsedSnapshot],
    steady_samples: List[SteadySample],
    confirmed_events: List[RefuelEventRecord],
    cfg: UnitConfig,
) -> Optional[KalmanSmoothedResult]:
    """
    Runs a 1D Kalman Filter and Rauch-Tung-Striebel (RTS) backward smoother over snapshots.
    Integrates physical energy burnup (k * APRM * dt), down-weights noisy samples via the Delta Method,
    and outputs smooth, monotonic trajectory with formal uncertainty bounds.
    """
    if not parsed_snapshots:
        return None

    meas_map: Dict[float, SteadySample] = {s.epoch: s for s in steady_samples}
    refuel_restart_epochs = {e.cutoff_epoch for e in confirmed_events}

    n_steps = len(parsed_snapshots)
    x_filt = [0.0] * n_steps
    p_filt = [0.0] * n_steps
    x_pred = [0.0] * n_steps
    p_pred = [0.0] * n_steps

    if steady_samples:
        x_init = steady_samples[0].fuel_val
        p_init = 4.0
    else:
        x_init = cfg.expected_refuel_fuel
        p_init = 25.0

    curr_x = x_init
    curr_p = p_init
    burn_rate_k = cfg.default_burn_rate_per_efph

    prev_epoch: Optional[float] = None

    for i, (epoch, ts, data) in enumerate(parsed_snapshots):
        unit_raw = data.get(cfg.name) if isinstance(data, dict) else {}
        unit_st = UnitState.from_dict(unit_raw if isinstance(unit_raw, dict) else {}, cfg.name)

        if prev_epoch is not None and epoch > prev_epoch:
            dt_sec = min(1800.0, epoch - prev_epoch)
            delta_efph = (unit_st.aprm / 100.0) * (dt_sec / 3600.0)
            curr_x = curr_x - burn_rate_k * delta_efph
            q_step = 0.25 * max(0.02, delta_efph) + 0.015
            curr_p = curr_p + q_step

        prev_epoch = epoch
        x_pred[i] = curr_x
        p_pred[i] = curr_p

        if epoch in refuel_restart_epochs:
            curr_x = cfg.expected_refuel_fuel
            curr_p = 3.0

        if epoch in meas_map:
            meas = meas_map[epoch]
            z_k = meas.fuel_val
            r_k = calculate_measurement_variance(unit_st, cfg, z_k)

            k_gain = curr_p / (curr_p + r_k)
            curr_x = curr_x + k_gain * (z_k - curr_x)
            curr_p = (1.0 - k_gain) * curr_p

        x_filt[i] = curr_x
        p_filt[i] = curr_p

    x_smooth = list(x_filt)
    p_smooth = list(p_filt)

    for i in range(n_steps - 2, -1, -1):
        if p_pred[i + 1] > 1e-6:
            c_gain = p_filt[i] / p_pred[i + 1]
            c_gain = min(1.0, max(0.0, c_gain))
            x_smooth[i] = x_filt[i] + c_gain * (x_smooth[i + 1] - x_pred[i + 1])
            p_smooth[i] = p_filt[i] + (c_gain ** 2) * (p_smooth[i + 1] - p_pred[i + 1])

    latest_x = round(min(100.0, max(0.0, x_smooth[-1])), 2)
    latest_var = max(0.04, p_smooth[-1])
    uncertainty = round(math.sqrt(latest_var), 2)
    ci_95 = (round(max(0.0, latest_x - 1.96 * uncertainty), 2), round(min(100.0, latest_x + 1.96 * uncertainty), 2))

    smoothed_traj = [
        (parsed_snapshots[i][0], x_smooth[i], p_smooth[i])
        for i in range(n_steps)
    ]

    return KalmanSmoothedResult(
        headline_fuel=latest_x,
        uncertainty=uncertainty,
        confidence_interval=ci_95,
        burn_rate_efph=burn_rate_k,
        smoothed_trajectory=smoothed_traj,
    )


def approximate_fuel_from_snapshots(
    snapshots: Union[Dict[str, Any], List[ParsedSnapshot]],
    unit_name: str = "Unit1",
    recency_half_life_sec: float = 1800.0,
) -> UnitFuelAssessment:
    """
    Evaluates unit fuel percentage and refueling history over historical snapshots.
    Integrates non-linear core physics, 1D Kalman state-space filter, RTS backward smoother,
    MAD outlier rejection, and explicit posterior uncertainty bounds.
    """
    clean_unit = resolve_unit_name(unit_name)
    cfg = UNIT_CONFIGS[clean_unit]

    parsed_snaps, _ = parse_and_sort_snapshots(snapshots)
    if not parsed_snaps:
        return UnitFuelAssessment(
            status="NO_DATA",
            unit=clean_unit,
            total_snapshots=0,
            steady_samples=0,
            latest_instantaneous=None,
            refuel_detected=False,
            refuel_info=None,
        )

    result = detect_refuel_events(parsed_snaps, cfg)

    if result.detected_mode and result.detected_mode.lower() not in ("classic", "default", ""):
        return UnitFuelAssessment(
            status="UNSUPPORTED_MODE",
            unit=clean_unit,
            total_snapshots=len(parsed_snaps),
            steady_samples=len(result.steady_samples),
            latest_instantaneous=result.latest_instantaneous_fuel,
            latest_timestamp=result.latest_timestamp,
            latest_aprm=result.latest_unit_state.aprm,
            latest_rods=result.latest_unit_state.rods,
            confidence="MODE_NOT_SUPPORTED",
            refuel_detected=bool(result.latest_confirmed),
            refuel_info=result.latest_confirmed,
            mode=result.detected_mode,
        )

    steady_samples = result.steady_samples

    if len(steady_samples) >= 5:
        fuel_vals = [s.fuel_val for s in steady_samples]
        med = statistics.median(fuel_vals)
        mad = statistics.median([abs(x - med) for x in fuel_vals])
        scale = max(1.4826 * mad, 1.0)
        filtered = [s for s in steady_samples if abs(s.fuel_val - med) <= 3.5 * scale]
        if len(filtered) >= 3:
            steady_samples = filtered

    kalman_res = run_kalman_smoother(parsed_snaps, steady_samples, result.events, cfg)

    if not steady_samples:
        is_offline = result.latest_unit_state.aprm < 5.0 or result.latest_unit_state.rods <= 1.0
        kalman_val = kalman_res.headline_fuel if kalman_res else None
        uncert = kalman_res.uncertainty if kalman_res else None
        ci = kalman_res.confidence_interval if kalman_res else None
        return UnitFuelAssessment(
            status="OFFLINE" if is_offline else "TRANSIENT_ACTIVE",
            unit=clean_unit,
            total_snapshots=len(parsed_snaps),
            steady_samples=0,
            latest_instantaneous=result.latest_instantaneous_fuel,
            projected_fuel=kalman_val,
            kalman_fuel=kalman_val,
            uncertainty=uncert,
            confidence_interval=ci,
            latest_timestamp=result.latest_timestamp,
            latest_aprm=result.latest_unit_state.aprm,
            latest_rods=result.latest_unit_state.rods,
            confidence="INSUFFICIENT_STEADY_SAMPLES",
            refuel_detected=bool(result.latest_confirmed),
            refuel_info=result.latest_confirmed,
            mode=result.detected_mode,
        )

    fuel_values = [s.fuel_val for s in steady_samples]
    median_fuel = statistics.median(fuel_values)
    mean_fuel = sum(fuel_values) / len(fuel_values)
    variance = sum((x - mean_fuel) ** 2 for x in fuel_values) / len(fuel_values)
    std_dev = math.sqrt(variance)

    last_sample_epoch = steady_samples[-1].epoch
    weights = [math.exp(-(last_sample_epoch - s.epoch) / recency_half_life_sec) for s in steady_samples]
    sum_w = sum(weights)
    weighted_fuel = sum(w * s.fuel_val for w, s in zip(weights, steady_samples)) / sum_w if sum_w > 0 else mean_fuel

    burn_rate_pct_hr: Optional[float] = None
    residual_std: Optional[float] = None
    projected_fuel: Optional[float] = None
    time_span_sec = steady_samples[-1].epoch - steady_samples[0].epoch

    if len(steady_samples) >= MIN_STEADY_SAMPLES_FOR_TREND and time_span_sec >= MIN_TIME_SPAN_FOR_TREND_SEC:
        t0 = steady_samples[0].epoch
        times = [s.epoch - t0 for s in steady_samples]
        t_mean = sum(times) / len(times)
        num = sum((t - t_mean) * (v - mean_fuel) for t, v in zip(times, fuel_values))
        den = sum((t - t_mean) ** 2 for t in times)
        if den > 0:
            slope_per_sec = num / den
            burn_rate_pct_hr = round(-slope_per_sec * 3600.0, 3)
            intercept = mean_fuel - slope_per_sec * t_mean

            residuals_sq = [
                (v - (slope_per_sec * t + intercept)) ** 2 for t, v in zip(times, fuel_values)
            ]
            dof = max(1, len(steady_samples) - 2)
            residual_std = math.sqrt(sum(residuals_sq) / dof)

            t_latest = steady_samples[-1].epoch - t0
            hat_y = slope_per_sec * t_latest + intercept

            if slope_per_sec <= 0.0001 and abs(hat_y - median_fuel) <= 10.0:
                projected_fuel = round(min(100.0, max(0.0, hat_y)), 2)

    kalman_fuel = kalman_res.headline_fuel if kalman_res else None
    uncertainty = kalman_res.uncertainty if kalman_res else None
    ci_95 = kalman_res.confidence_interval if kalman_res else None
    burn_efph = kalman_res.burn_rate_efph if kalman_res else None

    headline = kalman_fuel if kalman_fuel is not None else (projected_fuel if projected_fuel is not None else round(weighted_fuel, 2))

    if uncertainty is not None and uncertainty < 1.0 and len(steady_samples) >= 10:
        confidence = f"HIGH (uncertainty: +/-{uncertainty:.2f}%)"
    elif uncertainty is not None and uncertainty < 2.5:
        confidence = f"MODERATE (uncertainty: +/-{uncertainty:.2f}%)"
    elif residual_std is not None and residual_std < 1.0:
        confidence = f"HIGH (residual std < 1.0%: {residual_std:.2f}%)"
    elif residual_std is not None and residual_std < 2.5:
        confidence = f"MODERATE (residual std < 2.5%: {residual_std:.2f}%)"
    else:
        confidence = f"LOW (uncertainty: +/-{uncertainty:.2f}%)" if uncertainty is not None else "LOW (high variance or few samples)"

    return UnitFuelAssessment(
        status="STEADY_STATE_OPTIMAL",
        unit=clean_unit,
        total_snapshots=len(parsed_snaps),
        steady_samples=len(steady_samples),
        latest_instantaneous=result.latest_instantaneous_fuel,
        projected_fuel=headline,
        kalman_fuel=kalman_fuel,
        uncertainty=uncertainty,
        confidence_interval=ci_95,
        median_fuel=round(median_fuel, 2),
        mean_fuel=round(mean_fuel, 2),
        weighted_fuel=round(weighted_fuel, 2),
        std_dev=round(std_dev, 2),
        residual_std=round(residual_std, 2) if residual_std is not None else None,
        confidence=confidence,
        burn_rate_pct_hr=burn_rate_pct_hr,
        burn_rate_efph=burn_efph,
        time_span_minutes=round(time_span_sec / 60.0, 1),
        latest_timestamp=result.latest_timestamp,
        latest_aprm=result.latest_unit_state.aprm,
        latest_rods=result.latest_unit_state.rods,
        refuel_detected=bool(result.latest_confirmed),
        refuel_info=result.latest_confirmed,
        mode=result.detected_mode,
    )

def evaluate_server_fuel(
    snapshots: Union[Dict[str, Any], List[ParsedSnapshot]],
    recency_half_life_sec: float = 1800.0,
) -> ServerFuelAssessment:
    parsed_snaps, _ = parse_and_sort_snapshots(snapshots)
    u1_eval = approximate_fuel_from_snapshots(parsed_snaps, "Unit1", recency_half_life_sec=recency_half_life_sec)
    u2_eval = approximate_fuel_from_snapshots(parsed_snaps, "Unit2", recency_half_life_sec=recency_half_life_sec)

    if u1_eval.status == "UNSUPPORTED_MODE" or u2_eval.status == "UNSUPPORTED_MODE":
        server_status = "UNSUPPORTED_MODE"
    else:
        u1_ok = u1_eval.status == "STEADY_STATE_OPTIMAL"
        u2_ok = u2_eval.status == "STEADY_STATE_OPTIMAL"
        if u1_ok and u2_ok:
            server_status = "ONLINE_DUAL"
        elif u1_ok or u2_ok:
            server_status = "ONLINE_SINGLE"
        else:
            server_status = "OFFLINE_OR_TRANSIENT"

    return ServerFuelAssessment(
        server_status=server_status,
        unit1=u1_eval,
        unit2=u2_eval,
    )

def get_refuel_info_by_epoch(
    snapshots: Union[Dict[str, Any], List[ParsedSnapshot]],
    unit_name: str = "Unit2",
) -> Dict[float, Tuple[bool, float]]:
    clean_unit = resolve_unit_name(unit_name)
    cfg = UNIT_CONFIGS[clean_unit]
    parsed_snaps, _ = parse_and_sort_snapshots(snapshots)
    result = detect_refuel_events(parsed_snaps, cfg)
    return result.refuel_map_by_epoch