from sqlalchemy.orm import joinedload

from app.models.reading import Reading
from app.models.threshold_rule import ThresholdRule
from app.services.assessment_service import RULE_FIELDS
from app.services.measurement_format_service import format_sensor_value


SUPPORTING_CHANNELS = {
    "Turbidity": ("turbidity_ntu", "tss", "particle_level", "clarity"),
    "TDS": ("tds_ppm", "conductivity", "ionic_content", "salinity"),
    "pH": ("ph_value", "acidity", "alkalinity", "ph_stability"),
    "Temperature": ("temperature_c", "ambient_temperature", "change_rate", "thermal_anomaly"),
}
CHANNEL_LABELS = {
    "turbidity_ntu": "Turbidity",
    "tss": "TSS estimate",
    "particle_level": "Particle level",
    "clarity": "Clarity",
    "tds_ppm": "TDS",
    "conductivity": "Conductivity estimate",
    "ionic_content": "Ionic content score",
    "salinity": "Salinity estimate",
    "ph_value": "pH",
    "acidity": "Acidity score",
    "alkalinity": "Alkalinity score",
    "ph_stability": "pH stability",
    "temperature_c": "Water temperature",
    "ambient_temperature": "Ambient temperature",
    "change_rate": "Change rate",
    "thermal_anomaly": "Thermal anomaly",
}
STATUS_RANK = {"Good": 0, "Within range": 0, "No anomaly flag": 0, "Fair": 1, "Warning": 1, "Moderate": 1, "Poor": 2, "High": 2, "Critical": 3}
STATUS_CLASS = {
    "Good": "good",
    "Within range": "good",
    "No anomaly flag": "good",
    "Fair": "fair",
    "Warning": "warning",
    "Moderate": "moderate",
    "Poor": "poor",
    "High": "high",
    "Critical": "critical",
}


def get_decision_support_data():
    """Build an explainable summary from the latest saved measurement."""
    reading = (
        Reading.query
        .options(joinedload(Reading.river))
        .order_by(Reading.recorded_at.desc(), Reading.id.desc())
        .first()
    )
    if reading is None:
        return {"latest_reading": None, "triggered_rules": [], "measurements": [], "recommendation": None}

    triggered_rules = []
    evaluations_by_group = {group_name: [] for group_name in SUPPORTING_CHANNELS}
    field_groups = {
        field: group_name
        for group_name, fields in SUPPORTING_CHANNELS.items()
        for field in fields
    }
    thermal_rule_triggered = False
    for rule in ThresholdRule.query.filter_by(is_active=True).order_by(ThresholdRule.id.asc()).all():
        parameter = str(rule.parameter).strip().lower().replace(" ", "_")
        field = RULE_FIELDS.get(parameter)
        value = getattr(reading, field, None) if field else None
        if value is None or field not in field_groups:
            continue

        below_minimum = rule.min_value is not None and value < rule.min_value
        above_maximum = rule.max_value is not None and value > rule.max_value
        breached = below_minimum or above_maximum
        limits = []
        if rule.min_value is not None:
            limits.append(f"minimum {format_sensor_value(field, rule.min_value)}")
        if rule.max_value is not None:
            limits.append(f"maximum {format_sensor_value(field, rule.max_value)}")
        condition = (
            "Below configured minimum" if below_minimum
            else "Above configured maximum" if above_maximum
            else "Within configured limits"
        )
        evaluation = {
            "name": rule.rule_name,
            "field": CHANNEL_LABELS.get(field, field.replace("_", " ").title()),
            "value": format_sensor_value(field, value),
            "condition": condition + (": " + ", ".join(limits) if limits else ""),
            "status": rule.status if breached else "Within range",
            "status_class": STATUS_CLASS.get(rule.status, "unknown") if breached else "good",
            "breached": breached,
            "description": rule.description,
        }
        evaluations_by_group[field_groups[field]].append(evaluation)

        thermal_rule_triggered = thermal_rule_triggered or field == "thermal_anomaly"
        if breached:
            triggered_rules.append({
                "name": rule.rule_name,
                "field": evaluation["field"],
                "value": evaluation["value"],
                "condition": evaluation["condition"],
                "severity": rule.status,
                "description": rule.description,
            })

    if reading.turbidity_ntu is not None:
        band = "Good" if reading.turbidity_ntu <= 5 else "Fair" if reading.turbidity_ntu <= 10 else "Poor"
        condition = (
            "At or below 5 NTU"
            if band == "Good"
            else "Above 5 through 10 NTU"
            if band == "Fair"
            else "Above 10 NTU"
        )
        evaluation = {
            "name": "Base turbidity assessment",
            "field": "Turbidity",
            "value": format_sensor_value("turbidity_ntu", reading.turbidity_ntu),
            "condition": condition,
            "status": band,
            "status_class": STATUS_CLASS[band],
            "breached": band in {"Fair", "Poor"},
            "description": "Application assessment band; not a regulatory water-safety certification.",
        }
        evaluations_by_group["Turbidity"].append(evaluation)
        if band in {"Fair", "Poor"}:
            triggered_rules.append({
                "name": evaluation["name"],
                "field": evaluation["field"],
                "value": evaluation["value"],
                "condition": condition,
                "severity": band,
                "description": evaluation["description"],
            })

    if reading.thermal_anomaly is not None:
        anomaly_detected = reading.thermal_anomaly > 0
        evaluation = {
            "name": "ESP32 thermal check",
            "field": "Thermal anomaly",
            "value": format_sensor_value("thermal_anomaly", reading.thermal_anomaly),
            "condition": (
                "Firmware flagged this sample"
                if anomaly_detected
                else "No firmware anomaly flag reported"
            ),
            "status": "Poor" if anomaly_detected else "No anomaly flag",
            "status_class": "poor" if anomaly_detected else "good",
            "breached": anomaly_detected,
            "description": "Based on the ESP32 temperature limits and valid ambient-temperature comparison.",
        }
        evaluations_by_group["Temperature"].append(evaluation)

    if reading.thermal_anomaly and reading.thermal_anomaly > 0 and not thermal_rule_triggered:
        triggered_rules.append({
            "name": "ESP32 thermal anomaly",
            "field": "Thermal anomaly",
            "value": format_sensor_value("thermal_anomaly", reading.thermal_anomaly),
            "condition": "Firmware flagged this sample",
            "severity": "Poor",
            "description": "The flag follows the ESP32 sketch logic and requires sensor verification.",
        })

    analysis_groups = []
    for group_name, fields in SUPPORTING_CHANNELS.items():
        evaluations = evaluations_by_group[group_name]
        has_measurements = any(getattr(reading, field) is not None for field in fields)
        breached = [item for item in evaluations if item["breached"]]
        if breached:
            strongest = max(breached, key=lambda item: STATUS_RANK.get(item["status"], 0))
            group_status = strongest["status"]
            group_summary = f"{len(breached)} rule condition(s) require review."
        elif evaluations:
            group_status = evaluations[-1]["status"]
            group_summary = "Evaluated against the available application or firmware rule."
        elif has_measurements:
            if group_name == "Temperature":
                group_status = "No thermal flag"
                group_summary = "Temperature values are available, but no ESP32 thermal flag or configured temperature threshold was recorded for this sample."
            else:
                group_status = "No threshold configured"
                group_summary = "Measurements are shown for context; no configured rule evaluates these channels."
        else:
            group_status = "No measurement"
            if group_name == "pH":
                group_summary = "No pH value is available in this reading, so configured pH thresholds cannot be evaluated."
            else:
                group_summary = "No values are available in this sensor group for this reading."

        if not evaluations:
            empty_note = (
                "No pH measurement or configured pH threshold is available."
                if group_name == "pH"
                else "No ESP32 thermal flag or configured temperature threshold is available."
                if group_name == "Temperature"
                else f"No active {group_name} threshold is configured."
            )
        else:
            empty_note = None

        analysis_groups.append({
            "name": group_name,
            "status": group_status,
            "status_class": STATUS_CLASS.get(group_status, "unknown"),
            "summary": group_summary,
            "evaluations": evaluations,
            "empty_note": empty_note,
        })

    status = reading.quality_status or "Unknown"
    recommendations = {
        "Good": "No turbidity band, thermal flag, or configured threshold raises concern in this saved assessment. Continue routine monitoring.",
        "Fair": "Review the measured value and compare it with recent samples. Keep routine monitoring in place.",
        "Poor": "Review the flagged measurement, verify sensor calibration, and confirm with a follow-up sample. This application is not a water-safety certification.",
        "Critical": "Prioritize review of the triggered rule, verify the sensor and its calibration, and confirm with a follow-up sample. This application is not a water-safety certification.",
        "Unknown": "No quality category is available. Verify sensor input or configure a threshold for the available measurement before drawing a conclusion.",
    }

    measurements = [
        {
            "group": group_name,
            "channels": [
                {
                    "label": CHANNEL_LABELS[field],
                    "value": format_sensor_value(field, getattr(reading, field)),
                }
                for field in fields
            ],
        }
        for group_name, fields in SUPPORTING_CHANNELS.items()
    ]

    return {
        "latest_reading": reading,
        "triggered_rules": triggered_rules,
        "analysis_groups": analysis_groups,
        "measurements": measurements,
        "recommendation": recommendations.get(status, recommendations["Unknown"]),
    }
