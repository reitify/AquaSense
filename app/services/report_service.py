
from datetime import datetime, timezone

from sqlalchemy import func

from app.models.reading import Reading
from app.models.river import River


def generate_summary_report(river_id=None):
    """Generate a summary of recorded water-quality readings."""
    query = Reading.query

    if river_id is not None:
        query = query.filter(Reading.river_id == river_id)

    total_readings = query.count()

    latest_reading = (
        query.order_by(Reading.recorded_at.desc()).first()
    )

    averages = query.with_entities(
        func.avg(Reading.turbidity_ntu),
        func.avg(Reading.water_quality_index),
    ).first()

    river = None

    if river_id is not None:
        river = db_get_river(river_id)

        if river is None:
            raise ValueError("The specified river does not exist.")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "river": (
            {
                "id": river.id,
                "name": river.name,
            }
            if river else None
        ),
        "total_readings": total_readings,
        "average_turbidity_ntu": (
            round(float(averages[0]), 2)
            if averages and averages[0] is not None
            else None
        ),
        "average_wqi": (
            round(float(averages[1]), 2)
            if averages and averages[1] is not None
            else None
        ),
        "latest_reading": (
            {
                "id": latest_reading.id,
                "river_id": latest_reading.river_id,
                "turbidity_ntu": latest_reading.turbidity_ntu,
                "water_quality_index": (
                    latest_reading.water_quality_index
                ),
                "quality_status": latest_reading.quality_status,
                "recorded_at": (
                    latest_reading.recorded_at.isoformat()
                    if latest_reading.recorded_at
                    else None
                ),
            }
            if latest_reading else None
        ),
    }


def db_get_river(river_id):
    """Retrieve a river by its primary key."""
    return River.query.get(river_id)
