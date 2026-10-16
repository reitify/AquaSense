
import os
import tempfile
import uuid

from flask import Flask

from app.config import Config
from app.extensions import csrf, db, login_manager, migrate
from app.models.user import User
from app.routes import register_blueprints
from app.schema import ensure_sensor_reading_columns

__all__ = [
    "create_app",
    "User",
]


def _ensure_default_admin_user():
    username = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
    password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin")
    email = os.getenv("DEFAULT_ADMIN_EMAIL", f"{username}@local.local")

    admin_user = User.query.filter_by(username=username).first()
    if admin_user is None:
        admin_user = User(
            full_name="System Administrator",
            username=username,
            email=email,
            role="admin",
            is_active=True,
        )
        admin_user.set_password(password)
        db.session.add(admin_user)
    else:
        admin_user.role = "admin"
        admin_user.is_active = True
        if not admin_user.check_password(password):
            admin_user.set_password(password)

    db.session.commit()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if os.getenv("PYTEST_CURRENT_TEST"):
        app.config["TESTING"] = True
        app.config["SQLALCHEMY_DATABASE_URI"] = (
            f"sqlite:///{tempfile.gettempdir()}/aquasense_test_{uuid.uuid4().hex}.db"
        )
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {}

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    with app.app_context():
        if app.config.get("AUTO_CREATE_SCHEMA", True):
            db.create_all()
            ensure_sensor_reading_columns()
            _ensure_default_admin_user()

    register_blueprints(app)
    return app
