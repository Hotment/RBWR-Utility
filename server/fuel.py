"""
RBWR Core Fuel Level Estimation & Refueling Detection Engine

Provides multi-snapshot rolling evaluation, and automated refueling outage detection for 
Unit 1 and Unit 2 in Roblox RBWR.

Key physical mechanisms:
- Control rod reactivity worth (higher withdrawal at same APRM indicates lower fuel level)
- Core recirculation flow void-sweeping factor
- Steam void fraction negative reactivity feedback
- Xenon-135 neutron poison accumulation
- Water moderator density curve from reactor temperature
- Core water level coverage penalty
- Refueling outage detection & pre-refuel historical snapshot pruning
"""

import datetime
import math
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from server.models import (
        PendingRefuel,
        ConfirmedRefuel,
        SteadySample,
        UnitFuelAssessment,
        ServerFuelAssessment,
        UnitState,
    )
except ImportError:
    from models import (
        PendingRefuel,
        ConfirmedRefuel,
        SteadySample,
        UnitFuelAssessment,
        ServerFuelAssessment,
        UnitState,
    )

__all__ = [
    "CALIBRATION_CONST_U1",
    "CALIBRATION_CONST_U2",
    "REFUEL_DOWNTIME_MIN_U1",
    "REFUEL_DOWNTIME_MAX_U1",
    "REFUEL_DOWNTIME_MIN_U2",
    "REFUEL_PRE_FUEL_MAX",
    "REFUEL_POST_FUEL_MIN_U1",
    "REFUEL_POST_FUEL_MIN_U2",
    "calculate_u1_fuel_level",
    "calculate_u2_fuel_level",
    "calculate_unit_fuel_level",
    "approximate_fuel_from_snapshots",
    "evaluate_server_fuel",
    "get_refuel_info_by_epoch",
    "parse_iso_timestamp",
]

# Calibrated core reactivity constants
CALIBRATION_CONST_U1 = 34.9080
CALIBRATION_CONST_U2 = 33.5630

# Refueling detection physical thresholds
REFUEL_DOWNTIME_MIN_U1 = 300.0    # At least 5 minutes offline
REFUEL_DOWNTIME_MAX_U1 = 1260.0   # At most 20 minutes (with 1-minute buffer)
REFUEL_DOWNTIME_MIN_U2 = 3000.0   # At least 50 minutes offline
REFUEL_PRE_FUEL_MAX = 67.0        # Pre-outage fuel level below 67.0% (in-game 65% with 2% margin) # haha 67!!
REFUEL_POST_FUEL_MIN_U1 = 88.0    # Post-refuel fresh core threshold for Unit 1
REFUEL_POST_FUEL_MIN_U2 = 90.0    # Post-refuel fresh core threshold for Unit 2


def parse_iso_timestamp(ts: str) -> float:
    if not ts:
        return 0.0
    try:
        clean_ts = str(ts).replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(clean_ts).timestamp()
    except Exception:
        return 0.0


def calculate_u1_fuel_level(u1_data: Union[Dict[str, Any], UnitState]) -> float:
    if isinstance(u1_data, UnitState):
        aprm = u1_data.aprm
        rods = u1_data.rods
        recirc = u1_data.recirc
        temp = u1_data.temp
        xenon = u1_data.xenon
        level = u1_data.level
    elif isinstance(u1_data, dict):
        aprm = float(u1_data.get("APRM", 0.0) or 0.0)
        rods = float(u1_data.get("Avg. Rod", 0.0) or 0.0)
        recirc1 = float(u1_data.get("Recirc1", 0.0) or 0.0)
        recirc2 = float(u1_data.get("Recirc2", 0.0) or 0.0)
        recirc = (recirc1 + recirc2) / 2.0
        temp = float(u1_data.get("Reactor Temp", 0.0) or 0.0)
        xenon = float(u1_data.get("Xenon", 0.0) or 0.0)
        level = float(u1_data.get("ReactorLevel", 0.0) or 0.0)
    else:
        return 0.0

    if rods <= 1.0 or aprm < 1.0:
        return 0.0

    f_rod = 0.2 + 0.8 * (rods / 100.0)
    f_recirc = 1.0 + 0.25 * (recirc / 100.0)
    f_void = 1.0 - 0.38 * (aprm / 100.0)
    f_xe = 1.0 - (xenon / 4.5)

    rho = (
        -4.468e-6 * (temp ** 3)
        - 5.603e-4 * (temp ** 2)
        - 0.4291 * temp
        + 1010.04
    ) / 1000.0

    f_level = 1.0 if level >= -0.5 else max(0.1, 1.0 + (level + 0.5) * 0.25)

    denom = f_rod * f_recirc * f_void * f_xe * rho * f_level
    if denom <= 0.0:
        return 0.0

    u1_fuel_pct = CALIBRATION_CONST_U1 / denom
    return round(u1_fuel_pct, 2)


def calculate_u2_fuel_level(u2_data: Union[Dict[str, Any], UnitState]) -> float:
    if isinstance(u2_data, UnitState):
        aprm = u2_data.aprm
        rods = u2_data.rods
        recirc = u2_data.recirc
        temp = u2_data.temp
        xenon = u2_data.xenon
        level = u2_data.level
    elif isinstance(u2_data, dict):
        aprm = float(u2_data.get("APRM", 0.0) or 0.0)
        rods = float(u2_data.get("Avg. Rod", 0.0) or 0.0)
        recirc1 = float(u2_data.get("Recirc1", 0.0) or 0.0)
        recirc2 = float(u2_data.get("Recirc2", 0.0) or 0.0)
        recirc = (recirc1 + recirc2) / 2.0
        temp = float(u2_data.get("Reactor Temp", 0.0) or 0.0)
        xenon = float(u2_data.get("Xenon", 0.0) or 0.0)
        level = float(u2_data.get("ReactorLevel", 0.0) or 0.0)
    else:
        return 0.0

    if rods <= 1.0 or aprm < 1.0:
        return 0.0

    f_rod = 0.2 + 0.8 * (rods / 100.0)
    f_recirc = 1.0 + 0.25 * (recirc / 100.0)
    f_void = 1.0 - 0.42 * (aprm / 100.0)
    f_xe = 1.0 - (xenon / 4.5)

    rho = (
        -4.468e-6 * (temp ** 3)
        - 5.603e-4 * (temp ** 2)
        - 0.4291 * temp
        + 1010.04
    ) / 1000.0

    f_level = 1.0 if level >= -0.5 else max(0.1, 1.0 + (level + 0.5) * 0.25)

    denom = f_rod * f_recirc * f_void * f_xe * rho * f_level
    if denom <= 0.0:
        return 0.0

    u2_fuel_pct = CALIBRATION_CONST_U2 / denom
    return round(u2_fuel_pct, 2)


def calculate_unit_fuel_level(unit_name: str, unit_data: Union[Dict[str, Any], UnitState]) -> float:
    clean_name = str(unit_name).lower().replace(" ", "").replace("_", "")
    if "u2" in clean_name or "unit2" in clean_name:
        return calculate_u2_fuel_level(unit_data)
    return calculate_u1_fuel_level(unit_data)


def approximate_fuel_from_snapshots(
    snapshots: Dict[str, Any],
    unit_name: str = "Unit1",
    recency_half_life_sec: float = 1800.0
) -> UnitFuelAssessment:
    clean_unit = "Unit2" if "2" in unit_name else "Unit1"
    calc_func = calculate_u1_fuel_level if clean_unit == "Unit1" else calculate_u2_fuel_level
    sorted_ts = sorted([k for k in snapshots.keys() if not str(k).startswith("_")])

    if not sorted_ts:
        return UnitFuelAssessment(
            status="NO_DATA",
            unit=clean_unit,
            total_snapshots=0,
            steady_samples=0,
            latest_instantaneous=0.0,
            refuel_detected=False,
            refuel_info=None,
        )

    latest_ts = sorted_ts[-1]
    latest_st = (snapshots[latest_ts].get(clean_unit) or {}) if isinstance(snapshots[latest_ts], dict) else {}
    latest_instantaneous_fuel = calc_func(latest_st)

    min_refuel_downtime_sec = REFUEL_DOWNTIME_MIN_U1 if clean_unit == "Unit1" else REFUEL_DOWNTIME_MIN_U2
    max_refuel_downtime_sec = REFUEL_DOWNTIME_MAX_U1 if clean_unit == "Unit1" else None
    min_post_refuel_fuel = REFUEL_POST_FUEL_MIN_U1 if clean_unit == "Unit1" else REFUEL_POST_FUEL_MIN_U2

    steady_samples: List[SteadySample] = []
    last_steady_fuel: Optional[float] = None
    last_steady_epoch: Optional[float] = None
    in_outage: bool = False
    pending_refuel: Optional[PendingRefuel] = None
    confirmed_refuel: Optional[ConfirmedRefuel] = None
    refuel_cutoff_epoch: Optional[float] = None

    prev_epoch: Optional[float] = None
    prev_aprm: Optional[float] = None
    prev_rods: Optional[float] = None

    for ts in sorted_ts:
        snap_data = snapshots[ts]
        if not isinstance(snap_data, dict):
            continue
        unit_raw = snap_data.get(clean_unit)
        if not isinstance(unit_raw, dict):
            continue

        unit_st = UnitState.from_dict(unit_raw, clean_unit)
        epoch = parse_iso_timestamp(ts)

        rods_inserted = unit_st.is_rods_inserted

        if rods_inserted:
            if not in_outage:
                in_outage = True
                outage_start = last_steady_epoch if last_steady_epoch is not None else epoch
                pending_refuel = PendingRefuel(
                    start_epoch=outage_start,
                    pre_fuel=last_steady_fuel,
                )
        else:
            if in_outage:
                in_outage = False
                if pending_refuel is not None:
                    pending_refuel.mark_restart(epoch, ts)
            elif (
                pending_refuel is None
                and last_steady_epoch is not None
                and (epoch - last_steady_epoch) >= min_refuel_downtime_sec
            ):
                pending_refuel = PendingRefuel(
                    start_epoch=last_steady_epoch,
                    end_epoch=epoch,
                    downtime_sec=epoch - last_steady_epoch,
                    pre_fuel=last_steady_fuel,
                    restart_ts=ts,
                )

        if not unit_st.is_operating_envelope:
            prev_epoch, prev_aprm, prev_rods = epoch, unit_st.aprm, unit_st.rods
            continue

        is_steady = True
        if prev_epoch is not None and 0.0 < (epoch - prev_epoch) <= 180.0:
            dt_step = epoch - prev_epoch
            d_aprm_dt = abs(unit_st.aprm - (prev_aprm if prev_aprm is not None else unit_st.aprm)) / dt_step
            d_rod_dt = abs(unit_st.rods - (prev_rods if prev_rods is not None else unit_st.rods)) / dt_step
            if d_aprm_dt > 0.08 or d_rod_dt > 0.04:
                is_steady = False

        prev_epoch, prev_aprm, prev_rods = epoch, unit_st.aprm, unit_st.rods
        if not is_steady:
            continue

        fuel_val = calc_func(unit_st)
        if 10.0 <= fuel_val <= 125.0:
            if pending_refuel is not None and pending_refuel.downtime_sec is not None:
                dt_outage = pending_refuel.downtime_sec
                pre_f = pending_refuel.pre_fuel
                dt_valid = (dt_outage >= min_refuel_downtime_sec) and (
                    max_refuel_downtime_sec is None or dt_outage <= max_refuel_downtime_sec
                )
                pre_fuel_valid = (pre_f is not None and pre_f < REFUEL_PRE_FUEL_MAX)
                post_fuel_valid = (fuel_val >= min_post_refuel_fuel)

                if dt_valid and pre_fuel_valid:
                    if post_fuel_valid:
                        confirmed_refuel = ConfirmedRefuel(
                            downtime_minutes=round(dt_outage / 60.0, 1),
                            pre_fuel=round(pre_f, 2) if pre_f is not None else None,
                            post_fuel=round(fuel_val, 2),
                            restart_time=pending_refuel.restart_ts,
                            cutoff_epoch=pending_refuel.end_epoch or epoch,
                        )
                        refuel_cutoff_epoch = pending_refuel.end_epoch
                        pending_refuel = None
                    elif pending_refuel.end_epoch is not None and (epoch - pending_refuel.end_epoch) > 7200.0:
                        pending_refuel = None
                else:
                    pending_refuel = None

            steady_samples.append(
                SteadySample(epoch=epoch, timestamp=ts, fuel_val=fuel_val, aprm=unit_st.aprm, rods=unit_st.rods)
            )
            last_steady_fuel = fuel_val
            last_steady_epoch = epoch

    if refuel_cutoff_epoch is not None:
        discarded_count = sum(1 for s in steady_samples if s.epoch < refuel_cutoff_epoch)
        steady_samples = [s for s in steady_samples if s.epoch >= refuel_cutoff_epoch]
        if confirmed_refuel:
            confirmed_refuel.discarded_samples = discarded_count

    if not steady_samples:
        is_offline = latest_st.get("APRM", 0.0) < 5.0 or latest_st.get("Avg. Rod", 0.0) <= 1.0
        return UnitFuelAssessment(
            status="OFFLINE" if is_offline else "TRANSIENT_ACTIVE",
            unit=clean_unit,
            total_snapshots=len(sorted_ts),
            steady_samples=0,
            latest_instantaneous=latest_instantaneous_fuel,
            latest_timestamp=latest_ts,
            latest_aprm=latest_st.get("APRM", 0.0),
            latest_rods=latest_st.get("Avg. Rod", 0.0),
            confidence="INSUFFICIENT_STEADY_SAMPLES",
            refuel_detected=bool(confirmed_refuel),
            refuel_info=confirmed_refuel,
        )

    fuel_values = [s.fuel_val for s in steady_samples]
    fuel_sorted = sorted(fuel_values)
    median_fuel = fuel_sorted[len(fuel_sorted) // 2]
    mean_fuel = sum(fuel_values) / len(fuel_values)
    variance = sum((x - mean_fuel) ** 2 for x in fuel_values) / len(fuel_values)
    std_dev = math.sqrt(variance)

    last_sample_epoch = steady_samples[-1].epoch
    weights = [math.exp(-(last_sample_epoch - s.epoch) / recency_half_life_sec) for s in steady_samples]
    sum_w = sum(weights)
    weighted_fuel = sum(w * s.fuel_val for w, s in zip(weights, steady_samples)) / sum_w if sum_w > 0 else mean_fuel

    burn_rate_pct_hr: Optional[float] = None
    time_span_sec = steady_samples[-1].epoch - steady_samples[0].epoch
    if len(steady_samples) >= 6 and time_span_sec >= 900.0:
        times = [s.epoch - steady_samples[0].epoch for s in steady_samples]
        t_mean = sum(times) / len(times)
        num = sum((t - t_mean) * (v - mean_fuel) for t, v in zip(times, fuel_values))
        den = sum((t - t_mean) ** 2 for t in times)
        if den > 0:
            slope_per_sec = num / den
            burn_rate_pct_hr = round(-slope_per_sec * 3600.0, 3)

    if std_dev < 1.0 and len(steady_samples) >= 15:
        confidence = "HIGH (std < 1.0%)"
    elif std_dev < 2.5 and len(steady_samples) >= 5:
        confidence = "MODERATE (std < 2.5%)"
    else:
        confidence = "LOW (high variance or few samples)"

    return UnitFuelAssessment(
        status="STEADY_STATE_OPTIMAL",
        unit=clean_unit,
        total_snapshots=len(sorted_ts),
        steady_samples=len(steady_samples),
        latest_instantaneous=latest_instantaneous_fuel,
        median_fuel=round(median_fuel, 2),
        mean_fuel=round(mean_fuel, 2),
        weighted_fuel=round(weighted_fuel, 2),
        std_dev=round(std_dev, 2),
        confidence=confidence,
        burn_rate_pct_hr=burn_rate_pct_hr,
        time_span_minutes=round(time_span_sec / 60.0, 1),
        latest_timestamp=latest_ts,
        latest_aprm=latest_st.get("APRM", 0.0),
        latest_rods=latest_st.get("Avg. Rod", 0.0),
        refuel_detected=bool(confirmed_refuel),
        refuel_info=confirmed_refuel,
    )

def evaluate_server_fuel(
    snapshots: Dict[str, Any],
    recency_half_life_sec: float = 1800.0
) -> ServerFuelAssessment:
    u1_eval = approximate_fuel_from_snapshots(snapshots, "Unit1", recency_half_life_sec=recency_half_life_sec)
    u2_eval = approximate_fuel_from_snapshots(snapshots, "Unit2", recency_half_life_sec=recency_half_life_sec)

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
    snapshots: Union[Dict[str, Any], List[Tuple[float, str, Dict[str, Any]]]],
    unit_name: str = "Unit2"
) -> Dict[float, Tuple[bool, float]]:
    clean_unit = "Unit2" if "2" in unit_name else "Unit1"
    calc_func = calculate_u2_fuel_level if clean_unit == "Unit2" else calculate_u1_fuel_level
    min_downtime = REFUEL_DOWNTIME_MIN_U2 if clean_unit == "Unit2" else REFUEL_DOWNTIME_MIN_U1
    max_downtime = None if clean_unit == "Unit2" else REFUEL_DOWNTIME_MAX_U1
    min_post_fuel = REFUEL_POST_FUEL_MIN_U2 if clean_unit == "Unit2" else REFUEL_POST_FUEL_MIN_U1

    if isinstance(snapshots, dict):
        parsed = []
        for ts, st in snapshots.items():
            if str(ts).startswith("_"):
                continue
            parsed.append((parse_iso_timestamp(ts), str(ts), st if isinstance(st, dict) else {}))
        parsed.sort(key=lambda x: x[0])
    else:
        parsed = sorted(snapshots, key=lambda x: x[0])

    refuel_info: Dict[float, Tuple[bool, float]] = {}
    last_steady_fuel: Optional[float] = None
    last_steady_epoch: Optional[float] = None
    in_outage = False
    outage_start: Optional[float] = None
    pre_fuel: Optional[float] = None
    is_refuel_candidate = False
    current_outage_epochs: List[float] = []
    pending_verification: Optional[Dict[str, Any]] = None

    for epoch, ts, state in parsed:
        unit_raw = state.get(clean_unit) if isinstance(state, dict) else {}
        unit_st = UnitState.from_dict(unit_raw if isinstance(unit_raw, dict) else {}, clean_unit)
        fuel_val = calc_func(unit_st)

        if unit_st.is_operating_envelope and fuel_val > 0.0:
            last_steady_fuel = fuel_val
            last_steady_epoch = epoch

        rods_inserted = unit_st.is_rods_inserted

        if rods_inserted:
            if not in_outage:
                in_outage = True
                outage_start = last_steady_epoch if last_steady_epoch is not None else epoch
                pre_fuel = last_steady_fuel
                current_outage_epochs = [epoch]
                is_refuel_candidate = (pre_fuel is not None and pre_fuel < REFUEL_PRE_FUEL_MAX)
            else:
                current_outage_epochs.append(epoch)

            if is_refuel_candidate:
                elapsed_min = max(0.0, (epoch - (outage_start or epoch)) / 60.0)
                refuel_info[epoch] = (True, elapsed_min)
            else:
                refuel_info[epoch] = (False, 0.0)
        else:
            if in_outage:
                in_outage = False
                restart_epoch = epoch
                dt_sec = restart_epoch - (outage_start or epoch)
                dt_valid = (dt_sec >= min_downtime) and (max_downtime is None or dt_sec <= max_downtime)

                if dt_valid and is_refuel_candidate:
                    pending_verification = {
                        "epochs": list(current_outage_epochs),
                        "start": outage_start,
                        "restart": restart_epoch,
                        "pre_fuel": pre_fuel,
                    }
                else:
                    for ep in current_outage_epochs:
                        refuel_info[ep] = (False, 0.0)
                    pending_verification = None
                current_outage_epochs = []

            if pending_verification is not None:
                if fuel_val >= min_post_fuel:
                    pending_verification = None
                elif (epoch - pending_verification["restart"]) > 7200.0:
                    for ep in pending_verification["epochs"]:
                        refuel_info[ep] = (False, 0.0)
                    pending_verification = None

            refuel_info[epoch] = (False, 0.0)

    return refuel_info