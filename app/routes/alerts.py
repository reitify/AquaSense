
from datetime import datetime, timezone

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import or_

from app.extensions import db
from app.models.alert import Alert
from app.models.river import River
from app.services.measurement_format_service import format_sensor_value

alerts_bp = Blueprint("alerts", __name__, url_prefix="/alerts")

SENSOR_GROUPS = [
    ("Turbidity sensor", [
        ("Turbidity", "turbidity_ntu"),
        ("TSS estimate", "tss"),
        ("Particle level", "particle_level"),
        ("Clarity", "clarity"),
    ]),
    ("TDS sensor", [
        ("TDS", "tds_ppm"),
        ("Conductivity estimate", "conductivity"),
        ("Ionic content score", "ionic_content"),
        ("Salinity estimate", "salinity"),
    ]),
    ("pH sensor", [
        ("pH", "ph_value"),
        ("Acidity score", "acidity"),
        ("Alkalinity score", "alkalinity"),
        ("pH stability", "ph_stability"),
    ]),
    ("Temperature sensor", [
        ("Water temperature", "temperature_c"),
        ("Ambient temperature", "ambient_temperature"),
        ("Change rate", "change_rate"),
        ("Thermal anomaly", "thermal_anomaly"),
    ]),
]


@alerts_bp.route("/")
@login_required
def index():
    """Display water-quality alerts."""
    selected_status = request.args.get("status", "all").lower()
    if selected_status not in {"all", "open", "monitoring", "resolved"}:
        selected_status = "all"
    selected_severity = request.args.get("severity", "all").lower()
    if selected_severity not in {"all", "critical", "high", "warning", "moderate", "low"}:
        selected_severity = "all"
    search_term = request.args.get("q", "").strip()[:120]

    query = Alert.query
    if selected_status != "all":
        query = query.filter(db.func.lower(Alert.status) == selected_status)
    if selected_severity != "all":
        query = query.filter(db.func.lower(Alert.severity) == selected_severity)
    if search_term:
        pattern = f"%{search_term}%"
        query = query.outerjoin(Alert.river).filter(
            or_(Alert.message.ilike(pattern), River.name.ilike(pattern))
        )

    alerts = query.order_by(Alert.created_at.desc(), Alert.id.desc()).all()
    for alert in alerts:
        alert.sensor_groups = []
        if alert.reading:
            recorded_at = alert.reading.recorded_at
            time_label = (
                recorded_at.strftime("%I:%M %p").lstrip("0")
                if recorded_at else "—"
            )
            for group_name, channels in SENSOR_GROUPS:
                alert.sensor_groups.append({
                    "name": group_name,
                    "measurements": [
                        {
                            "label": label,
                            "value": format_sensor_value(
                                field,
                                getattr(alert.reading, field),
                            ),
                            "time": time_label,
                        }
                        for label, field in channels
                    ],
                })
    counts = {
        status: Alert.query.filter(db.func.lower(Alert.status) == status).count()
        for status in ("open", "monitoring", "resolved")
    }
    return render_template(
        "alerts.html",
        alerts=alerts,
        counts=counts,
        selected_status=selected_status,
        selected_severity=selected_severity,
        search_term=search_term,
    )


@alerts_bp.route("/<int:alert_id>/status", methods=["POST"])
@login_required
def update_status(alert_id):
    """Update an alert's review state."""
    alert = Alert.query.get_or_404(alert_id)
    status = request.form.get("status", "").lower()
    if status not in {"open", "monitoring", "resolved"}:
        flash("Choose a valid alert status.", "danger")
        return redirect(url_for("alerts.index"))

    alert.status = status
    alert.resolved_at = datetime.now(timezone.utc) if status == "resolved" else None
    db.session.commit()
    flash("Alert status updated.", "success")
    return redirect(url_for("alerts.index", status=request.form.get("return_status", "all")))


@alerts_bp.route("/api")
@login_required
def get_alerts():
    """Return recent alerts as JSON."""
    alerts = Alert.query.order_by(Alert.created_at.desc(), Alert.id.desc()).limit(500).all()

    return jsonify({
        "success": True,
        "count": len(alerts),
        "alerts": [
            {
                "id": alert.id,
                "message": getattr(alert, "message", None),
                "status": getattr(alert, "status", None),
                "severity": alert.severity,
                "river": alert.river.name if alert.river else None,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
                "reading": (
                    {
                        field: getattr(alert.reading, field)
                        for field in (
                            "turbidity_ntu", "tss", "particle_level", "clarity",
                            "tds_ppm", "conductivity", "ionic_content", "salinity",
                            "ph_value", "acidity", "alkalinity", "ph_stability",
                            "temperature_c", "ambient_temperature", "change_rate",
                            "thermal_anomaly", "water_quality_index", "quality_status",
                        )
                    } | {
                        "recorded_at": (
                            alert.reading.recorded_at.isoformat()
                            if alert.reading.recorded_at else None
                        )
                    }
                    if alert.reading else None
                ),
            }
            for alert in alerts
        ],
    }), 200
