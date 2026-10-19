
from app.extensions import db
from app.models.alert import Alert
from app.models.reading import Reading
from app.models.threshold_rule import ThresholdRule
from app.services.assessment_service import determine_quality_status
from sqlalchemy.exc import SQLAlchemyError


THRESHOLD_PARAMETERS = {
    "turbidity": "turbidity_ntu",
    "turbidity_ntu": "turbidity_ntu",
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
THRESHOLD_PARAMETERS.update({
    "tss": "tss",
    "particle_level": "particle_level",
    "clarity": "clarity",
    "tds_ppm": "tds_ppm",
    "conductivity": "conductivity",
    "ionic_content": "ionic_content",
    "salinity": "salinity",
    "ph_value": "ph_value",
    "acidity": "acidity",
    "alkalinity": "alkalinity",
    "ph_stability": "ph_stability",
    "temperature_c": "temperature_c",
    "ambient_temperature": "ambient_temperature",
    "change_rate": "change_rate",
    "thermal_anomaly": "thermal_anomaly",
})
QUALITY_STATUS_RANK = {"Unknown": -1, "Good": 0, "Fair": 1, "Poor": 2, "Critical": 3}
RULE_STATUS_RANK = {
    "good": 0,
    "fair": 1,
    "warning": 1,
    "moderate": 1,
    "poor": 2,
    "high": 2,
    "critical": 3,
}
READING_SEVERITIES = {
    "Good": "low",
    "Fair": "warning",
    "Poor": "high",
    "Critical": "critical",
}


def create_reading_notice(reading):
    """Create an informational alert entry for a reading with no alert yet."""
    if reading is None or reading.id is None:
        raise ValueError("A saved reading is required.")

    existing_alert = Alert.query.filter_by(reading_id=reading.id).first()
    if existing_alert is not None:
        return existing_alert

    status = reading.quality_status or "Unknown"
    alert = Alert(
        river_id=reading.river_id,
        reading_id=reading.id,
        message=f"Reading #{reading.id} recorded. Assessment: {status}.",
        status="open",
        severity=READING_SEVERITIES.get(status, "low"),
        created_at=reading.recorded_at,
    )

    try:
        db.session.add(alert)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise

    return alert


def backfill_reading_notices():
    """Ensure every historical reading has at least one linked alert entry."""
    readings = (
        Reading.query
        .filter(
            ~Reading.id.in_(
                db.session.query(Alert.reading_id)
                .filter(Alert.reading_id.isnot(None))
            )
        )
        .order_by(Reading.recorded_at.asc(), Reading.id.asc())
        .all()
    )
    if not readings:
        return 0

    alerts = [
        Alert(
            river_id=reading.river_id,
            reading_id=reading.id,
            message=(
                f"Reading #{reading.id} recorded. "
                f"Assessment: {reading.quality_status or 'Unknown'}."
            ),
            status="open",
            severity=READING_SEVERITIES.get(
                reading.quality_status or "Unknown",
                "low",
            ),
            created_at=reading.recorded_at,
        )
        for reading in readings
    ]

    try:
        db.session.add_all(alerts)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise

    return len(alerts)


def create_alert(reading, message=None):
    """Create alerts for existing quality status and configured rules."""
    if reading is None or reading.id is None:
        raise ValueError("A saved reading is required.")

    breaches = []
    for rule in ThresholdRule.query.filter_by(is_active=True).all():
        parameter = str(rule.parameter).strip().lower().replace(" ", "_")
        field = THRESHOLD_PARAMETERS.get(parameter)
        value = getattr(reading, field, None) if field else None
        if value is None:
            continue
        below_minimum = rule.min_value is not None and value < rule.min_value
        above_maximum = rule.max_value is not None and value > rule.max_value
        if below_minimum or above_maximum:
            breaches.append((rule, field, value))

    alerts = []
    status = getattr(reading, "quality_status", None)
    status_rank = QUALITY_STATUS_RANK.get(status, -1)
    baseline_status = determine_quality_status(reading.turbidity_ntu)
    baseline_rank = QUALITY_STATUS_RANK[baseline_status]
    rule_covers_status = any(
        RULE_STATUS_RANK.get(str(rule.status).strip().lower(), -1) >= status_rank
        for rule, _, _ in breaches
    )
    turbidity_rule_covers_baseline = any(
        field == "turbidity_ntu"
        and RULE_STATUS_RANK.get(str(rule.status).strip().lower(), -1) >= baseline_rank
        for rule, field, _ in breaches
    )
    thermal_rule_covers_anomaly = any(
        field == "thermal_anomaly"
        and RULE_STATUS_RANK.get(str(rule.status).strip().lower(), -1) >= 2
        for rule, field, _ in breaches
    )
    uncovered_quality_finding = (
        (baseline_rank >= 2 and not turbidity_rule_covers_baseline)
        or (
            reading.thermal_anomaly is not None
            and reading.thermal_anomaly > 0
            and not thermal_rule_covers_anomaly
        )
        or not rule_covers_status
    )
    if status in {"Poor", "Critical"} and uncovered_quality_finding:
        if message is None:
            message = (
                f"Water quality requires attention for river ID "
                f"{reading.river_id}. Recorded turbidity: "
                f"{reading.turbidity_ntu} NTU."
            )
        alerts.append(Alert(
            river_id=reading.river_id,
            reading_id=reading.id,
            message=message,
            status="open",
            severity="critical" if status == "Critical" else "high",
        ))

    for rule, field, value in breaches:
        rule_status = str(rule.status).strip().lower()
        severity = (
            "critical" if rule_status == "critical"
            else "high" if rule_status in {"high", "poor"}
            else "warning"
        )
        details = rule.description or rule.rule_name
        alerts.append(Alert(
            river_id=reading.river_id,
            reading_id=reading.id,
            message=f"{rule.rule_name}: {field} measured {value:g}. {details}",
            status="open",
            severity=severity,
        ))

    if not alerts:
        return create_reading_notice(reading)

    try:
        db.session.add_all(alerts)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise

    return alerts[0]
