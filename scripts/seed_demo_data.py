from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.alert import Alert
from app.models.reading import Reading
from app.models.river import River
from app.models.sensor import Sensor
from app.models.station import Station


def seed_demo_data():
    """Create a small demonstration dataset for AquaSense."""
    legacy_river_names = {
        "Maja River": "Matiktik River",
        "Cascades Creek": "Bakas River",
        "Bunga River": "Kanyakan River",
    }
    for old_name, new_name in legacy_river_names.items():
        river = River.query.filter_by(name=old_name).first()
        if river is not None and River.query.filter_by(name=new_name).first() is None:
            river.name = new_name

    rivers = [
        {
            "name": "Matiktik River",
            "barangay": "Maja",
            "municipality": "Norzagaray",
            "location_description": "North monitoring reach",
            "latitude": 14.9181,
            "longitude": 121.0778,
            "description": "A river reach with moderate agricultural runoff.",
        },
        {
            "name": "Bakas River",
            "barangay": "Bunga",
            "municipality": "Norzagaray",
            "location_description": "Forest edge and community outlet",
            "latitude": 14.9307,
            "longitude": 121.0986,
            "description": "Creek with higher turbidity during heavy rain.",
        },
        {
            "name": "Kanyakan River",
            "barangay": "Bunga",
            "municipality": "Norzagaray",
            "location_description": "Lower basin monitoring site",
            "latitude": 14.9125,
            "longitude": 121.1086,
            "description": "Lower basin river with variable turbidity and flow.",
        },
    ]

    created_rivers = []
    for river_data in rivers:
        river = River.query.filter_by(name=river_data["name"]).first()
        if river is None:
            river = River(**river_data)
            db.session.add(river)
            db.session.flush()
        created_rivers.append(river)

    sensors = [
        ("M-001", "Turbidity Sensor", created_rivers[0].id),
        ("C-002", "TDS Sensor", created_rivers[1].id),
        ("B-003", "pH Sensor", created_rivers[2].id),
        ("B-004", "Temperature Sensor", created_rivers[2].id),
        ("DEMO-ALL-SENSORS", "All-channel Demo Sensor", created_rivers[0].id),
    ]

    created_sensors = []
    for device_id, name, river_id in sensors:
        sensor = Sensor.query.filter_by(device_id=device_id).first()
        if sensor is None:
            sensor = Sensor(
                device_id=device_id,
                name=name,
                river_id=river_id,
                is_active=True,
            )
            db.session.add(sensor)
            db.session.flush()
        created_sensors.append(sensor)

    stations = [
        ("UP-01", "Matiktik Upstream Station", created_rivers[0].id, 14.9188, 121.0782),
        ("MID-02", "Bakas Mid Reach Station", created_rivers[1].id, 14.9312, 121.0991),
        ("LOW-03", "Kanyakan Intake Station", created_rivers[2].id, 14.9128, 121.1095),
    ]

    for code, name, river_id, latitude, longitude in stations:
        station = Station.query.filter_by(station_code=code).first()
        if station is None:
            station = Station(
                station_code=code,
                name=name,
                river_id=river_id,
                latitude=latitude,
                longitude=longitude,
                description="Demo monitoring station",
            )
            db.session.add(station)
        else:
            station.name = name

    now = datetime.now(timezone.utc)
    reading_samples = [
        (created_rivers[0].id, 3.2, 6.8, 27.1, 120.0, now - timedelta(hours=3), "manual"),
        (created_rivers[0].id, 4.6, 7.4, 28.5, 150.0, now - timedelta(hours=2), "device"),
        (created_rivers[1].id, 6.1, 8.1, 26.7, 220.0, now - timedelta(hours=4), "device"),
        (created_rivers[1].id, 7.8, 9.3, 26.1, 280.0, now - timedelta(hours=1), "device"),
        (created_rivers[2].id, 2.1, 5.9, 25.4, 96.0, now - timedelta(hours=5), "manual"),
        (created_rivers[2].id, 2.7, 6.1, 26.3, 101.0, now - timedelta(hours=2), "device"),
        (created_rivers[0].id, 12.5, 9.7, 29.2, 410.0, now - timedelta(hours=1), "device"),
        (created_rivers[1].id, 10.4, 8.8, 27.7, 350.0, now - timedelta(hours=0), "device"),
    ]

    created_readings = []
    for river_id, turbidity, wqi, temperature, tds, timestamp, source in reading_samples:
        reading = Reading.query.filter_by(
            river_id=river_id,
            turbidity_ntu=turbidity,
            recorded_at=timestamp,
        ).first()

        if reading is None:
            reading = Reading(
                river_id=river_id,
                turbidity_ntu=turbidity,
                water_quality_index=wqi,
                temperature_c=temperature,
                tds_ppm=tds,
                quality_status="Poor" if turbidity >= 10 else "Fair" if turbidity >= 5 else "Good",
                recorded_at=timestamp,
                source=source,
                device_id=next((sensor.device_id for sensor in created_sensors if sensor.river_id == river_id), None),
            )
            db.session.add(reading)
            db.session.flush()
        created_readings.append(reading)

    sample_reading = Reading.query.filter_by(
        device_id="DEMO-ALL-SENSORS",
        source="demo",
    ).first()
    if sample_reading is None:
        sample_reading = Reading(
            river_id=created_rivers[0].id,
            turbidity_ntu=12,
            tss=8,
            particle_level=15,
            clarity=85,
            tds_ppm=245,
            conductivity=490,
            ionic_content=25,
            salinity=0,
            ph_value=725,
            acidity=0,
            alkalinity=0,
            ph_stability=95,
            temperature_c=2846,
            ambient_temperature=3000,
            change_rate=12,
            thermal_anomaly=0,
            quality_status="Poor",
            recorded_at=now,
            source="demo",
            device_id="DEMO-ALL-SENSORS",
        )
        db.session.add(sample_reading)
        db.session.flush()
    created_readings.append(sample_reading)

    for reading in created_readings:
        if reading.quality_status == "Poor":
            alert = Alert.query.filter_by(reading_id=reading.id).first()
            if alert is None:
                db.session.add(
                    Alert(
                        river_id=reading.river_id,
                        reading_id=reading.id,
                        message=(
                            f"Water quality alert triggered: turbidity {reading.turbidity_ntu} NTU "
                            f"on river {reading.river_id}."
                        ),
                        status="open",
                        severity="high" if reading.turbidity_ntu >= 10 else "warning",
                    )
                )

    db.session.commit()

    return {
        "rivers": len(created_rivers),
        "sensors": len(created_sensors),
        "readings": len(created_readings),
        "alerts": Alert.query.count(),
    }


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        summary = seed_demo_data()
        print(f"Seeded demo data: {summary}")
