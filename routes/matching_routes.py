from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import db
from models import (
    User, StudentProfile, Skill, StudentSkill, Interest, StudentInterest,
    Project, ProjectSkill, Match,
)

matching_bp = Blueprint("matching", __name__, url_prefix="/api")

SKILL_WEIGHT = 0.5
INTEREST_WEIGHT = 0.3
AVAILABILITY_WEIGHT = 0.2


def serialize_project(project):
    required_skills = (
        db.session.query(Skill)
        .join(ProjectSkill, ProjectSkill.skill_id == Skill.id)
        .filter(ProjectSkill.project_id == project.id)
        .all()
    )
    interest = Interest.query.get(project.interest_id) if project.interest_id else None
    return {
        "id": project.id,
        "creator_id": project.creator_id,
        "title": project.title,
        "description": project.description,
        "difficulty": project.difficulty,
        "team_size": project.team_size,
        "status": project.status,
        "interest": interest.name if interest else None,
        "expected_hours_per_week": project.expected_hours_per_week,
        "required_skills": [s.name for s in required_skills],
        "created_at": project.created_at.isoformat() if project.created_at else None,
    }


@matching_bp.route("/projects", methods=["POST"])
@jwt_required()
def create_project():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    skill_names = data.get("skill_names") or []
    if not isinstance(skill_names, list) or not skill_names:
        return jsonify({"error": "skill_names must be a non-empty list"}), 400

    difficulty = (data.get("difficulty") or "medium").lower()
    if difficulty not in ("easy", "medium", "hard"):
        return jsonify({"error": "difficulty must be easy, medium, or hard"}), 400

    try:
        team_size = int(data.get("team_size", 1))
        expected_hours = int(data.get("expected_hours_per_week", 5))
    except (TypeError, ValueError):
        return jsonify({"error": "team_size and expected_hours_per_week must be numbers"}), 400

    interest_id = None
    interest_name = (data.get("interest_name") or "").strip()
    if interest_name:
        interest = Interest.query.filter(db.func.lower(Interest.name) == interest_name.lower()).first()
        if not interest:
            interest = Interest(name=interest_name)
            db.session.add(interest)
            db.session.commit()
        interest_id = interest.id

    project = Project(
        creator_id=user_id,
        title=title,
        description=(data.get("description") or "").strip(),
        difficulty=difficulty,
        team_size=team_size,
        expected_hours_per_week=expected_hours,
        interest_id=interest_id,
    )
    db.session.add(project)
    db.session.commit()

    for raw_name in skill_names:
        name = (raw_name or "").strip()
        if not name:
            continue
        skill = Skill.query.filter(db.func.lower(Skill.name) == name.lower()).first()
        if not skill:
            skill = Skill(name=name)
            db.session.add(skill)
            db.session.commit()
        db.session.add(ProjectSkill(project_id=project.id, skill_id=skill.id))
    db.session.commit()

    return jsonify(serialize_project(project)), 201


@matching_bp.route("/projects", methods=["GET"])
def list_projects():
    query = Project.query.filter_by(status="open")

    difficulty = request.args.get("difficulty")
    if difficulty:
        query = query.filter(Project.difficulty == difficulty.lower())

    interest_name = request.args.get("interest")
    if interest_name:
        interest = Interest.query.filter(db.func.lower(Interest.name) == interest_name.lower()).first()
        query = query.filter(Project.interest_id == (interest.id if interest else -1))

    search = request.args.get("search")
    if search:
        query = query.filter(Project.title.ilike(f"%{search}%"))

    projects = query.order_by(Project.created_at.desc()).all()

    skill_name = request.args.get("skill")
    if skill_name:
        skill = Skill.query.filter(db.func.lower(Skill.name) == skill_name.lower()).first()
        skill_id = skill.id if skill else -1
        projects = [
            p for p in projects
            if skill_id in {row.skill_id for row in ProjectSkill.query.filter_by(project_id=p.id).all()}
        ]

    return jsonify({"projects": [serialize_project(p) for p in projects]}), 200


@matching_bp.route("/projects/<int:project_id>", methods=["GET"])
def get_project(project_id):
    project = Project.query.get(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(serialize_project(project)), 200


def compute_score(student_skill_ids, student_interest_ids, availability_hours,
                   required_skill_ids, project_interest_id, expected_hours):
    if required_skill_ids:
        overlap = student_skill_ids & required_skill_ids
        skill_match = len(overlap) / len(required_skill_ids)
    else:
        skill_match = 0.0

    if project_interest_id:
        interest_match = 1.0 if project_interest_id in student_interest_ids else 0.0
    else:
        interest_match = 0.5

    if expected_hours and expected_hours > 0:
        availability_match = min(availability_hours / expected_hours, 1.0)
    else:
        availability_match = 1.0

    score = (
        SKILL_WEIGHT * skill_match
        + INTEREST_WEIGHT * interest_match
        + AVAILABILITY_WEIGHT * availability_match
    )
    return {
        "score": round(score * 100, 1),
        "skill_match": round(skill_match * 100, 1),
        "interest_match": round(interest_match * 100, 1),
        "availability_match": round(availability_match * 100, 1),
    }


@matching_bp.route("/projects/<int:project_id>/matches", methods=["GET"])
@jwt_required()
def get_matches(project_id):
    project = Project.query.get(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    required_skill_ids = {
        row.skill_id for row in ProjectSkill.query.filter_by(project_id=project_id).all()
    }

    candidates = User.query.filter(User.id != project.creator_id, User.role == "student").all()

    results = []
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

        existing = Match.query.filter_by(project_id=project_id, user_id=student.id).first()
        if existing:
            existing.score = breakdown["score"]
            existing.skill_match = breakdown["skill_match"]
            existing.interest_match = breakdown["interest_match"]
            existing.availability_match = breakdown["availability_match"]
        else:
            db.session.add(Match(
                project_id=project_id, user_id=student.id,
                score=breakdown["score"], skill_match=breakdown["skill_match"],
                interest_match=breakdown["interest_match"], availability_match=breakdown["availability_match"],
            ))

        results.append({
            "user_id": student.id,
            "name": student.name,
            "email": student.email,
            **breakdown,
        })

    db.session.commit()

    results.sort(key=lambda r: r["score"], reverse=True)

    return jsonify({
        "project": serialize_project(project),
        "ranked_matches": results,
    }), 200
