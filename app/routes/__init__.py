
"""Route blueprint registration for AquaSense."""

from app.routes.admin import admin_bp
from app.routes.alerts import alerts_bp
from app.routes.analytics import analytics_bp
from app.routes.assessments import assessments_bp
from app.routes.auth import auth_bp
from app.routes.chat import chat_bp
from app.routes.ingestion import ingestion_bp
from app.routes.main import main_bp
from app.routes.readings import readings_bp
from app.routes.reports import reports_bp
from app.routes.sensors import sensors_bp
from app.routes.stations import stations_bp


def register_blueprints(app):
    """Register all application route blueprints."""
    blueprints = (
        admin_bp,
        alerts_bp,
        analytics_bp,
        assessments_bp,
        auth_bp,
        chat_bp,
        ingestion_bp,
        main_bp,
        readings_bp,
        reports_bp,
        sensors_bp,
        stations_bp,
    )

    for blueprint in blueprints:
        app.register_blueprint(blueprint)
