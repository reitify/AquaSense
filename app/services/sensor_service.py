
from datetime import datetime, timezone

from app.extensions import db
from app.models.sensor import Sensor


def get_sensor_by_device_id(device_id):
    """Find a registered sensor using its device ID."""
    if not device_id:
        return None

    return Sensor.query.filter_by(device_id=device_id).first()


def update_sensor_last_seen(sensor):
    """Update the last-seen timestamp for a sensor."""
    if sensor is None:
        return False

    sensor.last_seen_at = datetime.now(timezone.utc)
    db.session.commit()
    return True


def get_sensor_status(sensor, timeout_minutes=10):
    """Return whether a sensor is active and recently connected."""
    if sensor is None or not getattr(sensor, "is_active", True):
        return "offline"

    last_seen = getattr(sensor, "last_seen_at", None)

    if last_seen is None:
        return "offline"

    now = datetime.now(timezone.utc)

    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)

    elapsed_seconds = (now - last_seen).total_seconds()

    if elapsed_seconds < 0:
        return "offline"

    return (
        "online"
        if elapsed_seconds <= timeout_minutes * 60
        else "offline"
    )
