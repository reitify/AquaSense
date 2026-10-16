
from flask import Blueprint, jsonify, render_template
from flask_login import login_required

from app.models.assessment import Assessment

assessments_bp = Blueprint(
    "assessments",
    __name__,
    url_prefix="/assessments",
)


@assessments_bp.route("/")
@login_required
def index():
    """Display water-quality assessments."""
    return render_template("assessments.html")


@assessments_bp.route("/api")
@login_required
def get_assessments():
    """Return recent assessments as JSON."""
    assessments = (
        Assessment.query
        .order_by(Assessment.id.desc())
        .limit(100)
        .all()
    )

    results = []

    for assessment in assessments:
        results.append({
            "id": assessment.id,
            "river_id": getattr(assessment, "river_id", None),
            "status": getattr(assessment, "status", None),
            "created_at": (
                assessment.created_at.isoformat()
                if getattr(assessment, "created_at", None)
                else None
            ),
        })

    return jsonify({
        "success": True,
        "count": len(results),
        "assessments": results,
    }), 200
