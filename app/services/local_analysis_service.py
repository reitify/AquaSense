from collections import Counter
from datetime import timezone
from statistics import median

from sqlalchemy.orm import joinedload

from app.models.reading import Reading
from app.models.threshold_rule import ThresholdRule


CHANNELS = [
    {"label": "Turbidity", "field": "turbidity_ntu", "group": "Turbidity sensor"},
    {"label": "TSS", "field": "tss", "group": "Turbidity sensor"},
    {"label": "Particle level", "field": "particle_level", "group": "Turbidity sensor"},
    {"label": "Clarity", "field": "clarity", "group": "Turbidity sensor"},
    {"label": "TDS", "field": "tds_ppm", "group": "TDS sensor"},
    {"label": "Conductivity", "field": "conductivity", "group": "TDS sensor"},
    {"label": "Ionic content", "field": "ionic_content", "group": "TDS sensor"},
    {"label": "Salinity", "field": "salinity", "group": "TDS sensor"},
    {"label": "pH", "field": "ph_value", "group": "pH sensor"},
    {"label": "Acidity", "field": "acidity", "group": "pH sensor"},
    {"label": "Alkalinity", "field": "alkalinity", "group": "pH sensor"},
    {"label": "pH stability", "field": "ph_stability", "group": "pH sensor"},
    {"label": "Temperature", "field": "temperature_c", "group": "Temperature sensor"},
    {"label": "Ambient temperature", "field": "ambient_temperature", "group": "Temperature sensor"},
    {"label": "Change rate", "field": "change_rate", "group": "Temperature sensor"},
    {"label": "Thermal anomaly", "field": "thermal_anomaly", "group": "Temperature sensor"},
    {"label": "Water quality index", "field": "water_quality_index", "group": "Assessment"},
]

THRESHOLD_FIELDS = {
    "turbidity": "turbidity_ntu",
    "total_suspended_solids": "tss",
    "particle": "particle_level",
    "water_clarity": "clarity",
    "tds": "tds_ppm",
    "electrical_conductivity": "conductivity",
    "ionic": "ionic_content",
    "salt_content": "salinity",
    "ph": "ph_value",
    "temperature": "temperature_c",
    "ambient_temp": "ambient_temperature",
    "temperature_change_rate": "change_rate",
}
THRESHOLD_FIELDS.update({channel["field"]: channel["field"] for channel in CHANNELS})


def _timestamp(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _channel_trend(values):
    first = values[0]
    latest = values[-1]
    delta = latest - first
    direction = "unchanged" if delta == 0 else "increasing" if delta > 0 else "decreasing"
    return {
        "first": round(first, 2),
        "latest": round(latest, 2),
        "change": round(delta, 2),
        "direction": direction,
    }


def _find_outliers(readings):
    """Find robust univariate outliers only when there are enough observations."""
    outliers = []
    for channel in CHANNELS:
        field = channel["field"]
        measured = [
            (reading, getattr(reading, field))
            for reading in readings
            if getattr(reading, field) is not None
        ]
        if len(measured) < 5:
            continue

        center = median(value for _, value in measured)
        deviation = median(abs(value - center) for _, value in measured)
        if deviation == 0:
            continue

        for reading, value in measured:
            modified_z_score = 0.6745 * (value - center) / deviation
            if abs(modified_z_score) > 3.5:
                outliers.append({
                    "label": channel["label"],
                    "field": field,
                    "value": value,
                    "river": reading.river.name if reading.river else f"River {reading.river_id}",
                    "recorded_at": _timestamp(reading.recorded_at),
                    "score": round(modified_z_score, 2),
                })
    return outliers


def _threshold_findings(readings):
    findings = []
    rules = ThresholdRule.query.filter_by(is_active=True).order_by(ThresholdRule.id.asc()).all()
    for rule in rules:
        parameter = str(rule.parameter).strip().lower().replace(" ", "_")
        field = THRESHOLD_FIELDS.get(parameter)
        if field is None:
            continue

        breaches = []
        for reading in readings:
            value = getattr(reading, field, None)
            if value is None:
                continue
            if (rule.min_value is not None and value < rule.min_value) or (
                rule.max_value is not None and value > rule.max_value
            ):
                breaches.append((reading, value))

        if breaches:
            findings.append({
                "rule": rule.rule_name,
                "parameter": parameter,
                "status": rule.status,
                "count": len(breaches),
                "min_value": rule.min_value,
                "max_value": rule.max_value,
                "description": rule.description,
            })
    return findings


def analyze_monitoring_data():
    """Build offline, explainable insights from every saved sensor reading."""
    readings = (
        Reading.query
        .options(joinedload(Reading.river))
        .order_by(Reading.recorded_at.asc(), Reading.id.asc())
        .all()
    )
    rivers = {reading.river_id for reading in readings}
    status_counts = dict(Counter(
        reading.quality_status or "Unknown" for reading in readings
    ))

    channel_summaries = []
    for channel in CHANNELS:
        measured = [
            (reading, getattr(reading, channel["field"]))
            for reading in readings
            if getattr(reading, channel["field"]) is not None
        ]
        values = [value for _, value in measured]
        channel_summaries.append({
            **channel,
            "count": len(values),
            "coverage_percent": round(len(values) * 100 / len(readings), 1) if readings else 0,
            "mean": round(sum(values) / len(values), 2) if values else None,
            "minimum": min(values) if values else None,
            "maximum": max(values) if values else None,
            "latest_value": values[-1] if values else None,
            "latest_at": _timestamp(measured[-1][0].recorded_at) if measured else None,
            "trend": _channel_trend(values) if len(values) >= 2 else None,
        })

    outliers = _find_outliers(readings)
    threshold_findings = _threshold_findings(readings)
    statuses_to_report = [
        f"{count} {status.lower()}"
        for status, count in sorted(status_counts.items())
    ]
    insights = []

    if readings:
        start = readings[0].recorded_at
        end = readings[-1].recorded_at
        insights.append({
            "kind": "coverage",
            "title": "Dataset coverage",
            "detail": (
                f"Scanned {len(readings)} saved readings across {len(rivers)} rivers, "
                f"from {_timestamp(start)} through {_timestamp(end)}."
            ),
        })
        if statuses_to_report:
            insights.append({
                "kind": "status",
                "title": "Recorded assessments",
                "detail": "Stored status counts: " + ", ".join(statuses_to_report) + ".",
            })

        missing = [
            channel for channel in channel_summaries
            if 0 < channel["count"] < len(readings)
        ]
        absent = [channel for channel in channel_summaries if channel["count"] == 0]
        if missing or absent:
            missing_labels = [
                f"{channel['label']} ({len(readings) - channel['count']} missing)"
                for channel in missing
            ] + [f"{channel['label']} (no data)" for channel in absent]
            insights.append({
                "kind": "coverage-gap",
                "title": "Channel coverage gaps",
                "detail": "; ".join(missing_labels) + ".",
            })

        trends = [
            f"{channel['label']} {channel['trend']['direction']} "
            f"({channel['trend']['first']:g} to {channel['trend']['latest']:g})"
            for channel in channel_summaries
            if channel["trend"] and channel["trend"]["direction"] != "unchanged"
        ]
        if trends:
            insights.append({
                "kind": "trend",
                "title": "Chronological channel changes",
                "detail": "; ".join(trends[:8]) + ("; more changes available in channel summaries." if len(trends) > 8 else "."),
            })
        else:
            insights.append({
                "kind": "trend",
                "title": "Trend confidence",
                "detail": "At least two measured values per channel are needed to compare chronological change.",
            })
    else:
        start = end = None
        insights.append({
            "kind": "coverage",
            "title": "No monitoring data yet",
            "detail": "No saved readings were found; local analysis will populate after sensor readings are recorded.",
        })

    if outliers:
        insights.append({
            "kind": "anomaly",
            "title": "Statistical outliers to review",
            "detail": (
                f"Found {len(outliers)} value(s) beyond the modified z-score threshold. "
                "This is a statistical flag, not a water-safety classification."
            ),
        })
    elif len(readings) >= 5:
        insights.append({
            "kind": "anomaly",
            "title": "Statistical anomaly scan",
            "detail": "No outliers passed the robust modified z-score threshold in channels with sufficient variation.",
        })

    if threshold_findings:
        for finding in threshold_findings:
            bound = []
            if finding["min_value"] is not None:
                bound.append(f"minimum {finding['min_value']:g}")
            if finding["max_value"] is not None:
                bound.append(f"maximum {finding['max_value']:g}")
            insights.append({
                "kind": "threshold",
                "title": f"Configured rule: {finding['rule']}",
                "detail": (
                    f"{finding['count']} reading(s) breached the configured "
                    f"{finding['parameter']} {' / '.join(bound)} limit."
                ),
            })

    return {
        "reading_count": len(readings),
        "river_count": len(rivers),
        "start_at": _timestamp(start),
        "end_at": _timestamp(end),
        "status_counts": status_counts,
        "channels": channel_summaries,
        "outliers": outliers,
        "threshold_findings": threshold_findings,
        "insights": insights,
    }