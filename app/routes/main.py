from flask import Blueprint, render_template

from app.extensions import db
from app.models.alert import Alert
from app.models.reading import Reading
from app.models.river import River
from app.models.sensor import Sensor
from app.services.decision_support_service import get_decision_support_data
from app.services.measurement_format_service import format_sensor_value


main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Display the AquaSense dashboard."""
    sensor_types = [
        {
            "name": "Turbidity Sensor",
            "symbol": "NTU",
            "accent": "aqua",
            "metrics": [
                ("Turbidity", "turbidity_ntu"),
                ("TSS estimate", "tss"),
                ("Particle level", "particle_level"),
                ("Clarity", "clarity"),
            ],
        },
        {
            "name": "TDS Sensor",
            "symbol": "TDS",
            "accent": "blue",
            "metrics": [
                ("TDS", "tds_ppm"),
                ("Conductivity estimate", "conductivity"),
                ("Ionic content score", "ionic_content"),
                ("Salinity estimate", "salinity"),
            ],
        },
        {
            "name": "pH Sensor",
            "symbol": "pH",
            "accent": "green",
            "metrics": [
                ("pH", "ph_value"),
                ("Acidity score", "acidity"),
                ("Alkalinity score", "alkalinity"),
                ("pH stability", "ph_stability"),
            ],
        },
        {
            "name": "Temperature Sensor",
            "symbol": "°C",
            "accent": "amber",
            "metrics": [
                ("Water temperature", "temperature_c"),
                ("Ambient temperature", "ambient_temperature"),
                ("Change rate", "change_rate"),
                ("Thermal anomaly", "thermal_anomaly"),
            ],
        },
    ]

    for sensor in sensor_types:
        results = []
        for label, field in sensor["metrics"]:
            reading = (
                Reading.query
                .filter(getattr(Reading, field).isnot(None))
                .order_by(Reading.recorded_at.desc(), Reading.id.desc())
                .first()
            )
            value = getattr(reading, field) if reading else None
            results.append({
                "label": label,
                "field": field,
                "value": format_sensor_value(field, value),
                "time": (
                    reading.recorded_at.strftime("%b %d · %I:%M %p").replace(" 0", " ")
                    if reading and reading.recorded_at
                    else "Awaiting reading"
                ),
                "river_name": reading.river.name if reading and reading.river else None,
                "quality_status": reading.quality_status if reading else None,
            })
        sensor["results"] = results

    average_turbidity = db.session.query(db.func.avg(Reading.turbidity_ntu)).scalar()
    summary = {
        "total_rivers": River.query.count(),
        "active_sensors": Sensor.query.filter_by(is_active=True).count(),
        "avg_turbidity": average_turbidity,
        "alerts_open": Alert.query.filter_by(status="open").count(),
        "sensor_types": sensor_types,
    }

    alerts = (
        Alert.query.filter_by(status="open")
        .order_by(Alert.created_at.desc())
        .limit(5)
        .all()
    )
    sensors = Sensor.query.order_by(Sensor.name.asc()).limit(6).all()
    recent_readings = (
        Reading.query
        .order_by(Reading.recorded_at.desc(), Reading.id.desc())
        .limit(8)
        .all()
    )

    for reading in recent_readings:
        reading.time_label = (
            reading.recorded_at.strftime("%I:%M %p").lstrip("0")
            if reading.recorded_at
            else "—"
        )
        reading.display_ph = format_sensor_value("ph_value", reading.ph_value)
        reading.display_temperature = format_sensor_value(
            "temperature_c",
            reading.temperature_c,
        )

    return render_template(
        "dashboard.html",
        summary=summary,
        alerts=alerts,
        sensors=sensors,
        recent_readings=recent_readings,
        sensor_types=sensor_types,
    )


@main_bp.route("/decision-support")
def decision_support():
    """Display the decision-support explanation page."""
    return render_template(
        "decision_support.html",
        **get_decision_support_data(),
    )


@main_bp.route("/about")
def about():
    """Display information about AquaSense."""
    return render_template("about.html")