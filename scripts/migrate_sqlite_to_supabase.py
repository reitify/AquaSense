import os
from pathlib import Path

from sqlalchemy import URL, create_engine, inspect, select, text

from app import create_app
from app.extensions import db
from app.schema import ensure_sensor_reading_columns


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = PROJECT_ROOT / "instance" / "aquasense.db"


def _copy_table(source_connection, target_connection, table):
    source_inspector = inspect(source_connection)
    source_column_names = {
        column["name"] for column in source_inspector.get_columns(table.name)
    }
    columns = [
        column for column in table.columns
        if column.name in source_column_names
    ]
    if not columns:
        return 0

    statement = select(*columns)
    result = source_connection.execute(statement)
    copied = 0
    while rows := result.fetchmany(500):
        target_connection.execute(
            table.insert(),
            [dict(row._mapping) for row in rows],
        )
        copied += len(rows)
    return copied


def _advance_postgres_sequences(connection, tables):
    dialect = db.engine.dialect
    preparer = dialect.identifier_preparer
    for table in tables:
        if "id" not in table.c or not table.c.id.primary_key:
            continue
        table_name = preparer.quote(table.name)
        connection.execute(text(
            "SELECT setval(pg_get_serial_sequence(:table_name, 'id'), "
            f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {table_name}"
        ), {"table_name": table.name})


def main():
    database_url = os.getenv("DATABASE_URL") or os.getenv(
        "SQLALCHEMY_DATABASE_URI"
    )
    if not database_url:
        raise SystemExit("Set DATABASE_URL to the Supabase transaction-pooler URL first.")

    app = create_app()
    if not db.engine.url.drivername.startswith("postgresql"):
        raise SystemExit("The destination DATABASE_URL must use PostgreSQL.")

    source_path = Path(os.getenv("SOURCE_SQLITE_PATH", str(DEFAULT_SOURCE))).resolve()
    if not source_path.exists():
        raise SystemExit(f"SQLite source database not found: {source_path}")

    with app.app_context():
        db.create_all()
        ensure_sensor_reading_columns()
        tables = db.metadata.sorted_tables
        source_engine = create_engine(URL.create(
            "sqlite",
            database=str(source_path),
        ))
        source_tables = set(inspect(source_engine).get_table_names())

        with source_engine.connect() as source_connection, db.engine.begin() as target_connection:
            target_inspector = inspect(target_connection)
            for table in tables:
                if target_inspector.has_table(table.name):
                    count = target_connection.execute(
                        select(db.func.count()).select_from(table)
                    ).scalar_one()
                    if count:
                        raise SystemExit(
                            f"Destination table {table.name} is not empty; refusing to duplicate data."
                        )

            copied_rows = {}
            for table in tables:
                if table.name in source_tables:
                    copied_rows[table.name] = _copy_table(
                        source_connection,
                        target_connection,
                        table,
                    )
            _advance_postgres_sequences(target_connection, tables)

        source_engine.dispose()

    total = sum(copied_rows.values())
    print(f"Copied {total} rows from {source_path.name} to Supabase.")
    for table_name, count in copied_rows.items():
        if count:
            print(f"  {table_name}: {count}")


if __name__ == "__main__":
    main()