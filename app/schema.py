from sqlalchemy import inspect

from app.extensions import db


SENSOR_READING_COLUMNS = {
    "tss": "FLOAT",
    "particle_level": "FLOAT",
    "clarity": "FLOAT",
    "acidity": "FLOAT",
    "alkalinity": "FLOAT",
    "ph_stability": "FLOAT",
    "ambient_temperature": "FLOAT",
    "change_rate": "FLOAT",
    "thermal_anomaly": "FLOAT",
    "conductivity": "FLOAT",
    "ionic_content": "FLOAT",
    "salinity": "FLOAT",
}


def ensure_sensor_reading_columns():
    """Add newly supported sensor channels to existing databases."""
    inspector = inspect(db.engine)
    if not inspector.has_table("readings"):
        return

    existing_columns = {
        column["name"] for column in inspector.get_columns("readings")
    }
    missing_columns = [
        name for name in SENSOR_READING_COLUMNS if name not in existing_columns
    ]
    if not missing_columns:
        return

    preparer = db.engine.dialect.identifier_preparer
    table_name = preparer.quote("readings")
    with db.engine.begin() as connection:
        for column_name in missing_columns:
            quoted_column = preparer.quote(column_name)
            connection.exec_driver_sql(
                f"ALTER TABLE {table_name} ADD COLUMN {quoted_column} FLOAT"
            )