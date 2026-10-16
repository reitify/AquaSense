# River and monitoring-station routes

from flask import Blueprint, jsonify, render_template
from flask_login import login_required

from app.models.station import Station

stations_bp = Blueprint(
    "stations",
    __name__,
    url_prefix="/stations",
)


@stations_bp.route("/")
@login_required
def index():
    """Display monitoring stations."""
    return render_template("stations.html")


@stations_bp.route("/api")
@login_required
def get_stations():
    """Return monitoring stations as JSON."""
    stations = Station.query.order_by(Station.id.asc()).all()

    return jsonify({
        "success": True,
        "count": len(stations),
        "stations": [
            {
                "id": station.id,
                "name": station.name,
            }
            for station in stations
        ],
    }), 200
