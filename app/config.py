
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL, make_url

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    IS_VERCEL = bool(os.getenv("VERCEL"))
    SECRET_KEY = os.getenv("SECRET_KEY") or "dev-secret-key"

    if SECRET_KEY.startswith("replace_with_"):
        SECRET_KEY = "dev-secret-key"

    if IS_VERCEL and SECRET_KEY == "dev-secret-key":
        raise RuntimeError("Set a strong SECRET_KEY in Vercel project environment variables.")

    DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv(
        "SQLALCHEMY_DATABASE_URI"
    )

    if IS_VERCEL and not DATABASE_URL:
        raise RuntimeError(
            "Set DATABASE_URL to the Supabase PostgreSQL transaction-pooler URL."
        )

    if DATABASE_URL:
        database_url = make_url(DATABASE_URL)
        if IS_VERCEL and not database_url.drivername.startswith("postgres"):
            raise RuntimeError(
                "DATABASE_URL must use Supabase PostgreSQL on Vercel."
            )
        if database_url.drivername in {"postgres", "postgresql"}:
            query = dict(database_url.query)
            query.setdefault("sslmode", "require")
            SQLALCHEMY_DATABASE_URI = database_url.set(
                drivername="postgresql+psycopg",
                query=query,
            )
        else:
            SQLALCHEMY_DATABASE_URI = database_url
    else:
        use_sqlite = (
            os.getenv("USE_SQLITE", "1").lower() in {"1", "true", "yes"}
            or not os.getenv("DB_HOST")
        )

        if use_sqlite:
            SQLALCHEMY_DATABASE_URI = "sqlite:///aquasense.db"
        else:
            SQLALCHEMY_DATABASE_URI = URL.create(
                drivername="mysql+pymysql",
                username=os.getenv("DB_USER", "aquasense_user"),
                password=os.getenv("DB_PASSWORD", ""),
                host=os.getenv("DB_HOST", "127.0.0.1"),
                port=int(os.getenv("DB_PORT", "3306")),
                database=os.getenv("DB_NAME", "aquasense_db"),
                query={"charset": "utf8mb4"},
            )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    database_url = make_url(SQLALCHEMY_DATABASE_URI)
    if database_url.drivername.startswith("sqlite"):
        SQLALCHEMY_ENGINE_OPTIONS = {}
    elif database_url.drivername.startswith("postgresql"):
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_pre_ping": True,
            "pool_size": 1 if IS_VERCEL else 5,
            "max_overflow": 0 if IS_VERCEL else 10,
            "pool_recycle": 300,
        }
        if IS_VERCEL and database_url.port == 6543:
            SQLALCHEMY_ENGINE_OPTIONS["connect_args"] = {
                "prepare_threshold": None,
            }
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_pre_ping": True,
            "pool_recycle": 1800,
        }

    AUTO_CREATE_SCHEMA = os.getenv(
        "AUTO_CREATE_SCHEMA",
        "0" if IS_VERCEL else "1",
    ).lower() in {"1", "true", "yes"}

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv(
        "COOKIE_SECURE",
        "1" if IS_VERCEL else "0",
    ) == "1"

    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600

    APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Manila")

    OLLAMA_BASE_URL = os.getenv(
        "OLLAMA_BASE_URL",
        "http://127.0.0.1:11434",
    )
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_API_URL = os.getenv(
        "GROQ_API_URL",
        "https://api.groq.com/openai/v1/chat/completions",
    )
    GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    GROQ_TIMEOUT_SECONDS = float(os.getenv("GROQ_TIMEOUT_SECONDS", "20"))

    SENSOR_OFFLINE_TIMEOUT_MINUTES = int(
        os.getenv("SENSOR_OFFLINE_TIMEOUT_MINUTES", "10")
    )

    DEMO_MODE = os.getenv("DEMO_MODE", "0").lower() in {
        "1", "true", "yes"
    }

    DEBUG = os.getenv("FLASK_DEBUG", "0").lower() in {
        "1", "true", "yes"
    }

    TEMPLATES_AUTO_RELOAD = os.getenv(
        "TEMPLATES_AUTO_RELOAD",
        "0" if IS_VERCEL else "1",
    ).lower() in {"1", "true", "yes"}
