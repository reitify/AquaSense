from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from app.extensions import csrf

from app.services.chat_service import answer_local_question, chat_model_status

chat_bp = Blueprint("chat", __name__, url_prefix="/chat")


@chat_bp.route("/")
@login_required
def index():
    """Render the private AquaSense assistant chat."""
    return render_template("chat.html", model_status=chat_model_status())


@chat_bp.route("/api/status")
@login_required
def status():
    """Report the preferred chat provider without exposing any secrets."""
    return jsonify(chat_model_status()), 200


@chat_bp.route("/api/message", methods=["POST"])
@login_required
@csrf.exempt
def message():
    """Answer a chat question using only local AquaSense data and models."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "A JSON message is required."}), 400

    question = payload.get("message")
    if not isinstance(question, str) or not question.strip():
        return jsonify({"success": False, "error": "Enter a question first."}), 400
    question = question.strip()
    if len(question) > 2000:
        return jsonify({"success": False, "error": "Questions must be 2,000 characters or fewer."}), 413

    conversation = payload.get("history", [])
    if not isinstance(conversation, list):
        conversation = []

    try:
        result = answer_local_question(question, conversation)
    except Exception:
        return jsonify({
            "success": False,
            "error": "AquaSense could not read the local dataset. Please try again.",
        }), 500

    return jsonify({
        "success": True,
        **result,
    }), 200