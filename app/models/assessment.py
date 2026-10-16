
from datetime import datetime, timezone

from app.extensions import db


class Assessment(db.Model):
    __tablename__ = "assessments"

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
        nullable=False,
        index=True,
    )

    status = db.Column(
        db.String(30),
        nullable=False,
        default="Unknown",
    )

    remarks = db.Column(db.Text, nullable=True)

    assessed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    river = db.relationship(
        "River",
        backref=db.backref("assessments", lazy=True),
    )

    reading = db.relationship(
        "Reading",
        backref=db.backref("assessments", lazy=True),
    )

    def __repr__(self):
        return f"<Assessment {self.id}: {self.status}>"
