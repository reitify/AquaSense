
from flask import Blueprint, abort, jsonify, render_template
from flask_login import current_user, login_required

from app.models.user import User

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def require_admin():
    """Allow access only to authenticated administrators."""
    if not current_user.is_authenticated:
        abort(403)

    if getattr(current_user, "role", None) != "admin":
        abort(403)


@admin_bp.route("/")
@login_required
def index():
    """Display the administration page."""
    require_admin()
    return render_template("admin.html")


@admin_bp.route("/api/users")
@login_required
def get_users():
    """Return basic account information for administrators."""
    require_admin()

    users = User.query.order_by(User.id.asc()).limit(500).all()

    return jsonify({
        "success": True,
        "count": len(users),
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
            }
            for user in users
        ],
    }), 200
