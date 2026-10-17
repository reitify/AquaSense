
from app.extensions import db
from app.models.assessment import Assessment
from app.models.reading import Reading
from app.models.threshold_rule import ThresholdRule


RULE_FIELDS = {
    "turbidity": "turbidity_ntu",
    "turbidity_ntu": "turbidity_ntu",
    "total_suspended_solids": "tss",
    "tss": "tss",
    "particle": "particle_level",
    "particle_level": "particle_level",
    "water_clarity": "clarity",
    "clarity": "clarity",
    "tds": "tds_ppm",
    "tds_ppm": "tds_ppm",
    "electrical_conductivity": "conductivity",
    "conductivity": "conductivity",
    "ionic": "ionic_content",
    "ionic_content": "ionic_content",
    "salt_content": "salinity",
    "salinity": "salinity",
    "ph": "ph_value",
    "ph_value": "ph_value",
    "acidity": "acidity",
    "alkalinity": "alkalinity",
    "ph_stability": "ph_stability",
    "temperature": "temperature_c",
    "temperature_c": "temperature_c",
    "ambient_temp": "ambient_temperature",
    "ambient_temperature": "ambient_temperature",
    "temperature_change_rate": "change_rate",
    "change_rate": "change_rate",
    "thermal_anomaly": "thermal_anomaly",
}
STATUS_RANK = {"Unknown": -1, "Good": 0, "Fair": 1, "Poor": 2, "Critical": 3}
RULE_STATUSES = {
    "good": "Good",
    "fair": "Fair",
    "warning": "Fair",
    "moderate": "Fair",
    "poor": "Poor",
    "high": "Poor",
    "critical": "Critical",
}


def determine_quality_status(turbidity_ntu):
    """Classify a reading using a configurable turbidity threshold."""
    if turbidity_ntu is None:
        return "Unknown"

    if turbidity_ntu < 0:
        raise ValueError("Turbidity cannot be negative.")

    if turbidity_ntu <= 5:
        return "Good"

    if turbidity_ntu <= 10:
        return "Fair"

    return "Poor"


def calculate_water_quality_index(reading):
    """Calculate AquaSense's equal-weight 0-100 demo index from primary sensors."""
    scores = []

    if reading.turbidity_ntu is not None:
        scores.append(max(0.0, min(100.0, 100.0 - reading.turbidity_ntu)))

    if reading.ph_value is not None:
        ph_value = reading.ph_value
        if abs(ph_value) > 14:
            ph_value /= 100
        scores.append(max(0.0, 100.0 - abs(ph_value - 7.0) * 20.0))

    if reading.tds_ppm is not None:
        tds_ppm = max(0.0, reading.tds_ppm)
        scores.append(max(0.0, 100.0 - tds_ppm / 20.0))

    if reading.temperature_c is not None:
        temperature = reading.temperature_c
        if abs(temperature) > 125:
            temperature /= 100
        scores.append(max(0.0, 100.0 - abs(temperature - 25.0) * 2.0))

    if not scores:
        return None

    return round(sum(scores) / len(scores), 2)


def assess_reading(reading):
    """Assess a reading and update its quality status."""
    if reading is None:
        raise ValueError("A reading is required.")

    if reading.water_quality_index is None:
        reading.water_quality_index = calculate_water_quality_index(reading)

    status = determine_quality_status(reading.turbidity_ntu)
    if reading.thermal_anomaly is not None and reading.thermal_anomaly > 0:
        status = "Poor"

    for rule in ThresholdRule.query.filter_by(is_active=True).all():
        parameter = str(rule.parameter).strip().lower().replace(" ", "_")
        field = RULE_FIELDS.get(parameter)
        value = getattr(reading, field, None) if field else None
        if value is None:
            continue
        breached = (
            rule.min_value is not None and value < rule.min_value
        ) or (
            rule.max_value is not None and value > rule.max_value
        )
        rule_status = RULE_STATUSES.get(str(rule.status).strip().lower())
        if breached and rule_status and STATUS_RANK[rule_status] > STATUS_RANK[status]:
            status = rule_status

    reading.quality_status = status

    return reading.quality_status


def create_assessment(reading):
    """Create and save an assessment for a reading."""
    if reading is None or reading.id is None:
        raise ValueError("A saved reading is required.")

    status = assess_reading(reading)

    assessment = Assessment(
        river_id=reading.river_id,
        reading_id=reading.id,
        status=status,
    )

    try:
        db.session.add(assessment)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return assessment
