from functools import wraps
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import db
from models import User, Project, Application, Match, TargetRole

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")

VALID_ROLES = ("student", "admin")
VALID_PROJECT_STATUSES = ("open", "closed")


def admin_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        if not user or user.role != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return fn(*args, **kwargs)
    return wrapper


@admin_bp.route("/bootstrap", methods=["POST"])
@jwt_required()
def bootstrap_admin():
    if User.query.filter_by(role="admin").count() > 0:
        return jsonify({"error": "An admin already exists. Ask them to promote you instead."}), 403

    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    user.role = "admin"
    db.session.commit()
    return jsonify({"message": f"{user.name} is now an admin", "user": user.to_dict()}), 200


@admin_bp.route("/stats", methods=["GET"])
@admin_required
def platform_stats():
    return jsonify({
        "total_students": User.query.filter_by(role="student").count(),
        "total_admins": User.query.filter_by(role="admin").count(),
        "total_projects": Project.query.count(),
        "open_projects": Project.query.filter_by(status="open").count(),
        "closed_projects": Project.query.filter_by(status="closed").count(),
        "total_applications": Application.query.count(),
        "pending_applications": Application.query.filter_by(status="pending").count(),
        "accepted_applications": Application.query.filter_by(status="accepted").count(),
        "total_matches_computed": Match.query.count(),
        "total_target_roles": TargetRole.query.count(),
    }), 200


@admin_bp.route("/users", methods=["GET"])
@admin_required
def list_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({"users": [u.to_dict() for u in users]}), 200


@admin_bp.route("/users/<int:target_user_id>/role", methods=["PUT"])
@admin_required
def update_user_role(target_user_id):
    user = User.query.get(target_user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    new_role = (data.get("role") or "").lower()
    if new_role not in VALID_ROLES:
        return jsonify({"error": f"role must be one of {VALID_ROLES}"}), 400

    user.role = new_role
    db.session.commit()
    return jsonify(user.to_dict()), 200


@admin_bp.route("/projects", methods=["GET"])
@admin_required
def list_all_projects():
    from routes.matching_routes import serialize_project
    projects = Project.query.order_by(Project.created_at.desc()).all()
    return jsonify({"projects": [serialize_project(p) for p in projects]}), 200


@admin_bp.route("/projects/<int:project_id>/status", methods=["PUT"])
@admin_required
def update_project_status(project_id):
    project = Project.query.get(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    data = request.get_json(silent=True) or {}
    new_status = (data.get("status") or "").lower()
    if new_status not in VALID_PROJECT_STATUSES:
        return jsonify({"error": f"status must be one of {VALID_PROJECT_STATUSES}"}), 400

    project.status = new_status
    db.session.commit()

    from routes.matching_routes import serialize_project
    return jsonify(serialize_project(project)), 200
