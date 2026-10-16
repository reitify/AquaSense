
from datetime import datetime, timezone

from app.extensions import db


class ThresholdRule(db.Model):
    __tablename__ = "threshold_rules"

    id = db.Column(db.Integer, primary_key=True)

    parameter = db.Column(
        db.String(50),
        nullable=False,
        index=True,
    )

    rule_name = db.Column(
        db.String(100),
        nullable=False,
    )

    min_value = db.Column(db.Float, nullable=True)
    max_value = db.Column(db.Float, nullable=True)

    status = db.Column(
        db.String(30),
        nullable=False,
    )

    description = db.Column(db.Text, nullable=True)

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

    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return (
            f"<ThresholdRule {self.parameter}: "
            f"{self.rule_name}>"
        )

