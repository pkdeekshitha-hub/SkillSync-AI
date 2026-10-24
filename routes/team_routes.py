from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import db
from models import (
    User, StudentProfile, Skill, StudentSkill, Interest, StudentInterest,
    Project, ProjectSkill, Match, Application, Team, TeamMember, Notification,
)
from routes.matching_routes import compute_score, serialize_project

team_bp = Blueprint("team", __name__, url_prefix="/api")

VALID_STATUSES = ("pending", "accepted", "rejected")


def serialize_application(app_row):
    user = User.query.get(app_row.user_id)
    return {
        "id": app_row.id,
        "project_id": app_row.project_id,
        "user_id": app_row.user_id,
        "name": user.name if user else None,
        "email": user.email if user else None,
        "status": app_row.status,
        "applied_at": app_row.applied_at.isoformat() if app_row.applied_at else None,
    }


@team_bp.route("/projects/<int:project_id>/apply", methods=["POST"])
@jwt_required()
def apply_to_project(project_id):
    user_id = int(get_jwt_identity())
    project = Project.query.get(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    if project.creator_id == user_id:
        return jsonify({"error": "You can't apply to your own project"}), 400

    if project.status != "open":
        return jsonify({"error": "This project is not accepting applications"}), 400

    existing = Application.query.filter_by(project_id=project_id, user_id=user_id).first()
    if existing:
        return jsonify({"error": f"You already applied (status: {existing.status})"}), 409

    application = Application(project_id=project_id, user_id=user_id, status="pending")
    db.session.add(application)
    db.session.commit()

    return jsonify(serialize_application(application)), 201


@team_bp.route("/projects/<int:project_id>/applications", methods=["GET"])
@jwt_required()
def list_applications(project_id):
    user_id = int(get_jwt_identity())
    project = Project.query.get(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    if project.creator_id != user_id:
        return jsonify({"error": "Only the project creator can view applications"}), 403

    applications = Application.query.filter_by(project_id=project_id).all()
    return jsonify({"applications": [serialize_application(a) for a in applications]}), 200


@team_bp.route("/projects/<int:project_id>/applications/<int:applicant_user_id>", methods=["PUT"])
@jwt_required()
def update_application(project_id, applicant_user_id):
    user_id = int(get_jwt_identity())
    project = Project.query.get(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    if project.creator_id != user_id:
        return jsonify({"error": "Only the project creator can update applications"}), 403

    application = Application.query.filter_by(project_id=project_id, user_id=applicant_user_id).first()
    if not application:
        return jsonify({"error": "Application not found"}), 404

    data = request.get_json(silent=True) or {}
    new_status = (data.get("status") or "").lower()
    if new_status not in VALID_STATUSES:
        return jsonify({"error": f"status must be one of {VALID_STATUSES}"}), 400

    application.status = new_status
    db.session.commit()

    return jsonify(serialize_application(application)), 200


@team_bp.route("/projects/<int:project_id>/suggested-team", methods=["GET"])
@jwt_required()
def suggested_team(project_id):
    project = Project.query.get(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    required_skill_ids = {
        row.skill_id for row in ProjectSkill.query.filter_by(project_id=project_id).all()
    }
    candidates = User.query.filter(User.id != project.creator_id, User.role == "student").all()

    ranked = []
    for student in candidates:
        profile = StudentProfile.query.get(student.id)
        availability_hours = profile.availability_hours if profile else 0

        student_skill_ids = {
            row.skill_id for row in StudentSkill.query.filter_by(user_id=student.id).all()
        }
        student_interest_ids = {
            row.interest_id for row in StudentInterest.query.filter_by(user_id=student.id).all()
        }

        breakdown = compute_score(
            student_skill_ids, student_interest_ids, availability_hours,
            required_skill_ids, project.interest_id, project.expected_hours_per_week,
        )
        ranked.append({"user_id": student.id, "name": student.name, "email": student.email, **breakdown})

    ranked.sort(key=lambda r: r["score"], reverse=True)
    top_team = ranked[: project.team_size]

    return jsonify({
        "project": serialize_project(project),
        "team_size_needed": project.team_size,
        "suggested_team": top_team,
    }), 200


# ============================================================
# Collaborative Teams Formation & Management
# ============================================================

def serialize_team(team):
    members_data = []
    members = TeamMember.query.filter_by(team_id=team.id).order_by(TeamMember.joined_at.asc()).all()
    for m in members:
        user = User.query.get(m.user_id)
        profile = StudentProfile.query.get(m.user_id)
        members_data.append({
            "member_id": m.id,
            "user_id": m.user_id,
            "name": user.name if user else "Unknown",
            "role": m.role,
            "department": profile.department if profile and profile.department else "Computer Science",
            "college": user.college if user else None,
            "joined_at": m.joined_at.isoformat() if m.joined_at else None,
            "is_creator": (m.user_id == team.created_by),
        })

    creator = User.query.get(team.created_by)
    return {
        "id": team.id,
        "name": team.name,
        "event_name": team.event_name,
        "project_idea": team.project_idea,
        "created_by": team.created_by,
        "creator_name": creator.name if creator else "Unknown",
        "created_at": team.created_at.isoformat() if team.created_at else None,
        "members_count": len(members_data),
        "members": members_data,
    }


@team_bp.route("/teams", methods=["POST"])
@jwt_required()
def create_team():
    user_id = int(get_jwt_identity())
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Team name is required"}), 400

    event_name = (data.get("event_name") or "AI Hackathon").strip()
    project_idea = (data.get("project_idea") or "").strip()
    creator_role = (data.get("creator_role") or "Team Lead").strip()

    team = Team(
        name=name,
        event_name=event_name,
        project_idea=project_idea,
        created_by=user_id,
    )
    db.session.add(team)
    db.session.commit()

    # Add creator as initial member
    creator_member = TeamMember(
        team_id=team.id,
        user_id=user_id,
        role=creator_role,
    )
    db.session.add(creator_member)

    # Add any invited members passed in
    invited_members = data.get("members") or []
    for m in invited_members:
        member_id = int(m.get("user_id") or 0)
        role = (m.get("role") or "Member").strip()
        if member_id and member_id != user_id:
            existing = TeamMember.query.filter_by(team_id=team.id, user_id=member_id).first()
            if not existing:
                db.session.add(TeamMember(
                    team_id=team.id,
                    user_id=member_id,
                    role=role,
                ))
                # Notify the invited member
                db.session.add(Notification(
                    user_id=member_id,
                    title="🚀 Team Invitation",
                    message=f"{current_user.name} added you to '{team.name}' as {role} for {event_name}!",
                    notif_type="team",
                    link_action="teams",
                ))

    db.session.commit()
    return jsonify(serialize_team(team)), 201


@team_bp.route("/teams", methods=["GET"])
@jwt_required()
def list_my_teams():
    user_id = int(get_jwt_identity())

    # Find all teams where user is creator or member
    member_team_ids = [m.team_id for m in TeamMember.query.filter_by(user_id=user_id).all()]
    created_team_ids = [t.id for t in Team.query.filter_by(created_by=user_id).all()]
    all_team_ids = sorted(list(set(member_team_ids + created_team_ids)), reverse=True)

    teams = Team.query.filter(Team.id.in_(all_team_ids)).all() if all_team_ids else []
    teams.sort(key=lambda t: t.created_at, reverse=True)

    return jsonify({"teams": [serialize_team(t) for t in teams]}), 200


@team_bp.route("/teams/<int:team_id>", methods=["GET"])
@jwt_required()
def get_team_details(team_id):
    team = Team.query.get(team_id)
    if not team:
        return jsonify({"error": "Team not found"}), 404
    return jsonify(serialize_team(team)), 200


@team_bp.route("/teams/<int:team_id>/invite", methods=["POST"])
@jwt_required()
def invite_to_team(team_id):
    user_id = int(get_jwt_identity())
    current_user = User.query.get(user_id)
    team = Team.query.get(team_id)
    if not team:
        return jsonify({"error": "Team not found"}), 404

    # Check if user is a member/creator of the team
    is_member = TeamMember.query.filter_by(team_id=team_id, user_id=user_id).first()
    if not is_member and team.created_by != user_id:
        return jsonify({"error": "Only team members can invite teammates"}), 403

    data = request.get_json(silent=True) or {}
    target_user_id = int(data.get("user_id") or 0)
    role = (data.get("role") or "Member").strip()

    if not target_user_id:
        return jsonify({"error": "user_id is required"}), 400

    target_user = User.query.get(target_user_id)
    if not target_user:
        return jsonify({"error": "Student not found"}), 404

    existing = TeamMember.query.filter_by(team_id=team_id, user_id=target_user_id).first()
    if existing:
        return jsonify({"error": f"{target_user.name} is already a member of this team"}), 409

    new_member = TeamMember(
        team_id=team_id,
        user_id=target_user_id,
        role=role,
    )
    db.session.add(new_member)

    # Notify invited student
    db.session.add(Notification(
        user_id=target_user_id,
        title="🚀 Added to Team",
        message=f"{current_user.name} added you to '{team.name}' as {role} for {team.event_name}!",
        notif_type="team",
        link_action="teams",
    ))

    db.session.commit()
    return jsonify(serialize_team(team)), 200


@team_bp.route("/teams/<int:team_id>/members/<int:member_user_id>", methods=["PUT"])
@jwt_required()
def update_team_member_role(team_id, member_user_id):
    user_id = int(get_jwt_identity())
    team = Team.query.get(team_id)
    if not team:
        return jsonify({"error": "Team not found"}), 404

    # Only creator or the member themselves can update role
    if team.created_by != user_id and user_id != member_user_id:
        return jsonify({"error": "Only team creator or the member can update roles"}), 403

    member = TeamMember.query.filter_by(team_id=team_id, user_id=member_user_id).first()
    if not member:
        return jsonify({"error": "Member not found in this team"}), 404

    data = request.get_json(silent=True) or {}
    new_role = (data.get("role") or "").strip()
    if not new_role:
        return jsonify({"error": "role cannot be empty"}), 400

    member.role = new_role
    db.session.commit()

    return jsonify(serialize_team(team)), 200


@team_bp.route("/teams/<int:team_id>/members/<int:member_user_id>", methods=["DELETE"])
@jwt_required()
def remove_team_member(team_id, member_user_id):
    user_id = int(get_jwt_identity())
    team = Team.query.get(team_id)
    if not team:
        return jsonify({"error": "Team not found"}), 404

    # Only creator or the member themselves (leaving)
    if team.created_by != user_id and user_id != member_user_id:
        return jsonify({"error": "Permission denied"}), 403

    member = TeamMember.query.filter_by(team_id=team_id, user_id=member_user_id).first()
    if not member:
        return jsonify({"error": "Member not found in team"}), 404

    db.session.delete(member)
    db.session.commit()

    return jsonify(serialize_team(team)), 200

