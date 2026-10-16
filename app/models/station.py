
from datetime import datetime, timezone

from app.extensions import db


class Station(db.Model):
    __tablename__ = "stations"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(120),
        nullable=False,
    )

    station_code = db.Column(
        db.String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    river_id = db.Column(
        db.Integer,
        db.ForeignKey("rivers.id"),
        nullable=False,
        index=True,
    )

    description = db.Column(db.Text, nullable=True)

    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    river = db.relationship(
        "River",
        backref=db.backref("stations", lazy=True),
    )

    def __repr__(self):
        return f"<Station {self.station_code}>"
