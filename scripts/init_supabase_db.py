from app import create_app
from app.extensions import db
from app.schema import ensure_sensor_reading_columns


def main():
    app = create_app()
    with app.app_context():
        if not db.engine.url.drivername.startswith("postgresql"):
            raise SystemExit(
                "DATABASE_URL must point to Supabase PostgreSQL before initializing."
            )
        db.create_all()
        ensure_sensor_reading_columns()
    print("Supabase schema initialized.")


if __name__ == "__main__":
    main()