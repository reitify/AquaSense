
from datetime import datetime, timezone
from math import isfinite

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import csrf, db
from app.models.reading import Reading
from app.models.river import River
from app.models.sensor import Sensor
from app.services.alert_service import create_alert
from app.services.assessment_service import assess_reading, create_assessment

ingestion_bp = Blueprint(
    "ingestion",
    __name__,
    url_prefix="/api/ingestion",
)

WOKWI_DEMO_RIVERS = {
    "WOKWI-DEMO-BAKAS": ("Bakas River", "Bakas River (Demo - Synthetic)"),
    "WOKWI-DEMO-MATIKTIK": ("Matiktik River", "Matiktik River (Demo - Synthetic)"),
    "WOKWI-DEMO-KANYAKAN": ("Kanyakan River", "Kanyakan River (Demo - Synthetic)"),
    "WOKWI-DEMO-MARAMO": ("Maramo River", "Maramo River (Demo - Synthetic)"),
}

MEASUREMENT_FIELDS = {
    "turbidity_ntu": {"turbidity"},
    "tss": {"total_suspended_solids"},
    "particle_level": {"particle"},
    "clarity": {"water_clarity"},
    "tds_ppm": {"tds"},
    "conductivity": {"electrical_conductivity"},
    "ionic_content": {"ionic"},
    "salinity": {"salt_content"},
    "ph_value": {"ph"},
    "acidity": set(),
    "alkalinity": set(),
    "ph_stability": set(),
    "temperature_c": {"temperature"},
    "ambient_temperature": {"ambient_temp", "at"},
    "change_rate": {"temperature_change_rate"},
    "thermal_anomaly": set(),
}


def _measurement_values(payload):
    """Normalize recognized sensor keys and reject non-numeric values."""
    aliases = {
        alias: field
        for field, field_aliases in MEASUREMENT_FIELDS.items()
        for alias in field_aliases
    }
    values = {}
    for key, value in payload.items():
        normalized_key = str(key).strip().lower().replace(" ", "_")
        field = normalized_key if normalized_key in MEASUREMENT_FIELDS else aliases.get(normalized_key)
        if field is None or value is None:
            continue
        if isinstance(value, bool):
            raise ValueError(f"{key} must be numeric.")
        try:
            numeric_value = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{key} must be numeric.") from error
        if not isfinite(numeric_value):
            raise ValueError(f"{key} must be a finite number.")
        values[field] = numeric_value
    return values


def _clamp_int(value, minimum, maximum):
    return max(min(int(value + 0.5), maximum), minimum)


def _as_ph(value):
    return value / 100 if abs(value) > 14 else value


def _as_temperature(value):
    return value / 100 if abs(value) > 125 else value


def _fill_derived_measurements(values, device_id, river_id, recorded_at):
    """Fill absent derived channels using the ESP32's documented formulas."""
    values = dict(values)
    turbidity = values.get("turbidity_ntu")
    if turbidity is not None:
        values.setdefault("tss", _clamp_int(turbidity * 0.5, 0, 10000))
        particle_level = _clamp_int(turbidity / 10.0, 0, 100)
        values.setdefault("particle_level", particle_level)
        values.setdefault("clarity", 100 - particle_level)

    tds = values.get("tds_ppm")
    if tds is not None:
        values.setdefault("conductivity", _clamp_int(tds * 2.0, 0, 20000))
        values.setdefault("ionic_content", _clamp_int(tds / 10.0, 0, 100))
        values.setdefault("salinity", _clamp_int(tds / 1000.0, 0, 100))

    ph_value = values.get("ph_value")
    if ph_value is not None:
        ph_real = _as_ph(ph_value)
        values.setdefault(
            "acidity",
            _clamp_int((7.0 - ph_real) / 7.0 * 100.0, 0, 100),
        )
        values.setdefault(
            "alkalinity",
            _clamp_int((ph_real - 7.0) / 7.0 * 100.0, 0, 100),
        )

    ph_history = []
    if ph_value is not None and "ph_stability" not in values:
        ph_history = (
            Reading.query
            .filter_by(device_id=device_id, river_id=river_id)
            .filter(Reading.recorded_at < recorded_at)
            .filter(Reading.ph_value.isnot(None))
            .order_by(Reading.recorded_at.desc(), Reading.id.desc())
            .limit(29)
            .all()
        )

    if ph_value is not None and "ph_stability" not in values:
        ph_values = [
            item.ph_value * 100 if abs(item.ph_value) <= 14 else item.ph_value
            for item in ph_history
        ]
        current_ph = ph_value * 100 if abs(ph_value) <= 14 else ph_value
        ph_values.append(current_ph)
        values["ph_stability"] = _clamp_int(
            100 - (max(ph_values) - min(ph_values)) * 2,
            0,
            100,
        )

    temperature = values.get("temperature_c")
    ambient_temperature = values.get("ambient_temperature")
    if temperature is not None:
        water_temp_c = _as_temperature(temperature)
        if "change_rate" not in values:
            previous = (
                Reading.query
                .filter_by(device_id=device_id, river_id=river_id)
                .filter(Reading.recorded_at < recorded_at)
                .filter(Reading.temperature_c.isnot(None))
                .order_by(Reading.recorded_at.desc(), Reading.id.desc())
                .first()
            )
            if previous is None:
                values["change_rate"] = 0
            else:
                previous_at = previous.recorded_at
                if previous_at.tzinfo is None:
                    previous_at = previous_at.replace(tzinfo=timezone.utc)
                elapsed_minutes = (recorded_at - previous_at).total_seconds() / 60.0
                if elapsed_minutes > 0:
                    rate = (
                        water_temp_c - _as_temperature(previous.temperature_c)
                    ) / elapsed_minutes
                    values["change_rate"] = _clamp_int(rate * 100, -10000, 10000)

        if "thermal_anomaly" not in values:
            if water_temp_c > 40.0 or water_temp_c < 5.0:
                values["thermal_anomaly"] = 1
            elif ambient_temperature is not None:
                ambient_temp_c = _as_temperature(ambient_temperature)
                values["thermal_anomaly"] = int(
                    abs(water_temp_c - ambient_temp_c) > 10.0
                )

    return values


@ingestion_bp.route("/health", methods=["GET"])
def health():
    """Check whether the ingestion endpoint and its database are available."""
    try:
        db.session.execute(db.text("SELECT 1"))
    except SQLAlchemyError:
        current_app.logger.exception("Ingestion health check could not reach the database.")
        return jsonify({
            "success": False,
            "service": "AquaSense ingestion",
            "database": "unavailable",
        }), 503

    return jsonify({
        "success": True,
        "service": "AquaSense ingestion",
        "database": "connected",
    }), 200


@ingestion_bp.route("/reading", methods=["POST"])
@csrf.exempt
def ingest_reading():
    """Accept a sensor reading from an authorized device."""
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify({
            "success": False,
            "error": "A valid JSON object is required.",
        }), 400

    device_id = str(payload.get("device_id") or "").strip()
    requested_river_id = payload.get("river_id")

    if not device_id or (
        requested_river_id is None and device_id not in WOKWI_DEMO_RIVERS
    ):
        return jsonify({
            "success": False,
            "error": "device_id and river_id are required for this device.",
        }), 400

    if requested_river_id is not None:
        try:
            requested_river_id = int(requested_river_id)
        except (TypeError, ValueError):
            return jsonify({
                "success": False,
                "error": "river_id must be numeric.",
            }), 400

    if requested_river_id is not None and requested_river_id <= 0:
        return jsonify({
            "success": False,
            "error": "Invalid river ID.",
        }), 400

    try:
        measurement_values = _measurement_values(payload)
    except ValueError as error:
        return jsonify({"success": False, "error": str(error)}), 400

    if not measurement_values:
        return jsonify({
            "success": False,
            "error": "At least one sensor measurement is required.",
        }), 400

    if measurement_values.get("turbidity_ntu", 0) < 0:
        return jsonify({
            "success": False,
            "error": "Turbidity cannot be negative.",
        }), 400

    sensor = Sensor.query.filter_by(device_id=device_id).first()
    if device_id in WOKWI_DEMO_RIVERS:
        river_name, synthetic_river_name = WOKWI_DEMO_RIVERS[device_id]
        river = River.query.filter_by(name=synthetic_river_name).first()
        if river is None:
            river = River.query.filter_by(name=river_name).first()
        if river is None:
            river = River(
                name=synthetic_river_name,
                municipality="Norzagaray",
                description="Synthetic river used by the Wokwi demo sensor.",
            )
            db.session.add(river)
            db.session.flush()

        if sensor is None:
            sensor = Sensor(
                device_id=device_id,
                name=f"Wokwi demo sensor - {river_name}",
                river_id=river.id,
                is_active=True,
            )
            db.session.add(sensor)
            db.session.flush()
        elif sensor.river_id != river.id:
            sensor.river_id = river.id

    if sensor is None or not sensor.is_active:
        return jsonify({
            "success": False,
            "error": "Unknown sensor device.",
        }), 403

    if requested_river_id is not None and requested_river_id != sensor.river_id:
        return jsonify({
            "success": False,
            "error": "river_id does not match the registered sensor river.",
        }), 400

    river_id = sensor.river_id

    recorded_at = datetime.now(timezone.utc)
    timestamp = payload.get("recorded_at")
    if timestamp:
        try:
            recorded_at = datetime.fromisoformat(
                str(timestamp).replace("Z", "+00:00")
            )
        except ValueError:
            return jsonify({
                "success": False,
                "error": "recorded_at must be an ISO 8601 timestamp.",
            }), 400
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=timezone.utc)

    reading = Reading(
        **_fill_derived_measurements(
            measurement_values,
            device_id,
            river_id,
            recorded_at,
        ),
        river_id=river_id,
        source="device",
        device_id=device_id,
        recorded_at=recorded_at,
    )

    reading.quality_status = assess_reading(reading)
    sensor.last_seen_at = datetime.now(timezone.utc)

    try:
        db.session.add(reading)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": "Unable to save the reading.",
        }), 500

    try:
        create_assessment(reading)
        create_alert(reading)
    except Exception:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": "Reading saved, but alerting failed.",
        }), 500

    return jsonify({
        "success": True,
        "message": "Reading received.",
        "reading_id": reading.id,
        "quality_status": reading.quality_status,
    }), 201
