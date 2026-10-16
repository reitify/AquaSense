from flask import Blueprint, jsonify, render_template
from flask_login import login_required

from app.models.sensor import Sensor

sensors_bp = Blueprint("sensors", __name__, url_prefix="/sensors")


@sensors_bp.route("/")
@login_required
def index():
    """Display the registered sensors dashboard."""
    return render_template("sensor_management.html")


@sensors_bp.route("/api")
@login_required
def get_sensors():
    """Return installed sensor metadata for the frontend."""
    sensors = Sensor.query.order_by(Sensor.id.asc()).all()

    return jsonify({
        "success": True,
        "count": len(sensors),
        "sensors": [
            {
                "id": sensor.id,
                "device_id": sensor.device_id,
                "name": sensor.name,
                "river_id": sensor.river_id,
                "is_active": sensor.is_active,
                "last_seen_at": (
                    sensor.last_seen_at.isoformat()
                    if sensor.last_seen_at is not None
                    else None
                ),
            }
            for sensor in sensors
        ],
    }), 200
