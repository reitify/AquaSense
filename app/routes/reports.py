
from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template
from flask_login import login_required
from sqlalchemy import func

from app.extensions import db
from app.models.alert import Alert
from app.models.reading import Reading
from app.models.river import River
from app.services.local_analysis_service import analyze_monitoring_data
from app.services.measurement_format_service import format_sensor_delta, format_sensor_value
from app.services.time_service import format_app_datetime

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")

REPORT_FIELDS = (
    "turbidity_ntu", "tss", "particle_level", "clarity",
    "tds_ppm", "conductivity", "ionic_content", "salinity",
    "ph_value", "acidity", "alkalinity", "ph_stability",
    "temperature_c", "ambient_temperature", "change_rate", "thermal_anomaly",
    "water_quality_index",
)
REPORT_COLUMNS = [
    {"label": "Turbidity", "field": "turbidity_ntu", "unit": " NTU"},
    {"label": "TSS", "field": "tss", "unit": ""},
    {"label": "Particles", "field": "particle_level", "unit": ""},
    {"label": "Clarity", "field": "clarity", "unit": ""},
    {"label": "TDS", "field": "tds_ppm", "unit": " ppm"},
    {"label": "Conductivity", "field": "conductivity", "unit": ""},
    {"label": "Ionic content", "field": "ionic_content", "unit": ""},
    {"label": "Salinity", "field": "salinity", "unit": ""},
    {"label": "pH", "field": "ph_value", "unit": ""},
    {"label": "Acidity", "field": "acidity", "unit": ""},
    {"label": "Alkalinity", "field": "alkalinity", "unit": ""},
    {"label": "pH stability", "field": "ph_stability", "unit": ""},
    {"label": "Temperature", "field": "temperature_c", "unit": ""},
    {"label": "Ambient temp", "field": "ambient_temperature", "unit": ""},
    {"label": "Change rate", "field": "change_rate", "unit": ""},
    {"label": "Thermal anomaly", "field": "thermal_anomaly", "unit": ""},
    {"label": "WQI", "field": "water_quality_index", "unit": ""},
]


@reports_bp.route("/")
@login_required
def index():
    """Display the AquaSense reports page."""
    reading_count = Reading.query.count()
    river_count = db.session.query(
        func.count(func.distinct(Reading.river_id))
    ).scalar() or 0
    first_reading, latest_reading = db.session.query(
        func.min(Reading.recorded_at), func.max(Reading.recorded_at)
    ).one()
    status_counts = db.session.query(
        Reading.quality_status, func.count(Reading.id)
    ).group_by(Reading.quality_status).order_by(Reading.quality_status).all()
    alert_summary = {
        status: Alert.query.filter(db.func.lower(Alert.status) == status).count()
        for status in ("open", "monitoring", "resolved")
    }
    alert_summary["critical_open"] = Alert.query.filter(
        db.func.lower(Alert.status) == "open",
        db.func.lower(Alert.severity) == "critical",
    ).count()
    analysis = analyze_monitoring_data()
    for channel in analysis["channels"]:
        field = channel["field"]
        channel["display_mean"] = format_sensor_value(field, channel["mean"])
        channel["display_minimum"] = format_sensor_value(field, channel["minimum"])
        channel["display_maximum"] = format_sensor_value(field, channel["maximum"])
        if channel["trend"]:
            channel["display_first"] = format_sensor_value(field, channel["trend"]["first"])
            channel["display_latest"] = format_sensor_value(field, channel["trend"]["latest"])
            channel["display_change"] = format_sensor_delta(
                field,
                channel["trend"]["change"],
                channel["trend"]["first"],
            )

    channel_groups = []
    for group_name in (
        "Turbidity sensor", "TDS sensor", "pH sensor",
        "Temperature sensor", "Assessment",
    ):
        channels = [
            channel for channel in analysis["channels"]
            if channel["group"] == group_name
        ]
        if channels:
            channel_groups.append({"name": group_name, "channels": channels})

    report_rows = []
    for river in River.query.order_by(River.name.asc()).all():
        averages = db.session.query(
            *(func.avg(getattr(Reading, field)) for field in REPORT_FIELDS)
        ).filter(Reading.river_id == river.id).one()
        latest = (
            Reading.query.filter_by(river_id=river.id)
            .order_by(Reading.recorded_at.desc(), Reading.id.desc())
            .first()
        )
        averages_by_field = {
            field: round(float(value), 2) if value is not None else None
            for field, value in zip(REPORT_FIELDS, averages)
        }
        report_rows.append({
            "river": river.name,
            "date": (
                format_app_datetime(latest.recorded_at, "%d/%m/%y")
                if latest and latest.recorded_at
                else "—"
            ),
            "time": (
                format_app_datetime(latest.recorded_at, "%I:%M %p")
                if latest and latest.recorded_at
                else "—"
            ),
            "status": latest.quality_status if latest else "No readings",
            "averages": averages_by_field,
            "display_averages": {
                field: format_sensor_value(field, value)
                for field, value in averages_by_field.items()
            },
        })

    return render_template(
        "reports.html",
        report_rows=report_rows,
        report_columns=REPORT_COLUMNS,
        alert_summary=alert_summary,
        generated_at=format_app_datetime(
            datetime.now(timezone.utc),
            "%d/%m/%y %I:%M %p",
        ),
        summary={
            "reading_count": reading_count,
            "river_count": river_count,
            "first_reading_date": (
                format_app_datetime(first_reading, "%d/%m/%y")
                if first_reading
                else None
            ),
            "latest_reading_date": (
                format_app_datetime(latest_reading, "%d/%m/%y")
                if latest_reading
                else None
            ),
            "status_counts": status_counts,
        },
        analysis=analysis,
        channel_groups=channel_groups,
    )


@reports_bp.route("/api/summary")
@login_required
def summary():
    """Return a summary of available monitoring data."""
    total_rivers = River.query.count()
    total_readings = Reading.query.count()
    analysis = analyze_monitoring_data()

    latest_reading = (
        Reading.query
        .order_by(Reading.recorded_at.desc())
        .first()
    )

    return jsonify({
        "success": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_rivers": total_rivers,
        "total_readings": total_readings,
        "local_analysis": {
            "reading_count": analysis["reading_count"],
            "river_count": analysis["river_count"],
            "status_counts": analysis["status_counts"],
            "insights": analysis["insights"],
            "start_at": analysis["start_at"],
            "end_at": analysis["end_at"],
        },
        "latest_reading": (
            {
                "id": latest_reading.id,
                "river_id": latest_reading.river_id,
                **{field: getattr(latest_reading, field) for field in REPORT_FIELDS},
                "recorded_at": (
                    latest_reading.recorded_at.isoformat()
                    if latest_reading.recorded_at
                    else None
                ),
            }
            if latest_reading else None
        ),
        "report_status": "Generated",
    }), 200
