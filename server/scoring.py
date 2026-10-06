"""
RBWR Server Performance Scoring Engine

Evaluates server operations and stability over a rolling 60-minute window of snapshot history.
Calculates sustainability weights, demand tracking accuracy, refuel status, and operational incident deductions.
Outputs a Top Score between 0.0 and 100.0 with optional detailed breakdown.
"""

import math
from datetime import datetime, timezone

__all__ = [
    "calculate_server_top_score",
    "get_unit_output_mw",
    "extract_snap_pps",
]


def get_unit_output_mw(unit_dict):
    """
    Extracts electrical power generation (MW) from a unit state dictionary.
    Handles Roblox RBWR field aliases:
    - Unit 1 uses 'Output (MW)'
    - Unit 2 uses 'PradDoSieci' (grid electrical power in MW)
    - Fallbacks: 'Output', 'Power', 'megawatts', 'output_mw'
    """
    if not isinstance(unit_dict, dict):
        return 0.0
    for k in ("Output (MW)", "PradDoSieci", "Output", "Power", "megawatts", "output_mw"):
        v = unit_dict.get(k)
        if v is not None:
            try:
                return float(v)
            except (ValueError, TypeError):
                continue
    return 0.0


def extract_snap_pps(snap_tuple):
    """
    Extracts points per second from a snapshot tuple (epoch, ts, state).
    """
    if not snap_tuple:
        return 0.0
    st = snap_tuple[2]
    u1_s = st.get("Unit1", {}) if isinstance(st.get("Unit1"), dict) else {}
    u2_s = st.get("Unit2", {}) if isinstance(st.get("Unit2"), dict) else {}
    m_s = st.get("Misc", {}) if isinstance(st.get("Misc"), dict) else {}
    tot = m_s.get("Total points/second") if m_s.get("Total points/second") is not None else st.get("Total points/second")
    if tot is not None:
        try:
            return float(tot)
        except (ValueError, TypeError):
            pass
    p1 = u1_s.get("PointsPerSecond")
    p2 = u2_s.get("PointsPerSecond")
    rate = 0.0
    if p1 is not None:
        try:
            rate += float(p1)
        except (ValueError, TypeError):
            pass
    if p2 is not None:
        try:
            rate += float(p2)
        except (ValueError, TypeError):
            pass
    return rate


def calculate_server_top_score(snapshots, now_utc=None, return_breakdown=False):
    """
    Evaluates server operations and stability over a rolling 60-minute window of snapshot history.

    Key Scoring Mechanics:
    1. Point Generation Sustainability Weight (PPS):
       - Maximum combined plant generation: Unit 1 (1.2) + Unit 2 (1.7) = 2.9 pts/s.
       - Recency-weighted efficiency weight: W_pps = sum(eta_i * w_i) / sum(w_i), where eta_i = min(1.0, snap_pps / 2.9).
       - Score is scaled down proportionally by W_pps (0 pts/s -> 0 final score).
    2. Recency Weighting & Snapshot Priority:
       - Exponential decay with a 10-minute half-life (600s): base_weight = exp(-delta_sec / 600.0).
       - Current snapshot: 1.50x boost.
       - Previous snapshot: 1.25x boost.
       - Historical snapshots: 1.00x base weight.
    3. Generation & Demand Tracking:
       - Normal generation within +-40 MW deadband receives full 1.0 ratio credit.
       - Deviations beyond +-40 MW incur proportional ratio deductions.
       - 60s Demand Grace Period awards 75.0 pts after demand setpoint changes.
       - Unexcused downtime (active demand with APRM < 5.0% or Output <= 0 MW) drops unit score to 5.0 pts.
       - Grid LOOP outage (Offsite Power == False or Demand == -2) awards 50.0 pts.
    4. Unit 2 Refueling Outage Detection:
       - Qualifying event (-1, -2, -3, -4 or offsite power loss) with cold offline core.
       - Optimal 50m refuel maintains ~70-72.5 pts.
       - 5-hour refuel decays to 20.0 pts; stalled outages (>5h) decay to 5.0 pts.
       - Disqualified if Unit 2 had prior unexcused demand downtime.
    5. Synergy & Incidents:
       - Dual unit active: 1.25x multiplier (+25%).
       - Single unit active: 1.00x multiplier.
       - Both offline: 0.70x multiplier.
       - In-snapshot SCRAM or Turbine Trip: 60% snapshot score reduction.
       - Cumulative incident penalty: -5.0 pts per SCRAM/Trip in window (capped at -25.0 pts).
    """
    if not snapshots or not isinstance(snapshots, dict):
        if return_breakdown:
            return 0.0, {
                "top_score": 0.0,
                "raw_score": 0.0,
                "evaluated_snapshots_count": 0,
                "total_snapshots_count": 0,
                "time_window_minutes": 0.0,
                "error": "No snapshots available"
            }
        return 0.0

    valid_ts_keys = sorted([k for k in snapshots.keys() if not k.startswith('_')])
    if not valid_ts_keys:
        if return_breakdown:
            return 0.0, {
                "top_score": 0.0,
                "raw_score": 0.0,
                "evaluated_snapshots_count": 0,
                "total_snapshots_count": 0,
                "time_window_minutes": 0.0,
                "error": "No valid snapshot timestamps"
            }
        return 0.0

    parsed_snaps = []
    for ts in valid_ts_keys:
        st = snapshots[ts]
        if not isinstance(st, dict):
            continue
        try:
            clean_ts = ts.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_ts)
            epoch = dt.timestamp()
            parsed_snaps.append((epoch, ts, st))
        except Exception:
            continue

    if not parsed_snaps:
        if return_breakdown:
            return 0.0, {
                "top_score": 0.0,
                "raw_score": 0.0,
                "evaluated_snapshots_count": 0,
                "total_snapshots_count": 0,
                "time_window_minutes": 0.0,
                "error": "Could not parse snapshot timestamps"
            }
        return 0.0

    parsed_snaps.sort(key=lambda x: x[0])
    latest_epoch = parsed_snaps[-1][0]

    u2_refuel_start_epoch = None
    u2_had_qualifying_event = False
    u2_had_prior_downtime = False
    u2_is_currently_refueling = False
    prev_d2_pre = None
    last_d2_change_pre = None

    refuel_info_by_epoch = {}

    for epoch, ts, state in parsed_snaps:
        u1_st = state.get("Unit1", {}) if isinstance(state.get("Unit1"), dict) else {}
        u2_st = state.get("Unit2", {}) if isinstance(state.get("Unit2"), dict) else {}

        aprm2_val = float(u2_st.get("APRM") or 0.0)
        out2_val = get_unit_output_mw(u2_st)
        d2_val = u2_st.get("DemandU2") if u2_st.get("DemandU2") is not None else u2_st.get("Demand")
        offsite2_val = u2_st.get("Offsite Power")
        rod2_val = u2_st.get("Avg. Rod")
        press2_val = u2_st.get("Pressure")

        if prev_d2_pre is not None and d2_val != prev_d2_pre:
            last_d2_change_pre = epoch
        prev_d2_pre = d2_val
        in_grace_2_pre = (last_d2_change_pre is not None and (epoch - last_d2_change_pre) <= 60.0)

        is_loop_2_pre = (offsite2_val is False) or (d2_val == -2)
        has_demand_2_pre = (d2_val is not None and isinstance(d2_val, (int, float)) and d2_val > 0)

        is_u2_generating = (aprm2_val >= 5.0 and out2_val > 0)
        if is_u2_generating:
            u2_had_qualifying_event = False
            u2_had_prior_downtime = False
            u2_is_currently_refueling = False
            u2_refuel_start_epoch = None

        if not u2_is_currently_refueling:
            if has_demand_2_pre and not is_loop_2_pre and not in_grace_2_pre and (aprm2_val < 5.0 or out2_val <= 0.0):
                u2_had_prior_downtime = True
                u2_had_qualifying_event = False
                u2_refuel_start_epoch = None

        is_event = (d2_val in (-1, -2, -3, -4)) or (offsite2_val is False)
        if is_event and not u2_had_prior_downtime:
            u2_had_qualifying_event = True
            if u2_refuel_start_epoch is None:
                u2_refuel_start_epoch = epoch

        rod_inserted = True
        if rod2_val is not None:
            try:
                rod_inserted = (float(rod2_val) <= 1.0)
            except (ValueError, TypeError):
                pass

        depressurized = True
        if press2_val is not None:
            try:
                depressurized = (float(press2_val) <= 15.0)
            except (ValueError, TypeError):
                pass

        is_cold_offline = (aprm2_val < 5.0 and out2_val <= 0.0 and rod_inserted and depressurized)

        if is_cold_offline and u2_had_qualifying_event and not u2_had_prior_downtime:
            if u2_refuel_start_epoch is None:
                u2_refuel_start_epoch = epoch
            elapsed_min = max(0.0, (epoch - u2_refuel_start_epoch) / 60.0)
            refuel_info_by_epoch[epoch] = (True, elapsed_min)
            u2_is_currently_refueling = True
        else:
            if not is_cold_offline:
                u2_refuel_start_epoch = None
                u2_had_qualifying_event = False
            u2_is_currently_refueling = False
            refuel_info_by_epoch[epoch] = (False, 0.0)

    eval_snaps = [s for s in parsed_snaps if (latest_epoch - s[0]) <= 3600]
    if not eval_snaps:
        eval_snaps = parsed_snaps[-10:]

    prev_d1 = None
    last_d1_change = None
    prev_d2 = None
    last_d2_change = None

    weighted_score_sum = 0.0
    total_weight = 0.0
    scram_trip_count = 0

    u1_score_sum = 0.0
    u2_score_sum = 0.0
    u1_active_count = 0
    u2_active_count = 0
    u1_downtime_count = 0
    u2_downtime_count = 0
    u1_grace_count = 0
    u2_grace_count = 0
    u1_loop_count = 0
    u2_loop_count = 0
    u2_refuel_count = 0
    u2_refuel_score_sum = 0.0
    u2_refuel_min_latest = None
    u2_refuel_pts_lost_latest = None
    u1_scrams = 0
    u1_trips = 0
    u2_scrams = 0
    u2_trips = 0
    u1_scram_reasons = []
    u1_trip_reasons = []
    u2_scram_reasons = []
    u2_trip_reasons = []
    u1_turb_sum = 0.0
    u1_turb_count = 0
    u2_turb_sum = 0.0
    u2_turb_count = 0
    u1_pps_sum = 0.0
    u1_pps_count = 0
    u1_out_sum = 0.0
    u1_out_count = 0
    u2_pps_sum = 0.0
    u2_pps_count = 0
    u2_out_sum = 0.0
    u2_out_count = 0
    u1_tolerance_count = 0
    u1_extreme_count = 0
    u2_tolerance_count = 0
    u2_extreme_count = 0
    dual_active_count = 0
    single_active_count = 0
    inactive_count = 0
    synergy_mult_sum = 0.0
    weighted_pps_eff_sum = 0.0
    weighted_pps_sum = 0.0

    snapshot_breakdowns = []
    n_snaps = len(eval_snaps)

    for idx, (epoch, ts, state) in enumerate(eval_snaps):
        delta_sec = max(0.0, latest_epoch - epoch)
        base_weight = math.exp(-delta_sec / 600.0)

        is_current_snap = (idx == n_snaps - 1)
        is_prev_snap = (idx == n_snaps - 2)
        if is_current_snap:
            weight = base_weight * 1.50
        elif is_prev_snap:
            weight = base_weight * 1.25
        else:
            weight = base_weight

        misc_st = state.get("Misc", {}) if isinstance(state.get("Misc"), dict) else {}
        server_pps_raw = misc_st.get("Total points/second") if misc_st.get("Total points/second") is not None else state.get("Total points/second")
        server_pps = None
        if server_pps_raw is not None:
            try:
                server_pps = float(server_pps_raw)
            except (ValueError, TypeError):
                server_pps = None

        u1 = state.get("Unit1", {}) if isinstance(state.get("Unit1"), dict) else {}
        d1 = u1.get("DemandU1") if u1.get("DemandU1") is not None else u1.get("Demand")
        offsite1 = u1.get("Offsite Power")
        aprm1 = float(u1.get("APRM") or 0.0)
        out1 = get_unit_output_mw(u1)
        pps1 = u1.get("PointsPerSecond")
        turb1 = u1.get("TurbineHealth")
        scram1 = u1.get("SCRAMreason")
        trip1 = u1.get("TRIPreason")

        if prev_d1 is not None and d1 != prev_d1:
            last_d1_change = epoch
        prev_d1 = d1
        in_grace_1 = (last_d1_change is not None and (epoch - last_d1_change) <= 60.0)

        is_loop_1 = (offsite1 is False) or (d1 == -2)
        has_demand_1 = (d1 is not None and isinstance(d1, (int, float)) and d1 > 0)

        pps1_val = None
        if pps1 is not None:
            try:
                pps1_val = float(pps1)
            except (ValueError, TypeError):
                pps1_val = None
        elif server_pps is not None:
            u1_act = (aprm1 >= 5.0 and out1 > 0)
            u2_st_check = state.get("Unit2", {}) if isinstance(state.get("Unit2"), dict) else {}
            u2_act = (float(u2_st_check.get("APRM") or 0) >= 5.0 and get_unit_output_mw(u2_st_check) > 0)
            if u1_act and u2_act:
                pps1_val = server_pps * (1.2 / 2.9)
            elif u1_act:
                pps1_val = server_pps

        u1_is_downtime = False
        u1_pts = None
        u1_expected_pts = None
        u1_ratio = None
        u1_turb_factor = 1.0
        u1_diff = None
        u1_in_tolerance = None
        u1_desc = ""

        if has_demand_1 and not is_loop_1:
            if in_grace_1:
                u1_score = 75.0
                u1_grace_count += 1
                u1_desc = "60s Demand Grace Period"
            elif aprm1 < 5.0 or out1 <= 0.0:
                u1_score = 5.0
                u1_downtime_count += 1
                u1_is_downtime = True
                u1_desc = "Downtime with Active Demand (APRM < 5% or Out <= 0)"
            else:
                target_d1 = max(50.0, float(d1))  # pyright: ignore[reportArgumentType]
                u1_diff = out1 - target_d1
                abs_diff1 = abs(u1_diff)

                if abs_diff1 <= 40.0:
                    mw_ratio = 1.0
                    u1_in_tolerance = True
                    u1_tolerance_count += 1
                else:
                    extreme_excess = abs_diff1 - 40.0
                    mw_ratio = max(0.0, 1.0 - (extreme_excess / target_d1))
                    u1_in_tolerance = False
                    u1_extreme_count += 1

                if pps1_val is not None:
                    pps_ratio = max(0.0, pps1_val) / 1.2
                    u1_pts = pps1_val
                    u1_expected_pts = 1.2
                    blended_ratio = 0.50 * mw_ratio + 0.50 * min(1.5, pps_ratio)
                    u1_ratio = min(1.35, max(mw_ratio, blended_ratio, pps_ratio))
                else:
                    u1_pts = max(0.0, out1)
                    u1_expected_pts = target_d1
                    u1_ratio = min(1.3, mw_ratio)

                u1_score = 80.0 * u1_ratio
                if abs_diff1 <= 40.0:
                    diff_tag = f"{u1_diff:+.0f} MW (within ±40 MW band)"
                else:
                    diff_tag = f"{u1_diff:+.0f} MW (extreme: {abs_diff1 - 40.0:.0f} MW off band)"
                u1_desc = f"Normal Generation ({out1:.0f}/{target_d1:.0f} MW, {diff_tag}, Target Ratio: {u1_ratio:.2f})"

                if turb1 is not None:
                    try:
                        th = float(turb1)
                        u1_turb_factor = 0.85 + 0.15 * min(1.0, max(0.0, th / 100.0))
                        u1_score *= u1_turb_factor
                        u1_turb_sum += th
                        u1_turb_count += 1
                    except (ValueError, TypeError):
                        pass

                has_scram = scram1 and str(scram1).strip().lower() not in ("none", "", "null", "false", "0")
                has_trip = trip1 and str(trip1).strip().lower() not in ("none", "", "null", "false", "0")
                if has_scram or has_trip:
                    scram_trip_count += 1
                    u1_score *= 0.4
                    if has_scram:
                        u1_scrams += 1
                        u1_scram_reasons.append(str(scram1).strip())
                        u1_desc += f" [SCRAM: {scram1}]"
                    if has_trip:
                        u1_trips += 1
                        u1_trip_reasons.append(str(trip1).strip())
                        u1_desc += f" [TRIP: {trip1}]"
        elif is_loop_1:
            u1_score = 50.0
            u1_loop_count += 1
            u1_desc = "Grid LOOP Outage (Offsite Power Off / Demand -2, partial deduction)"
        else:
            u1_score = 60.0 if aprm1 >= 5.0 else 50.0
            u1_desc = "Hot Standby" if aprm1 >= 5.0 else "Zero Demand / Offline"

        if aprm1 >= 5.0 and out1 > 0:
            u1_active_count += 1
        if out1 > 0:
            u1_out_sum += out1
            u1_out_count += 1
        if pps1_val is not None:
            u1_pps_sum += pps1_val
            u1_pps_count += 1

        u2 = state.get("Unit2", {}) if isinstance(state.get("Unit2"), dict) else {}
        d2 = u2.get("DemandU2") if u2.get("DemandU2") is not None else u2.get("Demand")
        offsite2 = u2.get("Offsite Power")
        aprm2 = float(u2.get("APRM") or 0.0)
        out2 = get_unit_output_mw(u2)
        pps2 = u2.get("PointsPerSecond")
        turb2 = u2.get("TurbineHealth")
        scram2 = u2.get("SCRAMreason")
        trip2 = u2.get("TRIPreason")

        if prev_d2 is not None and d2 != prev_d2:
            last_d2_change = epoch
        prev_d2 = d2
        in_grace_2 = (last_d2_change is not None and (epoch - last_d2_change) <= 60.0)

        is_loop_2 = (offsite2 is False) or (d2 == -2)
        has_demand_2 = (d2 is not None and isinstance(d2, (int, float)) and d2 > 0)
        is_refuel_2, refuel_min_2 = refuel_info_by_epoch.get(epoch, (False, 0.0))

        pps2_val = None
        if pps2 is not None:
            try:
                pps2_val = float(pps2)
            except (ValueError, TypeError):
                pps2_val = None
        elif server_pps is not None:
            u1_act = (aprm1 >= 5.0 and out1 > 0)
            u2_act = (aprm2 >= 5.0 and out2 > 0)
            if u1_act and u2_act:
                pps2_val = server_pps * (1.7 / 2.9)
            elif u2_act:
                pps2_val = server_pps

        u2_is_downtime = False
        u2_pts = None
        u2_expected_pts = None
        u2_ratio = None
        u2_turb_factor = 1.0
        u2_diff = None
        u2_in_tolerance = None
        u2_desc = ""
        u2_pred_lost = None

        if is_loop_2:
            u2_score = 50.0
            u2_loop_count += 1
            u2_desc = "Grid LOOP Outage (Offsite Power Off / Demand -2, partial deduction)"
        elif is_refuel_2:
            if refuel_min_2 <= 50.0:
                u2_score = 75.0 - 5.0 * (refuel_min_2 / 50.0)
                u2_pred_lost = int(round(1000.0 * (refuel_min_2 / 50.0)))
            elif refuel_min_2 <= 300.0:
                u2_score = 70.0 - 50.0 * ((refuel_min_2 - 50.0) / 250.0)
                u2_pred_lost = int(round(1000.0 + 29000.0 * ((refuel_min_2 - 50.0) / 250.0)))
            else:
                u2_score = max(5.0, 20.0 - 15.0 * ((refuel_min_2 - 300.0) / 60.0))
                u2_pred_lost = int(round(30000.0 + (refuel_min_2 - 300.0) * 100.0))

            u2_refuel_count += 1
            u2_refuel_score_sum += u2_score
            u2_refuel_min_latest = refuel_min_2
            u2_refuel_pts_lost_latest = u2_pred_lost
            u2_desc = f"Active Refueling Outage ({int(refuel_min_2)}m elapsed, -{u2_pred_lost:,} pts pred loss, {u2_score:.1f} pts)"
        elif has_demand_2:
            if in_grace_2:
                u2_score = 75.0
                u2_grace_count += 1
                u2_desc = "60s Demand Grace Period"
            elif aprm2 < 5.0 or out2 <= 0.0:
                u2_score = 5.0
                u2_downtime_count += 1
                u2_is_downtime = True
                u2_desc = "Downtime with Active Demand (APRM < 5% or Out <= 0)"
            else:
                target_d2 = max(50.0, float(d2))  # pyright: ignore[reportArgumentType]
                u2_diff = out2 - target_d2
                abs_diff2 = abs(u2_diff)

                if abs_diff2 <= 40.0:
                    mw_ratio2 = 1.0
                    u2_in_tolerance = True
                    u2_tolerance_count += 1
                else:
                    extreme_excess = abs_diff2 - 40.0
                    mw_ratio2 = max(0.0, 1.0 - (extreme_excess / target_d2))
                    u2_in_tolerance = False
                    u2_extreme_count += 1

                if pps2_val is not None:
                    pps_ratio2 = max(0.0, pps2_val) / 1.7
                    u2_pts = pps2_val
                    u2_expected_pts = 1.7
                    blended_ratio2 = 0.50 * mw_ratio2 + 0.50 * min(1.5, pps_ratio2)
                    u2_ratio = min(1.35, max(mw_ratio2, blended_ratio2, pps_ratio2))
                else:
                    u2_pts = max(0.0, out2)
                    u2_expected_pts = target_d2
                    u2_ratio = min(1.3, mw_ratio2)

                u2_score = 80.0 * u2_ratio
                if abs_diff2 <= 40.0:
                    diff_tag = f"{u2_diff:+.0f} MW (within ±40 MW band)"
                else:
                    diff_tag = f"{u2_diff:+.0f} MW (extreme: {abs_diff2 - 40.0:.0f} MW off band)"
                u2_desc = f"Normal Generation ({out2:.0f}/{target_d2:.0f} MW, {diff_tag}, Target Ratio: {u2_ratio:.2f})"

                if turb2 is not None:
                    try:
                        th = float(turb2)
                        u2_turb_factor = 0.85 + 0.15 * min(1.0, max(0.0, th / 100.0))
                        u2_score *= u2_turb_factor
                        u2_turb_sum += th
                        u2_turb_count += 1
                    except (ValueError, TypeError):
                        pass

                has_scram = scram2 and str(scram2).strip().lower() not in ("none", "", "null", "false", "0")
                has_trip = trip2 and str(trip2).strip().lower() not in ("none", "", "null", "false", "0")
                if has_scram or has_trip:
                    scram_trip_count += 1
                    u2_score *= 0.4
                    if has_scram:
                        u2_scrams += 1
                        u2_scram_reasons.append(str(scram2).strip())
                        u2_desc += f" [SCRAM: {scram2}]"
                    if has_trip:
                        u2_trips += 1
                        u2_trip_reasons.append(str(trip2).strip())
                        u2_desc += f" [TRIP: {trip2}]"
        else:
            u2_score = 60.0 if aprm2 >= 5.0 else 50.0
            u2_desc = "Hot Standby" if aprm2 >= 5.0 else "Zero Demand / Offline"

        if aprm2 >= 5.0 and out2 > 0:
            u2_active_count += 1
        if out2 > 0:
            u2_out_sum += out2
            u2_out_count += 1
        if pps2_val is not None:
            u2_pps_sum += pps2_val
            u2_pps_count += 1

        u1_active = (aprm1 >= 5.0 and out1 > 0)
        u2_active = (aprm2 >= 5.0 and out2 > 0)
        if u1_active and u2_active:
            synergy_mult = 1.25
            dual_active_count += 1
        elif u1_active or u2_active:
            synergy_mult = 1.0
            single_active_count += 1
        else:
            synergy_mult = 0.7
            inactive_count += 1

        synergy_mult_sum += synergy_mult

        snap_score = ((u1_score + u2_score) / 2.0) * synergy_mult
        snap_score = min(100.0, max(0.0, snap_score))

        snap_total_pps = extract_snap_pps((epoch, ts, state))
        if snap_total_pps <= 0.0:
            calc_pps = 0.0
            if pps1_val is not None and pps1_val > 0:
                calc_pps += pps1_val
            if pps2_val is not None and pps2_val > 0:
                calc_pps += pps2_val
            if calc_pps > 0:
                snap_total_pps = calc_pps

        snap_pps_eff = min(1.0, max(0.0, snap_total_pps / 2.9))

        weighted_score_sum += snap_score * weight
        weighted_pps_eff_sum += snap_pps_eff * weight
        weighted_pps_sum += snap_total_pps * weight
        total_weight += weight

        u1_score_sum += u1_score * weight
        u2_score_sum += u2_score * weight

        if return_breakdown:
            snapshot_breakdowns.append({
                "timestamp": ts,
                "epoch": epoch,
                "age_seconds": round(delta_sec, 1),
                "weight": round(weight, 4),
                "is_current_snapshot": is_current_snap,
                "is_previous_snapshot": is_prev_snap,
                "snap_score": round(snap_score, 1),
                "weighted_contribution": round(snap_score * weight, 2),
                "total_pps": round(snap_total_pps, 2),
                "pps_efficiency": round(snap_pps_eff, 4),
                "synergy_mult": synergy_mult,
                "u1": {
                    "demand": d1,
                    "offsite_power": offsite1,
                    "aprm": round(aprm1, 1),
                    "output_mw": round(out1, 1),
                    "demand_delta": round(u1_diff, 1) if u1_diff is not None else None,
                    "in_demand_tolerance": u1_in_tolerance,
                    "pps": round(float(pps1_val), 1) if pps1_val is not None else None,
                    "expected_pts": round(u1_expected_pts, 1) if u1_expected_pts is not None else None,
                    "ratio": round(u1_ratio, 2) if u1_ratio is not None else None,
                    "turb_health": round(float(turb1), 1) if turb1 is not None else None,
                    "turb_factor": round(u1_turb_factor, 2),
                    "is_loop": is_loop_1,
                    "in_grace": in_grace_1,
                    "is_downtime": u1_is_downtime,
                    "scram_reason": str(scram1) if scram1 else None,
                    "trip_reason": str(trip1) if trip1 else None,
                    "score": round(u1_score, 1),
                    "desc": u1_desc
                },
                "u2": {
                    "demand": d2,
                    "offsite_power": offsite2,
                    "aprm": round(aprm2, 1),
                    "output_mw": round(out2, 1),
                    "demand_delta": round(u2_diff, 1) if u2_diff is not None else None,
                    "in_demand_tolerance": u2_in_tolerance,
                    "pps": round(float(pps2_val), 1) if pps2_val is not None else None,
                    "expected_pts": round(u2_expected_pts, 1) if u2_expected_pts is not None else None,
                    "ratio": round(u2_ratio, 2) if u2_ratio is not None else None,
                    "turb_health": round(float(turb2), 1) if turb2 is not None else None,
                    "turb_factor": round(u2_turb_factor, 2),
                    "is_loop": is_loop_2,
                    "in_grace": in_grace_2,
                    "is_refuel": is_refuel_2,
                    "refuel_minutes": round(refuel_min_2, 1) if is_refuel_2 else None,
                    "pred_points_lost": u2_pred_lost,
                    "is_downtime": u2_is_downtime,
                    "scram_reason": str(scram2) if scram2 else None,
                    "trip_reason": str(trip2) if trip2 else None,
                    "score": round(u2_score, 1),
                    "desc": u2_desc
                }
            })

    curr_snap = eval_snaps[-1] if eval_snaps else None
    prev_snap = eval_snaps[-2] if len(eval_snaps) > 1 else None

    curr_pps = extract_snap_pps(curr_snap)
    prev_pps = extract_snap_pps(prev_snap) if prev_snap else curr_pps
    recent_pps_avg = (curr_pps + prev_pps) / 2.0

    raw_score = (weighted_score_sum / total_weight) if total_weight > 0 else 0.0
    weighted_pps_eff = (weighted_pps_eff_sum / total_weight) if total_weight > 0 else 0.0
    weighted_avg_pps = (weighted_pps_sum / total_weight) if total_weight > 0 else 0.0
    point_generation_weight = min(1.0, max(0.0, weighted_pps_eff))

    score_before_penalties = raw_score * point_generation_weight
    points_score_loss = max(0.0, raw_score - score_before_penalties)
    deduction = min(25.0, scram_trip_count * 5.0) if scram_trip_count > 0 else 0.0
    final_score = round(min(100.0, max(0.0, score_before_penalties - deduction)), 1)

    if not return_breakdown:
        return final_score

    snapshot_breakdowns.sort(key=lambda s: s["epoch"], reverse=True)

    window_mins = round((eval_snaps[-1][0] - eval_snaps[0][0]) / 60.0, 1) if len(eval_snaps) > 1 else 0.0

    breakdown = {
        "top_score": final_score,
        "raw_score": round(raw_score, 2),
        "score_before_penalties": round(score_before_penalties, 2),
        "evaluated_snapshots_count": len(eval_snaps),
        "total_snapshots_count": len(parsed_snaps),
        "time_window_minutes": window_mins,
        "half_life_seconds": 600,
        "point_generation": {
            "point_generation_weight": round(point_generation_weight, 4),
            "efficiency_percent": round(point_generation_weight * 100.0, 1),
            "points_score_multiplier": round(point_generation_weight, 4),
            "points_score_loss": round(points_score_loss, 1),
            "weighted_avg_pps": round(weighted_avg_pps, 2),
            "current_points_rate": round(curr_pps, 2),
            "previous_points_rate": round(prev_pps, 2),
            "avg_recent_points_rate": round(recent_pps_avg, 2),
            "max_u1_pps": 1.2,
            "max_u2_pps": 1.7,
            "max_total_pps": 2.9,
            "half_life_seconds": 600,
            "current_weight_multiplier": 1.50,
            "previous_weight_multiplier": 1.25,
            "is_actively_generating": curr_pps > 0 and prev_pps > 0,
            "is_sustaining_max": point_generation_weight >= 0.999,
        },
        "recent_point_generation": {
            "current_points_rate": round(curr_pps, 2),
            "previous_points_rate": round(prev_pps, 2),
            "avg_recent_points_rate": round(recent_pps_avg, 2),
            "recent_generation_bonus": 0.0,
            "point_generation_weight": round(point_generation_weight, 4),
            "efficiency_percent": round(point_generation_weight * 100.0, 1),
            "points_score_multiplier": round(point_generation_weight, 4),
            "points_score_loss": round(points_score_loss, 1),
            "weighted_avg_pps": round(weighted_avg_pps, 2),
            "half_life_seconds": 600,
            "current_weight_multiplier": 1.50,
            "previous_weight_multiplier": 1.25,
            "max_u1_pps": 1.2,
            "max_u2_pps": 1.7,
            "max_total_pps": 2.9,
            "is_actively_generating": curr_pps > 0 and prev_pps > 0,
            "is_sustaining_max": point_generation_weight >= 0.999,
        },
        "point_generation_weight": round(point_generation_weight, 4),
        "points_score_loss": round(points_score_loss, 1),
        "weights_sum": round(total_weight, 3),
        "synergy": {
            "dual_active_count": dual_active_count,
            "single_active_count": single_active_count,
            "inactive_count": inactive_count,
            "avg_synergy_multiplier": round(synergy_mult_sum / len(eval_snaps), 2) if eval_snaps else 1.0,
        },
        "penalties": {
            "scram_trip_count": scram_trip_count,
            "total_penalty_deduction": round(deduction, 1),
            "u1_scrams": u1_scrams,
            "u1_trips": u1_trips,
            "u2_scrams": u2_scrams,
            "u2_trips": u2_trips,
        },
        "unit1_summary": {
            "avg_score": round(u1_score_sum / total_weight, 1) if total_weight > 0 else 0.0,
            "active_snapshots": u1_active_count,
            "active_pct": round((u1_active_count / len(eval_snaps)) * 100, 1) if eval_snaps else 0.0,
            "avg_output_mw": round(u1_out_sum / u1_out_count, 1) if u1_out_count > 0 else 0.0,
            "latest_output_mw": round(get_unit_output_mw(eval_snaps[-1][2].get("Unit1", {})), 1) if eval_snaps else 0.0,
            "demand_tolerance_count": u1_tolerance_count,
            "demand_extreme_count": u1_extreme_count,
            "downtime_demand_count": u1_downtime_count,
            "grace_count": u1_grace_count,
            "loop_count": u1_loop_count,
            "avg_turbine_health": round(u1_turb_sum / u1_turb_count, 1) if u1_turb_count > 0 else None,
            "avg_points_per_sec": round(u1_pps_sum / u1_pps_count, 1) if u1_pps_count > 0 else 0.0,
            "scram_reasons": list(set(u1_scram_reasons)),
            "trip_reasons": list(set(u1_trip_reasons))
        },
        "unit2_summary": {
            "avg_score": round(u2_score_sum / total_weight, 1) if total_weight > 0 else 0.0,
            "active_snapshots": u2_active_count,
            "active_pct": round((u2_active_count / len(eval_snaps)) * 100, 1) if eval_snaps else 0.0,
            "avg_output_mw": round(u2_out_sum / u2_out_count, 1) if u2_out_count > 0 else 0.0,
            "latest_output_mw": round(get_unit_output_mw(eval_snaps[-1][2].get("Unit2", {})), 1) if eval_snaps else 0.0,
            "demand_tolerance_count": u2_tolerance_count,
            "demand_extreme_count": u2_extreme_count,
            "downtime_demand_count": u2_downtime_count,
            "grace_count": u2_grace_count,
            "loop_count": u2_loop_count,
            "refuel_count": u2_refuel_count,
            "refuel_minutes_latest": round(u2_refuel_min_latest, 1) if u2_refuel_min_latest is not None else None,
            "avg_refuel_score": round(u2_refuel_score_sum / u2_refuel_count, 1) if u2_refuel_count > 0 else None,
            "pred_points_lost_latest": u2_refuel_pts_lost_latest,
            "avg_turbine_health": round(u2_turb_sum / u2_turb_count, 1) if u2_turb_count > 0 else None,
            "avg_points_per_sec": round(u2_pps_sum / u2_pps_count, 1) if u2_pps_count > 0 else 0.0,
            "scram_reasons": list(set(u2_scram_reasons)),
            "trip_reasons": list(set(u2_trip_reasons))
        },
        "snapshots": snapshot_breakdowns
    }

    return final_score, breakdown
