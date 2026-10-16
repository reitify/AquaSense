# Latest and historical reading endpoints

from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from app.extensions import db
from app.models.reading import Reading
from app.services.measurement_format_service import format_sensor_value

readings_bp = Blueprint("readings", __name__, url_prefix="/readings")


@readings_bp.route("/")
@login_required
def index():
    """Display historical water-quality readings."""
    readings = Reading.query.order_by(Reading.recorded_at.desc()).all()
    display_fields = (
        "turbidity_ntu", "tss", "particle_level", "clarity", "tds_ppm",
        "conductivity", "ionic_content", "salinity", "ph_value", "acidity",
        "alkalinity", "ph_stability", "temperature_c", "ambient_temperature",
        "change_rate", "thermal_anomaly", "water_quality_index",
    )
    for reading in readings:
        reading.display_values = {
            field: format_sensor_value(field, getattr(reading, field))
            for field in display_fields
        }
    return render_template("historical_records.html", readings=readings)


@readings_bp.route("/api")
@login_required
def get_readings():
    """Return recent readings as JSON for the frontend."""
    limit_param = request.args.get("limit")

    if limit_param is None or limit_param.lower() in {"all", "none", "0"}:
        limit = None
    else:
        try:
            limit = max(1, min(int(limit_param), 5000))
        except ValueError:
            limit = None

    query = Reading.query.order_by(Reading.recorded_at.desc())

    river_id = request.args.get("river_id", type=int)
    if river_id is not None:
        query = query.filter(Reading.river_id == river_id)

    readings = query.all() if limit is None else query.limit(limit).all()

    return jsonify({
        "success": True,
        "count": len(readings),
        "readings": [
            {
                "id": reading.id,
                "river_id": reading.river_id,
                "turbidity_ntu": reading.turbidity_ntu,
                "tss": reading.tss,
                "particle_level": reading.particle_level,
                "clarity": reading.clarity,
                "conductivity": reading.conductivity,
                "ionic_content": reading.ionic_content,
                "salinity": reading.salinity,
                "ph_value": reading.ph_value,
                "acidity": reading.acidity,
                "alkalinity": reading.alkalinity,
                "ph_stability": reading.ph_stability,
                "temperature_c": reading.temperature_c,
                "ambient_temperature": reading.ambient_temperature,
                "change_rate": reading.change_rate,
                "thermal_anomaly": reading.thermal_anomaly,
                "tds_ppm": reading.tds_ppm,
                "water_quality_index": reading.water_quality_index,
                "quality_status": reading.quality_status,
                "recorded_at": (
                    reading.recorded_at.isoformat()
                    if reading.recorded_at
                    else None
                ),
            }
            for reading in readings
        ],
    }), 200
