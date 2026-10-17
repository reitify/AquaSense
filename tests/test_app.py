import json
import os
import re
import tempfile
from datetime import datetime, timedelta
from datetime import timezone

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", "sqlite://")

from app import create_app
from app.extensions import db
from app.models.alert import Alert
from app.models.assessment import Assessment
from app.models.audit_log import AuditLog
from app.models.reading import Reading
from app.models.river import River
from app.models.sensor import Sensor
from app.models.station import Station
from app.models.threshold_rule import ThresholdRule
from app.models.user import User
from app.schema import ensure_sensor_reading_columns
from app.services.assessment_service import calculate_water_quality_index
from app.services import chat_service
from app.services.chat_service import local_model_status
from app.services.local_analysis_service import analyze_monitoring_data
from app.services.measurement_format_service import format_sensor_delta, format_sensor_value
from scripts.seed_demo_data import seed_demo_data


def test_create_app_registers_routes():
    app = create_app()

    assert app is not None
    assert "main" in app.blueprints

    client = app.test_client()
    response = client.get("/")

    assert response.status_code == 200


def test_ingestion_health_checks_database_connection():
    app = create_app()

    response = app.test_client().get("/api/ingestion/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "service": "AquaSense ingestion",
        "database": "connected",
    }


def test_settings_page_shows_display_preferences_and_refresh_control():
    response = create_app().test_client().get("/settings")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Settings" in html
    assert 'id="settings-theme"' in html
    assert 'id="settings-refresh"' in html
    assert '<option value="15">15 seconds</option>' in html
    assert 'aria-label="Refresh settings page"' not in html
    assert "Other useful settings" not in html


def test_dashboard_shows_manual_and_configurable_refresh_controls():
    response = create_app().test_client().get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="dashboard-refresh-now"' in html
    assert 'id="dashboard-refresh-interval"' in html
    assert '<option value="0">Off</option>' in html
    assert '<option value="15">15 seconds</option>' in html
    assert '<option value="30">30 seconds</option>' in html
    assert '<option value="60">1 minute</option>' in html


def test_full_reset_requires_admin_confirmation_and_keeps_account_and_audit_log():
    app = create_app()
    app.config["WTF_CSRF_ENABLED"] = False

    with app.app_context():
        db.drop_all()
        db.create_all()
        admin = User(
            full_name="Reset Admin",
            username="reset-admin",
            email="reset-admin@example.com",
            role="admin",
            is_active=True,
        )
        admin.set_password("test-password")
        researcher = User(
            full_name="Researcher",
            username="researcher",
            email="researcher@example.com",
            role="researcher",
            is_active=True,
        )
        researcher.set_password("test-password")
        db.session.add_all([admin, researcher])
        db.session.commit()

        river = River(name="Reset River", municipality="Norzagaray")
        db.session.add(river)
        db.session.commit()
        sensor = Sensor(device_id="reset-sensor", name="Reset Sensor", river_id=river.id)
        station = Station(name="Reset Station", station_code="RESET-1", river_id=river.id)
        reading = Reading(river_id=river.id, turbidity_ntu=12, quality_status="Poor")
        rule = ThresholdRule(
            parameter="turbidity_ntu",
            rule_name="Reset rule",
            max_value=5,
            status="Poor",
        )
        db.session.add_all([sensor, station, reading, rule])
        db.session.commit()
        db.session.add_all([
            Assessment(river_id=river.id, reading_id=reading.id, status="Poor"),
            Alert(
                river_id=river.id,
                reading_id=reading.id,
                message="Reset test alert",
                severity="high",
            ),
            AuditLog(user_id=admin.id, action="before_reset"),
        ])
        admin_id = admin.id
        researcher_id = researcher.id
        db.session.commit()

    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    rejected = client.post(
        "/settings/delete-all",
        data={"confirmation": "DELETE"},
        follow_redirects=True,
    )
    assert rejected.status_code == 200
    assert "No data was deleted" in rejected.get_data(as_text=True)

    with app.app_context():
        assert Reading.query.count() == 1
        assert River.query.count() == 1

    response = client.post(
        "/settings/delete-all",
        data={"confirmation": "DELETE ALL"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Full reset complete" in response.get_data(as_text=True)

    with app.app_context():
        assert Alert.query.count() == 0
        assert Assessment.query.count() == 0
        assert Reading.query.count() == 0
        assert Sensor.query.count() == 0
        assert Station.query.count() == 0
        assert ThresholdRule.query.count() == 0
        assert River.query.count() == 0
        assert User.query.filter_by(id=admin_id).count() == 1
        assert User.query.filter_by(id=researcher_id).count() == 1
        assert AuditLog.query.count() == 2
        reset_log = AuditLog.query.filter_by(action="full_data_reset").one()
        assert reset_log.user_id == admin_id


def test_full_reset_is_admin_only():
    app = create_app()
    app.config["WTF_CSRF_ENABLED"] = False

    with app.app_context():
        db.drop_all()
        db.create_all()
        user = User(
            full_name="Researcher",
            username="non-admin",
            email="non-admin@example.com",
            role="researcher",
            is_active=True,
        )
        user.set_password("test-password")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True

    response = client.post(
        "/settings/delete-all",
        data={"confirmation": "DELETE ALL"},
    )

    assert response.status_code == 403


def test_full_reset_requires_csrf_token():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()
        admin = User(
            full_name="CSRF Admin",
            username="csrf-admin",
            email="csrf-admin@example.com",
            role="admin",
            is_active=True,
        )
        admin.set_password("test-password")
        db.session.add(admin)
        river = River(name="Protected River", municipality="Norzagaray")
        db.session.add(river)
        db.session.commit()
        admin_id = admin.id

    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(admin_id)
        session["_fresh"] = True

    response = client.post(
        "/settings/delete-all",
        data={"confirmation": "DELETE ALL"},
    )

    assert response.status_code == 400
    with app.app_context():
        assert River.query.count() == 1


def test_sensor_formatter_decodes_scaled_values_and_trends():
    assert format_sensor_value("ph_value", 725) == "7.25"
    assert format_sensor_value("temperature_c", 2846) == "28.46 °C"
    assert format_sensor_delta("ph_value", 20, 725) == "+0.20"
    assert format_sensor_delta("temperature_c", 20, 2846) == "+0.20"
    assert format_sensor_delta("change_rate", 12, 12) == "+0.12"


def test_default_admin_account_is_created_with_admin_credentials():
    app = create_app()

    with app.app_context():
        admin_user = User.query.filter_by(username="admin").first()
        assert admin_user is not None
        assert admin_user.role == "admin"
        assert admin_user.check_password("admin") is True


def test_chat_api_accepts_authenticated_message_without_csrf_token():
    app = create_app()
    user_id = None

    with app.app_context():
        db.drop_all()
        db.create_all()
        seed_demo_data()
        user = User(
            full_name="Test User",
            username="admin",
            email="admin@example.com",
            role="admin",
            is_active=True,
        )
        user.set_password("admin")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["_user_id"] = str(user_id)
            session["_fresh"] = True

        message = client.post(
            "/chat/api/message",
            json={"message": "What is the overall water quality status?"},
            follow_redirects=False,
        )

        assert message.status_code == 200
        payload = message.get_json()
        assert payload["success"] is True
        assert "answer" in payload


def test_decision_support_page_shows_rule_and_assessment_sections():
    app = create_app()

    client = app.test_client()
    response = client.get("/decision-support")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Decision Support" in html
    assert "Rule-Based Analysis" in html
    assert "Water Quality Assessment" in html
    assert "if turbidity_ntu <= 5" in html
    assert "if turbidity_ntu <= 10" in html
    assert "TURBIDITY_SLOPE = -1120.0" in html
    assert "133.42*v^3 - 255.86*v^2" in html
    assert "PH7_VOLTAGE defaults to 2.50 V" in html
    assert "change_rate = ((water_temp_c - previous_water_temp_c)" in html


def test_decision_support_evaluates_tds_ph_and_temperature_groups():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()
        river = River(name="Rule Analysis River", municipality="Norzagaray")
        db.session.add(river)
        db.session.commit()
        db.session.add_all([
            Reading(
                river_id=river.id,
                turbidity_ntu=4,
                tds_ppm=350,
                ph_value=725,
                temperature_c=2770,
                ambient_temperature=3000,
                thermal_anomaly=0,
                quality_status="Good",
            ),
            ThresholdRule(
                parameter="ph_value",
                rule_name="pH upper limit",
                max_value=700,
                status="Critical",
                description="Configured test threshold.",
            ),
        ])
        db.session.commit()

        response = app.test_client().get("/decision-support")
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Rule-based analysis by sensor" in html
        assert "TDS" in html and "No threshold configured" in html
        assert "pH upper limit" in html and "Critical" in html
        assert "ESP32 thermal check" in html and "No anomaly flag" in html
        assert "27.70 °C" in html


def test_chat_ai_reports_overall_status_and_highest_risk():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()
        seed_demo_data()

        overall = chat_service.answer_local_question("What is the overall water quality status?")
        risk = chat_service.answer_local_question("Which river is most at risk?")

        assert overall["mode"] in {"local-data", "local-model"}
        assert any(word in overall["answer"].lower() for word in ["good", "fair", "poor", "status"])
        assert "risk" in risk["answer"].lower() or "average turbidity" in risk["answer"].lower()


def test_ingestion_creates_alert_for_poor_quality():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()

        river = River(name="Test River", municipality="Norzagaray")
        db.session.add(river)
        db.session.commit()

        sensor = Sensor(device_id="sensor-test", name="Test Sensor", river_id=river.id)
        db.session.add(sensor)
        db.session.commit()

        client = app.test_client()
        response = client.post(
            "/api/ingestion/reading",
            json={
                "device_id": "sensor-test",
                "river_id": river.id,
                "turbidity_ntu": 12.5,
                "tss": 8,
                "particle_level": 15,
                "clarity": 85,
                "tds_ppm": 245,
                "conductivity": 490,
                "ionic_content": 25,
                "salinity": 0,
                "ph_value": 725,
                "acidity": 0,
                "alkalinity": 0,
                "ph_stability": 95,
                "temperature_c": 2846,
                "ambient_temperature": 3000,
                "change_rate": 12,
                "thermal_anomaly": 0,
            },
        )

        assert response.status_code == 201
        payload = response.get_json()
        assert payload["success"] is True

        reading = Reading.query.order_by(Reading.id.desc()).first()
        assert reading is not None
        assert reading.quality_status == "Poor"
        assert reading.tss == 8
        assert reading.particle_level == 15
        assert reading.clarity == 85
        assert reading.tds_ppm == 245
        assert reading.conductivity == 490
        assert reading.ionic_content == 25
        assert reading.salinity == 0
        assert reading.ph_value == 725
        assert reading.acidity == 0
        assert reading.alkalinity == 0
        assert reading.ph_stability == 95
        assert reading.temperature_c == 2846
        assert reading.ambient_temperature == 3000
        assert reading.change_rate == 12
        assert reading.thermal_anomaly == 0
        assert Alert.query.filter_by(reading_id=reading.id).count() == 1


def test_ingestion_fills_missing_esp32_derived_measurements():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()
        river = River(name="Derived River", municipality="Norzagaray")
        db.session.add(river)
        db.session.commit()
        db.session.add(Sensor(
            device_id="derived-sensor",
            name="ESP32 Sensor",
            river_id=river.id,
        ))
        db.session.add(ThresholdRule(
            parameter="tds_ppm",
            rule_name="TDS warning",
            max_value=100,
            status="Warning",
        ))
        db.session.commit()

        response = app.test_client().post(
            "/api/ingestion/reading",
            json={
                "device_id": "derived-sensor",
                "river_id": river.id,
                "turbidity_ntu": 20,
                "tds_ppm": 120,
                "ph_value": 725,
                "temperature_c": 4100,
                "ambient_temperature": 3000,
            },
        )

        assert response.status_code == 201
        reading = Reading.query.order_by(Reading.id.desc()).first()
        assert reading.tss == 10
        assert reading.particle_level == 2
        assert reading.clarity == 98
        assert reading.conductivity == 240
        assert reading.ionic_content == 12
        assert reading.salinity == 0
        assert reading.acidity == 0
        assert reading.alkalinity == 4
        assert reading.ph_stability == 100
        assert reading.change_rate == 0
        assert reading.thermal_anomaly == 1
        assert reading.quality_status == "Poor"
        alerts = Alert.query.filter_by(reading_id=reading.id).all()
        assert sorted(alert.severity for alert in alerts) == ["high", "warning"]


def test_wokwi_demo_sensor_is_registered_to_river_and_index_is_calculated():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()
        river = River(name="Maramo River (Demo - Synthetic)")
        db.session.add(river)
        db.session.commit()

        response = app.test_client().post(
            "/api/ingestion/reading",
            json={
                "device_id": "WOKWI-DEMO-MARAMO",
                "ph_value": 700,
                "turbidity_ntu": 5,
                "tds_ppm": 622,
                "temperature_c": 2600,
            },
        )

        assert response.status_code == 201
        reading = Reading.query.order_by(Reading.id.desc()).first()
        sensor = Sensor.query.filter_by(
            device_id="WOKWI-DEMO-MARAMO"
        ).one()
        assert sensor.river_id == river.id
        assert reading.river_id == river.id
        assert reading.water_quality_index == 90.47
        assert response.get_json()["success"] is True


def test_wokwi_bootstraps_a_missing_synthetic_river_and_sensor():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()

        response = app.test_client().post(
            "/api/ingestion/reading",
            json={
                "device_id": "WOKWI-DEMO-BAKAS",
                "turbidity_ntu": 5,
            },
        )

        assert response.status_code == 201
        river = River.query.filter_by(
            name="Bakas River (Demo - Synthetic)"
        ).one()
        sensor = Sensor.query.filter_by(
            device_id="WOKWI-DEMO-BAKAS"
        ).one()
        reading = Reading.query.one()
        assert sensor.river_id == river.id
        assert reading.river_id == river.id
        assert reading.water_quality_index == 95


def test_registered_sensor_cannot_submit_a_reading_for_another_river():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()
        registered_river = River(name="Registered River")
        other_river = River(name="Other River")
        db.session.add_all([registered_river, other_river])
        db.session.commit()
        db.session.add(Sensor(
            device_id="river-bound-sensor",
            name="River-bound Sensor",
            river_id=registered_river.id,
        ))
        db.session.commit()

        response = app.test_client().post(
            "/api/ingestion/reading",
            json={
                "device_id": "river-bound-sensor",
                "river_id": other_river.id,
                "turbidity_ntu": 5,
            },
        )

        assert response.status_code == 400
        assert Reading.query.count() == 0


def test_demo_index_uses_available_primary_sensor_scores():
    reading = Reading(
        river_id=1,
        turbidity_ntu=5,
        tds_ppm=600,
        ph_value=700,
        temperature_c=2600,
    )

    assert calculate_water_quality_index(reading) == 90.75


def test_configured_pH_threshold_creates_alert_without_turbidity():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()
        river = River(name="pH Rule River", municipality="Norzagaray")
        db.session.add(river)
        db.session.commit()
        db.session.add_all([
            Sensor(
                device_id="ph-rule-sensor",
                name="pH Sensor",
                river_id=river.id,
            ),
            ThresholdRule(
                parameter="ph_value",
                rule_name="pH upper limit",
                max_value=700,
                status="Critical",
                description="pH sensor value exceeded its configured limit.",
            ),
        ])
        db.session.commit()

        response = app.test_client().post(
            "/api/ingestion/reading",
            json={
                "device_id": "ph-rule-sensor",
                "river_id": river.id,
                "ph_value": 725,
            },
        )

        assert response.status_code == 201
        reading = Reading.query.order_by(Reading.id.desc()).first()
        alert = Alert.query.filter_by(reading_id=reading.id).first()
        assert reading.quality_status == "Critical"
        assert alert is not None
        assert alert.severity == "critical"
        assert "pH upper limit" in alert.message
        assert Alert.query.filter_by(reading_id=reading.id).count() == 1


def test_dashboard_lists_sensor_types():
    app = create_app()
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True).lower()

    for sensor_name in [
        "turbidity sensor",
        "tds sensor",
        "ph sensor",
        "temperature sensor",
    ]:
        assert sensor_name in html


def test_dashboard_shows_a_derived_index_for_older_readings_without_one():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()
        river = River(name="Index Display River")
        db.session.add(river)
        db.session.commit()
        reading = Reading(
            river_id=river.id,
            turbidity_ntu=5,
            quality_status="Good",
        )
        db.session.add(reading)
        db.session.commit()
        reading_id = reading.id

        response = app.test_client().get("/")

        assert response.status_code == 200
        assert b"<td>95</td>" in response.data
        assert db.session.get(Reading, reading_id).water_quality_index is None


def test_seed_demo_data_creates_records():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()

        summary = seed_demo_data()

        assert summary["rivers"] >= 3
        assert summary["sensors"] >= 3
        assert summary["readings"] >= 8
        assert summary["alerts"] >= 1
        assert River.query.count() >= 3
        assert Sensor.query.count() >= 3
        assert Reading.query.count() >= 8
        sample = Reading.query.filter_by(device_id="DEMO-ALL-SENSORS").first()
        assert sample is not None
        assert [
            sample.turbidity_ntu, sample.tss, sample.particle_level, sample.clarity,
            sample.tds_ppm, sample.conductivity, sample.ionic_content, sample.salinity,
            sample.ph_value, sample.acidity, sample.alkalinity, sample.ph_stability,
            sample.temperature_c, sample.ambient_temperature, sample.change_rate,
            sample.thermal_anomaly,
        ] == [12, 8, 15, 85, 245, 490, 25, 0, 725, 0, 0, 95, 2846, 3000, 12, 0]
        seed_demo_data()
        assert Reading.query.filter_by(device_id="DEMO-ALL-SENSORS").count() == 1


def test_readings_api_returns_all_records_by_default():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()

        user = User(
            full_name="Test User",
            username="tester",
            email="tester@example.com",
            role="researcher",
        )
        user.set_password("secret123")
        db.session.add(user)
        db.session.commit()

        river = River(name="Archive River", municipality="Norzagaray")
        db.session.add(river)
        db.session.commit()

        readings = [
            Reading(
                river_id=river.id,
                turbidity_ntu=idx,
                tss=idx + 1,
                thermal_anomaly=0,
                ph_value=7.0,
                temperature_c=25.0,
                tds_ppm=120,
                water_quality_index=75.0,
                quality_status="Good",
                source="test",
                device_id=f"sensor-{idx}",
            )
            for idx in range(120)
        ]
        db.session.add_all(readings)
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as session:
            session["_user_id"] = str(user.id)
            session["_fresh"] = True
        response = client.get("/readings/api")

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["success"] is True
        assert payload["count"] == 120
        assert payload["readings"][0]["tss"] == 120
        assert "thermal_anomaly" in payload["readings"][0]


def test_historical_records_page_displays_records_table():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()

        user = User(
            full_name="History User",
            username="historyuser",
            email="history@example.com",
            role="researcher",
        )
        user.set_password("secret123")
        db.session.add(user)
        db.session.commit()

        river = River(name="History River", municipality="Norzagaray")
        db.session.add(river)
        db.session.commit()

        db.session.add(
            Reading(
                river_id=river.id,
                turbidity_ntu=4.2,
                tss=77,
                ph_value=6.9,
                temperature_c=22.5,
                tds_ppm=110,
                water_quality_index=72.0,
                quality_status="Good",
                source="test",
                device_id="sensor-history",
            )
        )
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as session:
            session["_user_id"] = str(user.id)
            session["_fresh"] = True
        response = client.get("/readings/")

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "All records" in html
        assert "History River" in html
        assert "77" in html


def test_dashboard_shows_latest_values_for_all_sensors_with_time():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()

        river = River(name="Sensor Results River", municipality="Norzagaray")
        db.session.add(river)
        db.session.commit()
        db.session.add(
            Reading(
                river_id=river.id,
                turbidity_ntu=8.6,
                tss=8,
                particle_level=15,
                clarity=85,
                tds_ppm=330,
                conductivity=490,
                ionic_content=25,
                salinity=0,
                ph_value=7.2,
                acidity=0,
                alkalinity=0,
                ph_stability=95,
                temperature_c=23.1,
                ambient_temperature=30,
                change_rate=12,
                thermal_anomaly=0,
                water_quality_index=74.0,
                quality_status="Fair",
                recorded_at=datetime(2026, 10, 14, 2, 44, tzinfo=timezone.utc),
            )
        )
        db.session.commit()

        response = app.test_client().get("/")

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        for result in [
            "8.6 NTU", "8", "15", "85", "330 ppm", "490", "25", "0",
            "7.2", "95", "23.1", "30", "12", "2:44 AM",
        ]:
            assert result in html
        assert "7.20" in html
        assert "23.10 °C" in html
        assert "0.12 °C/min" in html


def test_alerts_page_shows_real_alert_sensor_values_and_timestamp():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()

        user = User(
            full_name="Alert Admin",
            username="alertadmin",
            email="alertadmin@example.com",
            role="admin",
        )
        user.set_password("secret123")
        river = River(name="Alert Test River", municipality="Norzagaray")
        db.session.add_all([user, river])
        db.session.commit()

        reading = Reading(
            river_id=river.id,
            turbidity_ntu=12.4,
            tss=8,
            particle_level=15,
            clarity=85,
            tds_ppm=480,
            conductivity=490,
            ionic_content=25,
            salinity=0,
            ph_value=6.1,
            acidity=0,
            alkalinity=0,
            ph_stability=95,
            temperature_c=29.3,
            ambient_temperature=30,
            change_rate=12,
            thermal_anomaly=0,
            water_quality_index=45.0,
            quality_status="Poor",
            recorded_at=datetime(2026, 10, 14, 2, 44, tzinfo=timezone.utc),
        )
        db.session.add(reading)
        db.session.commit()
        alert = Alert(
                river_id=river.id,
                reading_id=reading.id,
                message="Turbidity exceeded the safe threshold.",
                severity="critical",
                status="open",
                created_at=datetime(2026, 10, 14, 2, 44, tzinfo=timezone.utc),
            )
        db.session.add(alert)
        db.session.commit()

        app.config["WTF_CSRF_ENABLED"] = False
        client = app.test_client()
        with client.session_transaction() as session:
            session["_user_id"] = str(user.id)
            session["_fresh"] = True
        response = client.get("/alerts/")

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        for result in [
            "Alert Test River",
            "Turbidity exceeded the safe threshold.",
            "12.4 NTU",
            "480 ppm",
            "Conductivity",
            "490",
            "Particle level",
            "15",
            "6.1",
            "Alkalinity",
            "95",
            "29.3",
            "Thermal anomaly",
            "2:44 AM",
        ]:
            assert result in html

        api_response = client.get("/alerts/api")
        alert_data = api_response.get_json()["alerts"][0]
        assert alert_data["reading"]["ambient_temperature"] == 30
        assert alert_data["reading"]["thermal_anomaly"] == 0

        update_response = client.post(
            f"/alerts/{alert.id}/status",
            data={"status": "resolved", "return_status": "all"},
        )
        assert update_response.status_code == 302
        assert Alert.query.get(alert.id).status == "resolved"


def test_alert_search_and_severity_filters_compose():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()
        user = User(
            full_name="Filter Admin",
            username="filteradmin",
            email="filteradmin@example.com",
            role="admin",
        )
        user.set_password("secret123")
        north_river = River(name="North River", municipality="Norzagaray")
        south_river = River(name="South River", municipality="Norzagaray")
        db.session.add_all([user, north_river, south_river])
        db.session.commit()
        db.session.add_all([
            Alert(
                river_id=north_river.id,
                message="Turbidity threshold exceeded",
                severity="critical",
                status="open",
            ),
            Alert(
                river_id=south_river.id,
                message="TDS warning",
                severity="warning",
                status="open",
            ),
        ])
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as session:
            session["_user_id"] = str(user.id)
            session["_fresh"] = True
        response = client.get("/alerts/?status=open&severity=critical&q=North")

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "North River" in html
        assert "Turbidity threshold exceeded" in html
        assert "South River" not in html


def test_existing_readings_table_is_upgraded_for_all_sensor_channels():
    app = create_app()

    with app.app_context():
        db.drop_all()
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE readings (id INTEGER PRIMARY KEY, turbidity_ntu FLOAT)"
            )

        ensure_sensor_reading_columns()
        column_names = {
            column["name"]
            for column in db.inspect(db.engine).get_columns("readings")
        }
        assert {
            "tss", "particle_level", "clarity", "conductivity",
            "ionic_content", "salinity", "acidity", "alkalinity",
            "ph_stability", "ambient_temperature", "change_rate",
            "thermal_anomaly",
        }.issubset(column_names)


def test_analytics_and_reports_use_saved_sensor_data():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()
        user = User(
            full_name="Report User",
            username="reportuser",
            email="reportuser@example.com",
            role="researcher",
        )
        user.set_password("secret123")
        river = River(name="Measured River", municipality="Norzagaray")
        db.session.add_all([user, river])
        db.session.commit()
        db.session.add(
            Reading(
                river_id=river.id,
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
                water_quality_index=74,
                quality_status="Poor",
            )
        )
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as session:
            session["_user_id"] = str(user.id)
            session["_fresh"] = True

        analytics = client.get("/analytics/")
        reports = client.get("/reports/")
        analytics_api = client.get("/analytics/api").get_json()
        report_api = client.get("/reports/api/summary").get_json()

        assert analytics.status_code == 200
        assert reports.status_code == 200
        assert "490" in analytics.get_data(as_text=True)
        analytics_html = analytics.get_data(as_text=True)
        assert analytics_html.count('class="panel chart-panel"') == 4
        assert "7.25" in analytics_html
        assert "28.46 °C" in analytics_html
        report_html = reports.get_data(as_text=True)
        assert "Measured River" in report_html
        assert "AquaSense Local AI Analysis" in report_html
        assert "Print report" in report_html
        assert "1 readings" in report_html
        assert "7.25" in report_html
        assert "28.46 °C" in report_html
        assert analytics_api["total_readings"] == 1
        assert analytics_api["averages"]["ambient_temperature"] == 3000
        assert report_api["local_analysis"]["reading_count"] == 1


def test_analytics_time_range_filters_saved_readings():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()
        user = User(
            full_name="Analytics User",
            username="analyticsuser",
            email="analytics@example.com",
            role="researcher",
        )
        user.set_password("secret123")
        river = River(name="Range River", municipality="Norzagaray")
        db.session.add_all([user, river])
        db.session.commit()
        now = datetime.now(timezone.utc)
        db.session.add_all([
            Reading(
                river_id=river.id,
                turbidity_ntu=4,
                tds_ppm=100,
                recorded_at=now - timedelta(hours=3),
            ),
            Reading(
                river_id=river.id,
                turbidity_ntu=8,
                tds_ppm=200,
                recorded_at=now - timedelta(days=3),
            ),
            Reading(
                river_id=river.id,
                turbidity_ntu=12,
                tds_ppm=300,
                recorded_at=now - timedelta(days=45),
            ),
        ])
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as session:
            session["_user_id"] = str(user.id)
            session["_fresh"] = True
        week_response = client.get("/analytics/?range=7d")
        day_response = client.get("/analytics/?range=24h")

        assert week_response.status_code == 200
        assert "2 readings · Past 7 days" in week_response.get_data(as_text=True)
        assert "1 reading · Past 24 hours" in day_response.get_data(as_text=True)


def test_local_report_analysis_scans_all_rows_and_reports_channel_trends():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()
        river = River(name="Analysis River", municipality="Norzagaray")
        db.session.add(river)
        db.session.commit()

        timestamps = [
            datetime(2026, 10, 12, 2, 44, tzinfo=timezone.utc),
            datetime(2026, 10, 13, 2, 44, tzinfo=timezone.utc),
            datetime(2026, 10, 14, 2, 44, tzinfo=timezone.utc),
        ]
        db.session.add_all([
            Reading(
                river_id=river.id,
                recorded_at=timestamps[0],
                turbidity_ntu=4,
                ph_value=700,
                salinity=0,
                quality_status="Good",
            ),
            Reading(
                river_id=river.id,
                recorded_at=timestamps[1],
                turbidity_ntu=8,
                ph_value=725,
                salinity=5,
                quality_status="Fair",
            ),
            Reading(
                river_id=river.id,
                recorded_at=timestamps[2],
                turbidity_ntu=12,
                ph_value=750,
                salinity=10,
                quality_status="Poor",
            ),
        ])
        db.session.commit()

        analysis = analyze_monitoring_data()

        assert analysis["reading_count"] == 3
        assert analysis["river_count"] == 1
        assert analysis["status_counts"] == {"Good": 1, "Fair": 1, "Poor": 1}
        turbidity = next(
            channel for channel in analysis["channels"]
            if channel["field"] == "turbidity_ntu"
        )
        assert turbidity["count"] == 3
        assert turbidity["mean"] == 8
        assert turbidity["minimum"] == 4
        assert turbidity["maximum"] == 12
        assert turbidity["trend"]["direction"] == "increasing"
        salinity = next(
            channel for channel in analysis["channels"]
            if channel["field"] == "salinity"
        )
        assert salinity["minimum"] == 0
        assert analysis["threshold_findings"] == []


def test_local_report_analysis_flags_outliers_and_configured_thresholds():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()
        river = River(name="Outlier River", municipality="Norzagaray")
        db.session.add(river)
        db.session.commit()
        db.session.add_all([
            Reading(
                river_id=river.id,
                turbidity_ntu=value,
                recorded_at=datetime(2026, 10, 10 + index, tzinfo=timezone.utc),
                quality_status="Poor" if value > 10 else "Good",
            )
            for index, value in enumerate([4, 5, 5, 6, 100])
        ])
        db.session.add(
            ThresholdRule(
                parameter="turbidity_ntu",
                rule_name="Turbidity upper limit",
                max_value=10,
                status="Critical",
            )
        )
        db.session.commit()

        analysis = analyze_monitoring_data()

        assert analysis["reading_count"] == 5
        assert len(analysis["outliers"]) == 1
        assert analysis["outliers"][0]["value"] == 100
        assert len(analysis["threshold_findings"]) == 1
        assert analysis["threshold_findings"][0]["count"] == 1


def test_logout_form_includes_csrf_token_and_logs_out():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()
        user = User(
            full_name="Logout User",
            username="logoutuser",
            email="logoutuser@example.com",
            role="researcher",
        )
        user.set_password("secret123")
        db.session.add(user)
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as session:
            session["_user_id"] = str(user.id)
            session["_fresh"] = True

        dashboard = client.get("/")
        token_match = re.search(
            r'<input[^>]*name="csrf_token"[^>]*value="([^"]+)"',
            dashboard.get_data(as_text=True),
        )
        assert token_match is not None

        response = client.post(
            "/auth/logout",
            data={"csrf_token": token_match.group(1)},
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/auth/login")
        assert client.get("/alerts/").status_code == 302


def test_chat_answers_from_local_data_when_ollama_is_unavailable():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()
        user = User(
            full_name="Chat User",
            username="chatuser",
            email="chatuser@example.com",
            role="researcher",
        )
        user.set_password("secret123")
        river = River(name="Chat River", municipality="Norzagaray")
        db.session.add_all([user, river])
        db.session.commit()
        db.session.add_all([
            Reading(river_id=river.id, turbidity_ntu=4, tds_ppm=200),
            Reading(river_id=river.id, turbidity_ntu=8, tds_ppm=400),
        ])
        db.session.commit()

        app.config["OLLAMA_BASE_URL"] = "http://127.0.0.1:1"
        client = app.test_client()
        with client.session_transaction() as session:
            session["_user_id"] = str(user.id)
            session["_fresh"] = True

        page = client.get("/chat/")
        assert page.status_code == 200
        page_html = page.get_data(as_text=True)
        token_match = re.search(
            r'id="chat-csrf-token" value="([^"]+)"', page_html,
        )
        assert token_match is not None

        response = client.post(
            "/chat/api/message",
            json={"message": "What is the average turbidity?", "history": []},
            headers={"X-CSRFToken": token_match.group(1)},
        )

        assert response.status_code == 200
        result = response.get_json()
        assert result["success"] is True
        assert result["mode"] == "local-data"
        assert "average is 6" in result["answer"]
        assert "2 readings" in result["answer"]


def test_chat_uses_configured_online_provider_for_free_form_questions(monkeypatch):
    app = create_app()
    captured = {}

    class MockResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"Online reply from AquaSense."}}]}'

    def mock_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return MockResponse()

    monkeypatch.setattr(chat_service, "urlopen", mock_urlopen)

    with app.app_context():
        db.drop_all()
        db.create_all()
        app.config["GROQ_API_KEY"] = "test-api-key"
        app.config["GROQ_MODEL"] = "test-fast-model"
        app.config["GROQ_API_URL"] = "https://api.groq.test/openai/v1/chat/completions"
        river = River(name="Online Test River", municipality="Norzagaray")
        db.session.add(river)
        db.session.commit()
        db.session.add(Reading(river_id=river.id, turbidity_ntu=6))
        db.session.commit()

        result = chat_service.answer_local_question(
            "Why is regular water-quality monitoring important?"
        )

    assert result["mode"] == "online-model"
    assert result["answer"] == "Online reply from AquaSense."
    assert result["model_status"]["provider"] == "online"
    assert captured["url"] == "https://api.groq.test/openai/v1/chat/completions"
    assert captured["authorization"] == "Bearer test-api-key"
    assert captured["payload"]["model"] == "test-fast-model"
    assert "Online Test River" in captured["payload"]["messages"][0]["content"]
    assert captured["timeout"] == 20


def test_chat_returns_prompt_specific_reply_without_ai_provider():
    app = create_app()

    with app.app_context():
        db.drop_all()
        db.create_all()
        app.config["GROQ_API_KEY"] = ""
        app.config["OLLAMA_BASE_URL"] = "http://127.0.0.1:1"
        river = River(name="Fallback Test River", municipality="Norzagaray")
        db.session.add(river)
        db.session.commit()
        db.session.add(Reading(river_id=river.id, turbidity_ntu=7))
        db.session.commit()

        prompt = "Can you explain how rainfall affects river monitoring?"
        result = chat_service.answer_local_question(prompt)

    assert result["mode"] == "local-data"
    assert prompt in result["answer"]
    assert "1 readings across 1 rivers" in result["answer"]
    assert "GROQ_API_KEY" in result["answer"]


def test_chat_refuses_remote_ollama_url():
    app = create_app()

    with app.app_context():
        app.config["OLLAMA_BASE_URL"] = "http://example.com:11434"
        status = local_model_status()

        assert status["available"] is False
        assert "loopback" in status["message"]


def test_app_factory_can_skip_schema_creation_for_serverless_runtime():
    class ServerlessConfig:
        SECRET_KEY = "serverless-test-key"
        SQLALCHEMY_DATABASE_URI = "sqlite://"
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        SQLALCHEMY_ENGINE_OPTIONS = {}
        WTF_CSRF_ENABLED = False
        AUTO_CREATE_SCHEMA = False

    app = create_app(ServerlessConfig)

    with app.app_context():
        assert db.inspect(db.engine).get_table_names() == []


def test_vercel_instance_path_uses_writable_temp_directory(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")

    app = create_app()

    assert app.instance_path == os.path.join(
        tempfile.gettempdir(), "aquasense-instance"
    )


def test_chat_uses_exact_local_calculation_for_average_even_with_ai_available(monkeypatch):
    app = create_app()

    def fail_if_model_is_called(*args, **kwargs):
        raise AssertionError("Exact numeric questions should not be delegated to the LLM.")

    monkeypatch.setattr(chat_service, "local_model_status", lambda: {
        "available": True,
        "model": "qwen2.5:3b",
        "models": ["qwen2.5:3b"],
        "message": "Local model ready",
    })
    monkeypatch.setattr(chat_service, "urlopen", fail_if_model_is_called)

    with app.app_context():
        db.drop_all()
        db.create_all()
        river = River(name="Exact Answer River", municipality="Norzagaray")
        db.session.add(river)
        db.session.commit()
        db.session.add_all([
            Reading(river_id=river.id, turbidity_ntu=4),
            Reading(river_id=river.id, turbidity_ntu=8),
        ])
        db.session.commit()

        result = chat_service.answer_local_question(
            "What is the average turbidity across all readings?"
        )

        assert result["mode"] == "local-data"
        assert "average is 6" in result["answer"]
        assert "all 2 readings" in result["answer"]

        latest = chat_service.answer_local_question(
            "What is the latest turbidity?"
        )
        assert latest["mode"] == "local-data"
        assert "latest saved Turbidity value is 8" in latest["answer"]
