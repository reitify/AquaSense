
from datetime import datetime, timezone

from app.extensions import db


class Sensor(db.Model):
    __tablename__ = "sensors"

    id = db.Column(db.Integer, primary_key=True)

    device_id = db.Column(
        db.String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    name = db.Column(db.String(120), nullable=False)

    river_id = db.Column(
        db.Integer,
        db.ForeignKey("rivers.id"),
        nullable=False,
        index=True,
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    last_seen_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    api_key_hash = db.Column(db.String(255), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    river = db.relationship(
        "River",
        backref=db.backref("sensors", lazy=True),
    )

    def __repr__(self):
        return f"<Sensor {self.device_id}>"
