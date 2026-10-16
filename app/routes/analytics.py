
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required
from sqlalchemy import func

from app.extensions import db
from app.models.reading import Reading
from app.services.measurement_format_service import format_sensor_value

analytics_bp = Blueprint(
    "analytics",
    __name__,
    url_prefix="/analytics",
)

SENSOR_CHANNELS = {
    "Turbidity": [("Turbidity", "turbidity_ntu"), ("TSS", "tss"), ("Particle level", "particle_level"), ("Clarity", "clarity")],
    "TDS": [("TDS", "tds_ppm"), ("Conductivity", "conductivity"), ("Ionic content", "ionic_content"), ("Salinity", "salinity")],
    "pH": [("pH", "ph_value"), ("Acidity", "acidity"), ("Alkalinity", "alkalinity"), ("pH stability", "ph_stability")],
    "Temperature": [("Temperature", "temperature_c"), ("Ambient temperature", "ambient_temperature"), ("Change rate", "change_rate"), ("Thermal anomaly", "thermal_anomaly")],
}

TIME_RANGES = {
    "24h": ("Past 24 hours", timedelta(hours=24)),
    "7d": ("Past 7 days", timedelta(days=7)),
    "30d": ("Past 30 days", timedelta(days=30)),
    "all": ("All recorded data", None),
}


def _reading_query(selected_range):
    query = Reading.query
    duration = TIME_RANGES[selected_range][1]
    if duration is not None:
        query = query.filter(
            Reading.recorded_at >= datetime.now(timezone.utc) - duration
        )
    return query


def _reading_summary(selected_range="all"):
    fields = [field for channels in SENSOR_CHANNELS.values() for _, field in channels]
    fields.append("water_quality_index")
    result = _reading_query(selected_range).with_entities(
        func.count(Reading.id),
        *(func.avg(getattr(Reading, field)) for field in fields),
    ).one()
    averages = {
        field: round(float(value), 2) if value is not None else None
        for field, value in zip(fields, result[1:])
    }
    return result[0], averages


def _recent_points(selected_range="all"):
    readings = (
        _reading_query(selected_range)
        .order_by(Reading.recorded_at.desc(), Reading.id.desc())
        .limit(6)
        .all()
    )
    points = [
        {
            "label": reading.recorded_at.strftime("%b %d") if reading.recorded_at else f"#{reading.id}",
            "turbidity": reading.turbidity_ntu,
            "turbidity_display": format_sensor_value("turbidity_ntu", reading.turbidity_ntu),
            "wqi": reading.water_quality_index,
            "tds": reading.tds_ppm,
            "tds_display": format_sensor_value("tds_ppm", reading.tds_ppm),
            "ph": (
                reading.ph_value / 100
                if reading.ph_value is not None and abs(reading.ph_value) > 14
                else reading.ph_value
            ),
            "ph_display": format_sensor_value("ph_value", reading.ph_value),
            "temperature": (
                reading.temperature_c / 100
                if reading.temperature_c is not None and abs(reading.temperature_c) > 125
                else reading.temperature_c
            ),
            "temperature_display": format_sensor_value("temperature_c", reading.temperature_c),
            "time": reading.recorded_at.strftime("%I:%M %p").lstrip("0") if reading.recorded_at else "—",
        }
        for reading in reversed(readings)
    ]
    chart_channels = ("turbidity", "tds", "ph", "temperature")
    chart_maxima = {
        channel: max(
            (point[channel] for point in points if point[channel] is not None),
            default=0,
        )
        for channel in chart_channels
    }
    for point in points:
        for channel in chart_channels:
            value = point[channel]
            point[f"{channel}_height"] = (
                round(value * 100 / chart_maxima[channel], 1)
                if value is not None and chart_maxima[channel] > 0
                else 0
            )
    return points


@analytics_bp.route("/")
@login_required
def index():
    """Display water-quality analytics."""
    selected_range = request.args.get("range", "all").lower()
    if selected_range not in TIME_RANGES:
        selected_range = "all"
    total_readings, averages = _reading_summary(selected_range)
    scoped_readings = _reading_query(selected_range)
    summary = {
        "avg_turbidity": averages["turbidity_ntu"],
        "avg_tds": averages["tds_ppm"],
        "avg_ph": averages["ph_value"],
        "avg_temperature": averages["temperature_c"],
        "avg_wqi": averages.get("water_quality_index"),
        "max_turbidity": scoped_readings.with_entities(func.max(Reading.turbidity_ntu)).scalar(),
        "total_readings": total_readings,
        "risk_readings": scoped_readings.filter(
            Reading.quality_status.in_(["Poor", "Critical"])
        ).count(),
    }
    sensor_averages = [
        {
            "name": name,
            "channels": [
                {
                    "label": label,
                    "value": averages[field],
                    "display_value": (
                        f"{averages[field] * 100:.0f}% readings flagged"
                        if field == "thermal_anomaly" and averages[field] is not None
                        else format_sensor_value(field, averages[field])
                    ),
                }
                for label, field in channels
            ],
        }
        for name, channels in SENSOR_CHANNELS.items()
    ]
    trend_points = _recent_points(selected_range)
    recent_turbidity_max = max(
        (point["turbidity"] for point in trend_points if point["turbidity"] is not None),
        default=0,
    )
    recent_tds_max = max(
        (point["tds"] for point in trend_points if point["tds"] is not None),
        default=0,
    )
    recent_ph_max = max(
        (point["ph"] for point in trend_points if point["ph"] is not None),
        default=0,
    )
    recent_temperature_max = max(
        (point["temperature"] for point in trend_points if point["temperature"] is not None),
        default=0,
    )

    return render_template(
        "analytics.html",
        summary=summary,
        sensor_averages=sensor_averages,
        trend_points=trend_points,
        selected_range=selected_range,
        selected_range_label=TIME_RANGES[selected_range][0],
        has_turbidity_data=any(point["turbidity"] is not None for point in trend_points),
        has_tds_data=any(point["tds"] is not None for point in trend_points),
        has_ph_data=any(point["ph"] is not None for point in trend_points),
        has_temperature_data=any(point["temperature"] is not None for point in trend_points),
        recent_turbidity_max=recent_turbidity_max,
        recent_tds_max=recent_tds_max,
        recent_ph_max=recent_ph_max,
        recent_temperature_max=recent_temperature_max,
    )


@analytics_bp.route("/api")
@login_required
def get_analytics():
    """Return summary statistics for recorded readings."""
    total_readings, averages = _reading_summary()

    return jsonify({
        "success": True,
        "total_readings": total_readings,
        "averages": averages,
        "average_turbidity_ntu": averages["turbidity_ntu"],
        "average_wqi": averages["water_quality_index"],
        "recent_trend": _recent_points(),
    }), 200
