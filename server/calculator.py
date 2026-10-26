import math
from typing import Any

APRM_TO_RECIRC_TABLE = {
    0: 0, 10: 28, 20: 28, 30: 28, 40: 38, 50: 50,
    60: 70, 70: 85, 80: 94, 90: 97, 100: 100, 110: 100
}


def get_recirc_pump_speed(aprm: float) -> float:
    keys = sorted(APRM_TO_RECIRC_TABLE.keys())
    for k in keys:
        if k >= aprm:
            return float(APRM_TO_RECIRC_TABLE[k])
    return float(APRM_TO_RECIRC_TABLE[keys[-1]])


# =========================================================================
# REGRESSION MODEL EQUATIONS
# Unit 1: Quadratic (y = a*x^2 + b*x + c)
# Unit 2: Cubic (y = a*x^3 + b*x^2 + c*x + d)
# Parameter x = Core RTP / APRM (%)
# =========================================================================

UNIT_1_REGRESSION_MODELS: dict[str, dict[str, Any]] = {
    "FWF": {
        "name": "Feedwater Flow",
        "unit": "kg/s",
        "type": "quadratic",
        "a": 0.005886446886,
        "b": 13.73489499,
        "c": 105.928083,
        "equation": "y = 0.0059x^2 + 13.7349x + 105.9281",
    },
    "TCV": {
        "name": "Turbine Control Valve",
        "unit": "%",
        "type": "quadratic",
        "a": -0.00118974359,
        "b": 0.935565812,
        "c": 5.905726496,
        "equation": "y = -0.0012x^2 + 0.9356x + 5.9057",
    },
    "CRP": {
        "name": "Condenser Recirculation Pump",
        "unit": "%",
        "type": "quadratic",
        "a": -0.00008805860806,
        "b": 0.7933676679,
        "c": 6.818485958,
        "equation": "y = -0.0001x^2 + 0.7934x + 6.8185",
    },
    "DIO Intake": {
        "name": "Deaerator Intake",
        "unit": "%",
        "type": "quadratic",
        "a": 0.006874236874,
        "b": -1.526903541,
        "c": 98.06593407,
        "equation": "y = 0.0069x^2 - 1.5269x + 98.0659",
    },
    "DIO Output": {
        "name": "Deaerator Output",
        "unit": "%",
        "type": "quadratic",
        "a": -0.0017997558,
        "b": -0.03670573871,
        "c": 75.81684982,
        "equation": "y = -0.0018x^2 - 0.0367x + 75.8168",
    },
    "TGL": {
        "name": "Turbine Generator Load",
        "unit": "MWe",
        "type": "quadratic",
        "a": 0.005396825397,
        "b": 12.99801221,
        "c": -135.3540904,
        "equation": "y = 0.0054x^2 + 12.9980x - 135.3541",
    },
}

UNIT_2_REGRESSION_MODELS: dict[str, dict[str, Any]] = {
    "FWF": {
        "name": "Feedwater Flow",
        "unit": "kg/s",
        "type": "cubic",
        "a": 0.0005007109276,
        "b": -0.06112934297,
        "c": 15.90900097,
        "d": 101.8426385,
        "equation": "y = 0.0005x^3 - 0.0611x^2 + 15.9090x + 101.8426",
    },
    "TCV": {
        "name": "Turbine Control Valve",
        "unit": "%",
        "type": "cubic",
        "a": 0.00002797844284,
        "b": -0.005614723082,
        "c": 1.142296755,
        "d": 4.254317165,
        "equation": "y = 0.0000x^3 - 0.0056x^2 + 1.1423x + 4.2543",
    },
    "CRP": {
        "name": "Condenser Recirculation Pump",
        "unit": "%",
        "type": "cubic",
        "a": 0.00001414975347,
        "b": -0.001052287582,
        "c": 0.7989324619,
        "d": 8.249466804,
        "equation": "y = 0.0000x^3 - 0.0011x^2 + 0.7989x + 8.2495",
    },
    "SJAE": {
        "name": "Steam Jet Air Ejector",
        "unit": "%",
        "type": "cubic",
        "a": 0.00009104460498,
        "b": -0.01512108703,
        "c": 1.279841188,
        "d": 8.240626075,
        "equation": "y = 0.0001x^3 - 0.0151x^2 + 1.2798x + 8.2406",
    },
    "DIO Intake": {
        "name": "Deaerator Intake",
        "unit": "%",
        "type": "cubic",
        "a": -0.00008852195849,
        "b": 0.02103887169,
        "c": -2.055509689,
        "d": 99.02339181,
        "equation": "y = -0.0001x^3 + 0.0210x^2 - 2.0555x + 99.0234",
    },
    "DIO Output": {
        "name": "Deaerator Output",
        "unit": "%",
        "type": "cubic",
        "a": 0.00001364522417,
        "b": -0.003620571035,
        "c": -0.01696479761,
        "d": 78.64877881,
        "equation": "y = 0.0000x^3 - 0.0036x^2 - 0.0170x + 78.6488",
    },
    "TGL": {
        "name": "Turbine Generator Load",
        "unit": "MWe",
        "type": "cubic",
        "a": -0.000001031991744,
        "b": 0.005510835913,
        "c": 12.99032508,
        "d": -135.0562436,
        "equation": "y = 0.0000x^3 + 0.0055x^2 + 12.9903x - 135.0562",
    },
    "MSS": {
        "name": "Main Steam Sealing",
        "unit": "%",
        "type": "cubic",
        "a": 0.00001373695677,
        "b": -0.004640522876,
        "c": 1.609876734,
        "d": -41.59191606,
        "equation": "y = 0.0000x^3 - 0.0046x^2 + 1.6099x - 41.5919",
    },
    "OCL": {
        "name": "Oil Cooling",
        "unit": "%",
        "type": "cubic",
        "a": 0.00007570232771,
        "b": -0.01113140695,
        "c": 1.529275312,
        "d": -29.78538012,
        "equation": "y = 0.0001x^3 - 0.0111x^2 + 1.5293x - 29.7854",
    },
    "OCV": {
        "name": "Oil Cooler Valve",
        "unit": "%",
        "type": "cubic",
        "a": -0.00001688034188,
        "b": 0.001993589744,
        "c": 0.8435936286,
        "d": -14.32666667,
        "equation": "y = 0.0000x^3 + 0.0020x^2 + 0.8436x - 14.3267",
    },
    "MCV": {
        "name": "Motor Coolant Valve",
        "unit": "%",
        "type": "cubic",
        "a": -0.0000009712509713,
        "b": -0.000460955711,
        "c": 0.8748815074,
        "d": -3.63,
        "equation": "y = 0.0000x^3 - 0.0005x^2 + 0.8749x - 3.6300",
    },
}


def evaluate_regression_model(model: dict[str, Any], x: float) -> float:
    m_type = model.get("type", "quadratic")
    if m_type == "cubic":
        a = float(model.get("a", 0.0))
        b = float(model.get("b", 0.0))
        c = float(model.get("c", 0.0))
        d = float(model.get("d", 0.0))
        return (a * (x ** 3)) + (b * (x ** 2)) + (c * x) + d
    else:
        a = float(model.get("a", 0.0))
        b = float(model.get("b", 0.0))
        c = float(model.get("c", 0.0))
        return (a * (x ** 2)) + (b * x) + c


def calculate_regression_parameters(unit: int, rtp: float) -> dict[str, Any]:
    selected_unit = 2 if int(unit) == 2 else 1
    models = UNIT_2_REGRESSION_MODELS if selected_unit == 2 else UNIT_1_REGRESSION_MODELS
    results: dict[str, Any] = {}
    for param_key, model_info in models.items():
        val = evaluate_regression_model(model_info, rtp)
        results[param_key] = {
            "name": model_info.get("name", param_key),
            "unit": model_info.get("unit", ""),
            "value": round(val, 4),
            "display": f"{val:.2f}",
            "equation": model_info.get("equation", ""),
            "model_type": model_info.get("type", "quadratic"),
        }
    return results


class UsageCalculator:
    def __init__(self, unit: int):
        self.unit = unit
        if unit == 1:
            self.feedwater_usage = 0.014
            self.condenser_usage = 0.014
            self.condenser_circ_usage = 6.5
            self.recirculation_usage = 0.028
        else:
            self.feedwater_usage = 0.014
            self.condenser_usage = 3.5
            self.condenser_circ_usage = 6.5
            self.recirculation_usage = 0.01
            self.tower_makeup_usage = 0.5

    def calculate_usage(self, feedwater_flow: float, aprm: float, override_speed: float | None = None) -> float:
        feedwater_usage = self.feedwater_usage * feedwater_flow
        condenser_usage = self.condenser_usage if self.unit == 2 else self.condenser_usage * feedwater_flow
        speed = override_speed if override_speed is not None else get_recirc_pump_speed(aprm)
        recirculation_usage = self.recirculation_usage * speed * 10
        const_usage = (self.condenser_circ_usage * 2) + (self.tower_makeup_usage if self.unit == 2 else 0)
        total = feedwater_usage + condenser_usage + const_usage + recirculation_usage
        return round(total, 4)

class ReactorCalculator:
    def __init__(self, unit: int = 1, usage: float = 61.32):
        self.selected_unit = 1 if unit != 2 else 2
        self.usage = usage
        self.usage_calc1 = UsageCalculator(1)
        self.usage_calc2 = UsageCalculator(2)
        self.recirc_override: float | None = None
        self.models = UNIT_2_REGRESSION_MODELS if self.selected_unit == 2 else UNIT_1_REGRESSION_MODELS

    def calc_flow(self, thermal: float) -> float:
        model = self.models.get("FWF")
        if model:
            return max(0.0, evaluate_regression_model(model, thermal))
        return 0.0

    def calc_gen_load(self, thermal: float) -> float:
        model = self.models.get("TGL")
        if model:
            return max(0.0, evaluate_regression_model(model, thermal))
        return 0.0

    def calc_param(self, param_key: str, thermal: float) -> float:
        model = self.models.get(param_key)
        if model:
            return evaluate_regression_model(model, thermal)
        return 0.0

    def _solve_thermal_from_load(self, target_gross: float) -> float:
        if target_gross <= 0:
            return 0.0
        model = self.models.get("TGL")
        if not model:
            return 0.0

        m_type = model.get("type", "quadratic")
        if m_type == "cubic":
            a = float(model.get("a", 0.0))
            b = float(model.get("b", 0.0))
            c = float(model.get("c", 0.0))
            d = float(model.get("d", 0.0))
            x = max(0.0, (target_gross - d) / c if c != 0 else 0.0)
            for _ in range(8):
                fx = (a * (x ** 3)) + (b * (x ** 2)) + (c * x) + d - target_gross
                fpx = (3 * a * (x ** 2)) + (2 * b * x) + c
                if fpx == 0:
                    break
                x = max(0.0, x - (fx / fpx))
            return x
        else:
            a = float(model.get("a", 0.0))
            b = float(model.get("b", 0.0))
            c = float(model.get("c", 0.0))
            inner = (b ** 2) - 4 * a * (c - target_gross)
            if inner < 0:
                return 0.0
            return max(0.0, (-b + math.sqrt(inner)) / (2 * a))

    def calc_thermal(self, demand: float) -> float:
        current_usage = self.usage
        thermal = 0.0
        for _ in range(5):
            target_gross = demand + current_usage
            thermal = self._solve_thermal_from_load(target_gross)
            flow = self.calc_flow(thermal)
            u_calc = self.usage_calc1 if self.selected_unit == 1 else self.usage_calc2
            current_usage = u_calc.calculate_usage(flow, thermal, override_speed=self.recirc_override)

        self.usage = current_usage
        return thermal


def calculate_reactor_metrics(
    unit: int = 1,
    demand: float | None = None,
    thermal: float | None = None,
    recirc_override: float | None = None,
) -> dict[str, Any]:
    """
    Computes reactor operational metrics for Unit 1 or Unit 2.
    Accepts generator demand setpoint (MWe) or APRM/RTP (%).
    """
    selected_unit = 2 if int(unit) == 2 else 1
    calc = ReactorCalculator(unit=selected_unit)

    override_val: float | None = None
    if recirc_override is not None:
        try:
            override_val = max(0.0, min(100.0, float(recirc_override)))
            calc.recirc_override = override_val
        except (ValueError, TypeError):
            override_val = None

    if demand is None and thermal is None:
        raise ValueError("Either 'demand' (MWe) or 'thermal' / 'aprm' / 'rtp' (%) must be provided.")

    if demand is not None:
        demand_val = max(0.0, float(demand))
        solved_thermal = calc.calc_thermal(demand_val)
        flow = calc.calc_flow(solved_thermal)
        gen_load = calc.calc_gen_load(solved_thermal)
        usage = calc.usage
        net_output = max(0.0, gen_load - usage)
    else:
        assert thermal is not None
        thermal_val = max(0.0, min(250.0, float(thermal)))
        solved_thermal = thermal_val
        flow = calc.calc_flow(thermal_val)
        gen_load = calc.calc_gen_load(thermal_val)
        u_calc = calc.usage_calc1 if selected_unit == 1 else calc.usage_calc2
        calc.usage = u_calc.calculate_usage(flow, thermal_val, override_speed=override_val)
        usage = calc.usage
        net_output = max(0.0, gen_load - usage)
        demand_val = net_output

    speed = override_val if override_val is not None else get_recirc_pump_speed(solved_thermal)
    scram_limit = 108.0
    scram_risk = solved_thermal > scram_limit

    regression_params = calculate_regression_parameters(selected_unit, solved_thermal)
    simplified_params = {k: v["value"] for k, v in regression_params.items()}

    return {
        "unit": selected_unit,
        "demand_mwe": round(demand_val, 2),
        "thermal_percent": round(solved_thermal, 3),
        "rtp_percent": round(solved_thermal, 3),
        "aprm_percent": round(solved_thermal, 3),
        "flow_kg_s": round(flow, 2),
        "gen_load_mwe": round(gen_load, 2),
        "station_usage_mwe": round(usage, 2),
        "net_output_mwe": round(net_output, 2),
        "recirc_pump_speed": round(speed, 1),
        "is_recirc_overridden": override_val is not None,
        "scram_risk": scram_risk,
        "scram_limit_percent": scram_limit,
        "parameters": simplified_params,
        "regression_parameters": regression_params,
    }