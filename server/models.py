from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional, Tuple


class DictLikeModel:
    """Base mixin providing backwards-compatible dict-like lookup and serialization."""

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            val = getattr(self, item)
            if hasattr(val, "to_dict"):
                return val.to_dict()
            return val
        raise KeyError(f"{self.__class__.__name__} has no attribute '{item}'")

    def get(self, key: str, default: Any = None) -> Any:
        if hasattr(self, key):
            val = getattr(self, key)
            if val is not None and hasattr(val, "to_dict"):
                return val.to_dict()
            return val if val is not None else default
        return default

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key) and getattr(self, key) is not None

    def to_dict(self) -> Dict[str, Any]:
        """Converts model to a clean, JSON-serializable dictionary."""
        result: Dict[str, Any] = {}
        for k, v in asdict(self).items():  # pyright: ignore[reportArgumentType]
            if isinstance(v, dict) and hasattr(v, "to_dict"):
                result[k] = v.to_dict()  # pyright: ignore[reportAttributeAccessIssue]
            else:
                result[k] = v
        return result


@dataclass(frozen=True)
class UnitConfig:
    """Configuration parameters and physical coefficients for a reactor unit."""
    name: str
    calibration: float
    void_coeff: float
    downtime_min: float
    downtime_max: Optional[float]
    post_fuel_min: float
    rod_alpha: float = 0.45
    recirc_coeff: float = 0.28
    pressure_coeff: float = 0.35
    natural_flow_fraction: float = 0.25
    nominal_pressure_kpa: float = 7000.0
    expected_refuel_fuel: float = 97.0
    default_burn_rate_per_efph: float = 2.40


@dataclass
class PendingRefuel(DictLikeModel):
    """
    Represents an ongoing candidate refueling outage tracking cycle.
    Created when control rods are inserted; closed when control rods are pulled.
    """
    start_epoch: float
    pre_fuel: Optional[float] = None
    end_epoch: Optional[float] = None
    downtime_sec: Optional[float] = None
    restart_ts: Optional[str] = None

    @property
    def downtime_minutes(self) -> Optional[float]:
        """Returns downtime duration in minutes if closed."""
        if self.downtime_sec is not None:
            return round(self.downtime_sec / 60.0, 1)
        return None

    def mark_restart(self, end_epoch: float, restart_ts: str) -> None:
        """Records control rods withdrawal, halting downtime accumulation."""
        self.end_epoch = end_epoch
        self.downtime_sec = max(0.0, end_epoch - self.start_epoch)
        self.restart_ts = restart_ts


@dataclass
class ConfirmedRefuel(DictLikeModel):
    """
    Represents a verified refueling outage event that satisfies duration,
    pre-depletion, and post-refuel reactivity thresholds.
    """
    downtime_minutes: float
    pre_fuel: Optional[float]
    post_fuel: float
    restart_time: Optional[str]
    cutoff_epoch: float
    discarded_samples: int = 0


@dataclass
class SteadySample(DictLikeModel):
    """A single snapshot sample meeting steady-state core operational criteria."""
    epoch: float
    timestamp: str
    fuel_val: float
    aprm: float
    rods: float


@dataclass
class UnitFuelAssessment(DictLikeModel):
    """Assessment of fuel percentage and refuel state for a single reactor unit."""
    status: str
    unit: str
    total_snapshots: int = 0
    steady_samples: int = 0
    latest_instantaneous: Optional[float] = None
    projected_fuel: Optional[float] = None
    kalman_fuel: Optional[float] = None
    uncertainty: Optional[float] = None
    confidence_interval: Optional[Tuple[float, float]] = None
    median_fuel: Optional[float] = None
    mean_fuel: Optional[float] = None
    weighted_fuel: Optional[float] = None
    std_dev: Optional[float] = None
    residual_std: Optional[float] = None
    confidence: str = ""
    burn_rate_pct_hr: Optional[float] = None
    burn_rate_efph: Optional[float] = None
    time_span_minutes: Optional[float] = None
    latest_timestamp: Optional[str] = None
    latest_aprm: Optional[float] = None
    latest_rods: Optional[float] = None
    refuel_detected: bool = False
    refuel_info: Optional[ConfirmedRefuel] = None
    mode: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        if self.refuel_info is not None and hasattr(self.refuel_info, "to_dict"):
            d["refuel_info"] = self.refuel_info.to_dict()
        return d


@dataclass
class ServerFuelAssessment(DictLikeModel):
    """Combined fuel assessment across Unit 1 and Unit 2 for a game server."""
    server_status: str
    unit1: UnitFuelAssessment
    unit2: UnitFuelAssessment
    job_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "server_status": self.server_status,
            "unit1": self.unit1.to_dict(),
            "unit2": self.unit2.to_dict(),
        }
        if self.job_id:
            d["job_id"] = self.job_id
        return d


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None or isinstance(val, (dict, list, tuple, set, bool)):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


@dataclass
class UnitState(DictLikeModel):
    """
    Parsed operational metrics for a single reactor unit at one snapshot timestamp.
    Extracts standardized fields across Roblox RBWR alias variants.
    """
    aprm: float = 0.0
    rods: float = 0.0
    recirc1: float = 0.0
    recirc2: float = 0.0
    recirc: float = 0.0
    temp: float = 0.0
    xenon: float = 0.0
    iodine: float = 0.0
    level: float = 0.0
    output_mw: float = 0.0
    pressure: float = 0.0
    offsite_power: bool = True
    demand: Optional[float] = None
    points_per_second: float = 0.0
    mode: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], unit_name: str = "Unit1") -> "UnitState":
        """Builds a UnitState from a raw snapshot dictionary handling key variations."""
        if not isinstance(data, dict):
            return cls()

        aprm = _safe_float(data.get("APRM"), 0.0)
        rods = _safe_float(data.get("Avg. Rod"), 0.0)
        recirc1 = _safe_float(data.get("Recirc1"), 0.0)
        recirc2 = _safe_float(data.get("Recirc2"), 0.0)
        recirc = (recirc1 + recirc2) / 2.0 if (recirc1 or recirc2) else _safe_float(data.get("Recirc"), 0.0)
        temp_val = data.get("Reactor Temp") if data.get("Reactor Temp") is not None else data.get("CasingTemperature")
        temp = _safe_float(temp_val, 0.0)
        xenon = _safe_float(data.get("Xenon"), 0.0)
        iodine = _safe_float(data.get("Iodine"), 0.0)
        level = _safe_float(data.get("ReactorLevel"), 0.0)

        output_mw = 0.0
        for k in ("Output (MW)", "PradDoSieci", "Output", "Power", "megawatts", "output_mw"):
            if k in data and data[k] is not None:
                try:
                    output_mw = float(data[k])
                    break
                except (ValueError, TypeError):
                    pass

        pressure = _safe_float(data.get("Pressure"), 0.0)
        offsite = bool(data.get("Offsite Power", True))

        demand_key = "DemandU2" if "2" in str(unit_name) else "DemandU1"
        demand_val = data.get(demand_key)
        demand = float(demand_val) if demand_val is not None and not isinstance(demand_val, (dict, list, bool)) else None

        pps = _safe_float(data.get("PointsPerSecond"), 0.0)

        mode_val = data.get("Mode") or data.get("ReactorMode") or data.get("GameMode")
        mode = str(mode_val).strip() if mode_val is not None else None

        return cls(
            aprm=aprm,
            rods=rods,
            recirc1=recirc1,
            recirc2=recirc2,
            recirc=recirc,
            temp=temp,
            xenon=xenon,
            iodine=iodine,
            level=level,
            output_mw=output_mw,
            pressure=pressure,
            offsite_power=offsite,
            demand=demand,
            points_per_second=pps,
            mode=mode,
            raw=data,
        )

    @property
    def is_rods_inserted(self) -> bool:
        """True if control rods are inserted at or below cutoff."""
        return (self.rods <= 1.0) or (self.aprm < 1.0 and self.rods <= 2.0)

    @property
    def is_operating_envelope(self) -> bool:
        """True if unit meets basic steady-state envelope requirements."""
        return (self.aprm >= 20.0 and self.rods >= 10.0 and self.temp >= 180.0 and self.level >= -0.5)

@dataclass
class PointGenerationMetrics(DictLikeModel):
    """Breakdown of points-per-second generation efficiency."""
    point_generation_weight: float = 1.0
    efficiency_percent: float = 100.0
    points_score_multiplier: float = 1.0
    points_score_loss: float = 0.0
    weighted_avg_pps: float = 0.0
    current_points_rate: float = 0.0
    previous_points_rate: float = 0.0
    avg_recent_points_rate: float = 0.0
    max_u1_pps: float = 1.2
    max_u2_pps: float = 1.7
    max_total_pps: float = 2.9
    half_life_seconds: int = 600
    is_actively_generating: bool = True
    is_sustaining_max: bool = True


@dataclass
class ScoreBreakdown(DictLikeModel):
    """Complete Top Score evaluation breakdown for modal inspection and API."""
    top_score: float
    raw_score: float
    score_before_penalties: float
    evaluated_snapshots_count: int
    total_snapshots_count: int
    time_window_minutes: float
    point_generation: PointGenerationMetrics
    point_generation_weight: float
    points_score_loss: float
    weights_sum: float
    scram_trip_penalties: float = 0.0
    scram_trip_count: int = 0
    synergy_multiplier: float = 1.0
    job_id: Optional[str] = None
    short_id: Optional[str] = None


__all__ = [
    "DictLikeModel",
    "UnitConfig",
    "PendingRefuel",
    "ConfirmedRefuel",
    "SteadySample",
    "UnitFuelAssessment",
    "ServerFuelAssessment",
    "UnitState",
    "PointGenerationMetrics",
    "ScoreBreakdown",
]