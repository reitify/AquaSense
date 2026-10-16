
from datetime import datetime, timezone

from app.extensions import db


class River(db.Model):
    __tablename__ = "rivers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    location_description = db.Column(db.String(255), nullable=True)
    barangay = db.Column(db.String(100), nullable=True)
    municipality = db.Column(
        db.String(100),
        nullable=False,
        default="Norzagaray",
    )

    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<River {self.name}>"
