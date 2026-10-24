from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from models import Project, Application
from routes.matching_routes import serialize_project
from routes.team_routes import serialize_application

finder_bp = Blueprint("finder", __name__, url_prefix="/api")


@finder_bp.route("/my-projects", methods=["GET"])
@jwt_required()
def my_projects():
    user_id = int(get_jwt_identity())
    projects = Project.query.filter_by(creator_id=user_id).order_by(Project.created_at.desc()).all()
    return jsonify({"projects": [serialize_project(p) for p in projects]}), 200


@finder_bp.route("/my-applications", methods=["GET"])
@jwt_required()
def my_applications():
    user_id = int(get_jwt_identity())
    applications = Application.query.filter_by(user_id=user_id).order_by(Application.applied_at.desc()).all()

    results = []
    for app_row in applications:
        project = Project.query.get(app_row.project_id)
        entry = serialize_application(app_row)
        entry["project_title"] = project.title if project else None
        entry["project_status"] = project.status if project else None
        results.append(entry)

    return jsonify({"applications": results}), 200
