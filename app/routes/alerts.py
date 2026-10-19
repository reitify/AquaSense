
from datetime import datetime, timezone
from math import isfinite

from flask import abort, Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.alert import Alert
from app.models.river import River
from app.models.threshold_rule import ThresholdRule
from app.services.measurement_format_service import format_sensor_value

alerts_bp = Blueprint("alerts", __name__, url_prefix="/alerts")

THRESHOLD_OPTIONS = (
    ("turbidity_ntu", "Turbidity (NTU)", 1),
    ("tss", "Total suspended solids", 1),
    ("particle_level", "Particle level (%)", 1),
    ("clarity", "Clarity (%)", 1),
    ("tds_ppm", "TDS (ppm)", 1),
    ("conductivity", "Conductivity (µS/cm)", 1),
    ("ionic_content", "Ionic content", 1),
    ("salinity", "Salinity (ppt)", 1),
    ("ph_value", "pH", 100),
    ("acidity", "Acidity (%)", 1),
    ("alkalinity", "Alkalinity (%)", 1),
    ("ph_stability", "pH stability (%)", 1),
    ("temperature_c", "Water temperature (°C)", 100),
    ("ambient_temperature", "Ambient temperature (°C)", 100),
    ("change_rate", "Temperature change rate (°C/min)", 100),
    ("thermal_anomaly", "Thermal anomaly (0 or 1)", 1),
)
THRESHOLD_OPTION_MAP = {
    parameter: (label, scale)
    for parameter, label, scale in THRESHOLD_OPTIONS
}
THRESHOLD_STATUSES = ("Fair", "Poor", "Critical")
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


def _require_threshold_admin():
    if current_user.role != "admin":
        abort(403)


def _parse_threshold_values(form, parameter=None):
    rule_name = form.get("rule_name", "").strip()
    if not rule_name or len(rule_name) > 100:
        raise ValueError("Enter a threshold name of 1 to 100 characters.")

    parameter = parameter or form.get("parameter", "")
    if parameter not in THRESHOLD_OPTION_MAP:
        raise ValueError("Choose a supported sensor measurement.")

    status = form.get("status", "")
    if status not in THRESHOLD_STATUSES:
        raise ValueError("Choose a valid alert severity.")

    _, scale = THRESHOLD_OPTION_MAP[parameter]
    values = {}
    for bound in ("min_value", "max_value"):
        raw_value = form.get(bound, "").strip()
        if not raw_value:
            values[bound] = None
            continue
        try:
            value = float(raw_value)
        except ValueError as error:
            raise ValueError("Thresholds must be valid numbers.") from error
        if not isfinite(value):
            raise ValueError("Thresholds must be finite numbers.")
        scaled_value = value * scale
        if not isfinite(scaled_value):
            raise ValueError("Threshold is outside the supported numeric range.")
        values[bound] = scaled_value

    minimum = values["min_value"]
    maximum = values["max_value"]
    if minimum is None and maximum is None:
        raise ValueError("Enter a minimum or maximum threshold.")
    if minimum is not None and maximum is not None and minimum >= maximum:
        raise ValueError("Minimum threshold must be lower than maximum.")

    return {
        "rule_name": rule_name,
        "parameter": parameter,
        "min_value": minimum,
        "max_value": maximum,
        "status": status,
        "description": form.get("description", "").strip()[:500] or None,
    }


def _commit_threshold_change(success_message):
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Unable to save an alert threshold.")
        flash("Could not save the threshold. Please try again.", "danger")
        return False
    flash(success_message, "success")
    return True


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
    is_admin = current_user.role == "admin"
    threshold_rules = (
        ThresholdRule.query.order_by(ThresholdRule.parameter, ThresholdRule.id).all()
        if is_admin
        else []
    )
    for rule in threshold_rules:
        _, scale = THRESHOLD_OPTION_MAP.get(rule.parameter, ("", 1))
        rule.min_display = (
            f"{rule.min_value / scale:g}" if rule.min_value is not None else ""
        )
        rule.max_display = (
            f"{rule.max_value / scale:g}" if rule.max_value is not None else ""
        )

    return render_template(
        "alerts.html",
        alerts=alerts,
        counts=counts,
        selected_status=selected_status,
        selected_severity=selected_severity,
        search_term=search_term,
        threshold_rules=threshold_rules,
        threshold_options=THRESHOLD_OPTIONS,
        threshold_labels={
            parameter: label for parameter, label, _ in THRESHOLD_OPTIONS
        },
        threshold_statuses=THRESHOLD_STATUSES,
        is_admin=is_admin,
    )


@alerts_bp.route("/thresholds", methods=["POST"])
@login_required
def create_threshold():
    """Create an active alert threshold for future sensor readings."""
    _require_threshold_admin()
    try:
        values = _parse_threshold_values(request.form)
    except ValueError as error:
        flash(str(error), "danger")
        return redirect(url_for("alerts.index"))

    db.session.add(ThresholdRule(is_active=True, **values))
    _commit_threshold_change("Alert threshold added.")
    return redirect(url_for("alerts.index"))


@alerts_bp.route("/thresholds/<int:rule_id>", methods=["POST"])
@login_required
def update_threshold(rule_id):
    """Update threshold bounds, severity, or active state."""
    _require_threshold_admin()
    rule = ThresholdRule.query.get_or_404(rule_id)
    try:
        values = _parse_threshold_values(request.form, parameter=rule.parameter)
    except ValueError as error:
        flash(str(error), "danger")
        return redirect(url_for("alerts.index"))

    for field, value in values.items():
        setattr(rule, field, value)
    rule.is_active = request.form.get("is_active") == "1"
    _commit_threshold_change("Alert threshold updated.")
    return redirect(url_for("alerts.index"))


@alerts_bp.route("/thresholds/<int:rule_id>/delete", methods=["POST"])
@login_required
def delete_threshold(rule_id):
    """Delete an alert threshold."""
    _require_threshold_admin()
    rule = ThresholdRule.query.get_or_404(rule_id)
    db.session.delete(rule)
    _commit_threshold_change("Alert threshold deleted.")
    return redirect(url_for("alerts.index"))


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
