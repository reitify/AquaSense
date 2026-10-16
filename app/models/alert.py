
from datetime import datetime, timezone

from app.extensions import db


class Alert(db.Model):
    __tablename__ = "alerts"

    id = db.Column(db.Integer, primary_key=True)

    river_id = db.Column(
        db.Integer,
        db.ForeignKey("rivers.id"),
        nullable=False,
        index=True,
    )

    reading_id = db.Column(
        db.Integer,
        db.ForeignKey("readings.id"),
        nullable=True,
        index=True,
    )

    message = db.Column(db.Text, nullable=False)

    status = db.Column(
        db.String(30),
        nullable=False,
        default="open",
        index=True,
    )

    severity = db.Column(
        db.String(20),
        nullable=False,
        default="warning",
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    resolved_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    river = db.relationship(
        "River",
        backref=db.backref("alerts", lazy=True),
    )

    reading = db.relationship(
        "Reading",
        backref=db.backref("alerts", lazy=True),
    )

    def __repr__(self):
        return f"<Alert {self.id}: {self.status}>"
