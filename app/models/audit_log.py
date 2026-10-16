
from datetime import datetime, timezone

from app.extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    action = db.Column(
        db.String(100),
        nullable=False,
    )

    entity_type = db.Column(
        db.String(100),
        nullable=True,
    )

    entity_id = db.Column(
        db.Integer,
        nullable=True,
    )

    details = db.Column(db.Text, nullable=True)

    ip_address = db.Column(db.String(45), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    user = db.relationship(
        "User",
        backref=db.backref("audit_logs", lazy=True),
    )

    def __repr__(self):
        return f"<AuditLog {self.id}: {self.action}>"
