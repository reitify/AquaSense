
from datetime import datetime, timezone

from app.extensions import db


class Reading(db.Model):
    __tablename__ = "readings"

    id = db.Column(db.Integer, primary_key=True)

    river_id = db.Column(
        db.Integer,
        db.ForeignKey("rivers.id"),
        nullable=False,
        index=True,
    )

    turbidity_ntu = db.Column(db.Float, nullable=True)
    tss = db.Column(db.Float, nullable=True)
    particle_level = db.Column(db.Float, nullable=True)
    clarity = db.Column(db.Float, nullable=True)
    ph_value = db.Column(db.Float, nullable=True)
    acidity = db.Column(db.Float, nullable=True)
    alkalinity = db.Column(db.Float, nullable=True)
    ph_stability = db.Column(db.Float, nullable=True)
    temperature_c = db.Column(db.Float, nullable=True)
    ambient_temperature = db.Column(db.Float, nullable=True)
    change_rate = db.Column(db.Float, nullable=True)
    thermal_anomaly = db.Column(db.Float, nullable=True)
    tds_ppm = db.Column(db.Float, nullable=True)
    conductivity = db.Column(db.Float, nullable=True)
    ionic_content = db.Column(db.Float, nullable=True)
    salinity = db.Column(db.Float, nullable=True)

    water_quality_index = db.Column(db.Float, nullable=True)
    quality_status = db.Column(db.String(50), nullable=True)

    recorded_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    source = db.Column(
        db.String(30),
        nullable=False,
        default="manual",
    )

    device_id = db.Column(db.String(100), nullable=True)

    river = db.relationship(
        "River",
        backref=db.backref("readings", lazy="select"),
    )

    def __repr__(self):
        return (
            f"<Reading river_id={self.river_id} "
            f"turbidity={self.turbidity_ntu}>"
        )
