from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import db
from models import User, StudentProfile, Skill, StudentSkill, Interest, StudentInterest

profile_bp = Blueprint("profile", __name__, url_prefix="/api/profile")

VALID_LEVELS = ("beginner", "intermediate", "advanced")


def get_or_create_profile(user_id):
    profile = StudentProfile.query.get(user_id)
    if not profile:
        profile = StudentProfile(user_id=user_id)
        db.session.add(profile)
        db.session.commit()
    return profile


def serialize_profile(user):
    profile = StudentProfile.query.get(user.id)

    skills = (
        db.session.query(StudentSkill, Skill)
        .join(Skill, StudentSkill.skill_id == Skill.id)
        .filter(StudentSkill.user_id == user.id)
        .all()
    )
    interests = (
        db.session.query(StudentInterest, Interest)
        .join(Interest, StudentInterest.interest_id == Interest.id)
        .filter(StudentInterest.user_id == user.id)
        .all()
    )

    return {
        "user_id": user.id,
        "name": user.name,
        "email": user.email,
        "college": user.college,
        "department": profile.department if profile and profile.department else "Computer Science",
        "preferred_event": profile.preferred_event if profile and profile.preferred_event else "AI Hackathon",
        "bio": profile.bio if profile else None,
        "availability_hours": profile.availability_hours if profile else 0,
        "experience_level": profile.experience_level if profile else "beginner",
        "skills": [{"id": s.id, "name": s.name, "proficiency": ss.proficiency} for ss, s in skills],
        "interests": [{"id": i.id, "name": i.name} for si, i in interests],
    }


@profile_bp.route("/me", methods=["GET"])
@jwt_required()
def get_my_profile():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(serialize_profile(user)), 200


@profile_bp.route("/me", methods=["PUT"])
@jwt_required()
def update_my_profile():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    profile = get_or_create_profile(user_id)

    if "bio" in data:
        profile.bio = (data.get("bio") or "").strip()[:500]

    if "department" in data:
        profile.department = (data.get("department") or "Computer Science").strip()[:100]

    if "preferred_event" in data:
        profile.preferred_event = (data.get("preferred_event") or "AI Hackathon").strip()[:150]

    if "availability_hours" in data:
        try:
            hours = int(data.get("availability_hours"))
        except (TypeError, ValueError):
            return jsonify({"error": "availability_hours must be a number"}), 400
        if hours < 0 or hours > 168:
            return jsonify({"error": "availability_hours must be between 0 and 168"}), 400
        profile.availability_hours = hours

    if "experience_level" in data:
        level = (data.get("experience_level") or "").lower()
        if level not in VALID_LEVELS:
            return jsonify({"error": f"experience_level must be one of {VALID_LEVELS}"}), 400
        profile.experience_level = level

    db.session.commit()
    return jsonify(serialize_profile(user)), 200


@profile_bp.route("/skills", methods=["POST"])
@jwt_required()
def add_skill():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    skill_name = (data.get("skill_name") or "").strip()
    proficiency = (data.get("proficiency") or "beginner").lower()

    if not skill_name:
        return jsonify({"error": "skill_name is required"}), 400
    if proficiency not in VALID_LEVELS:
        return jsonify({"error": f"proficiency must be one of {VALID_LEVELS}"}), 400

    skill = Skill.query.filter(db.func.lower(Skill.name) == skill_name.lower()).first()
    if not skill:
        skill = Skill(name=skill_name)
        db.session.add(skill)
        db.session.commit()

    existing = StudentSkill.query.filter_by(user_id=user_id, skill_id=skill.id).first()
    if existing:
        existing.proficiency = proficiency
    else:
        db.session.add(StudentSkill(user_id=user_id, skill_id=skill.id, proficiency=proficiency))
    db.session.commit()

    user = User.query.get(user_id)
    return jsonify(serialize_profile(user)), 201


@profile_bp.route("/skills/<int:skill_id>", methods=["DELETE"])
@jwt_required()
def remove_skill(skill_id):
    user_id = int(get_jwt_identity())
    row = StudentSkill.query.filter_by(user_id=user_id, skill_id=skill_id).first()
    if not row:
        return jsonify({"error": "Skill not found on your profile"}), 404

    db.session.delete(row)
    db.session.commit()

    user = User.query.get(user_id)
    return jsonify(serialize_profile(user)), 200


@profile_bp.route("/interests", methods=["POST"])
@jwt_required()
def add_interest():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    interest_name = (data.get("interest_name") or "").strip()

    if not interest_name:
        return jsonify({"error": "interest_name is required"}), 400

    interest = Interest.query.filter(db.func.lower(Interest.name) == interest_name.lower()).first()
    if not interest:
        interest = Interest(name=interest_name)
        db.session.add(interest)
        db.session.commit()

    existing = StudentInterest.query.filter_by(user_id=user_id, interest_id=interest.id).first()
    if not existing:
        db.session.add(StudentInterest(user_id=user_id, interest_id=interest.id))
        db.session.commit()

    user = User.query.get(user_id)
    return jsonify(serialize_profile(user)), 201


@profile_bp.route("/interests/<int:interest_id>", methods=["DELETE"])
@jwt_required()
def remove_interest(interest_id):
    user_id = int(get_jwt_identity())
    row = StudentInterest.query.filter_by(user_id=user_id, interest_id=interest_id).first()
    if not row:
        return jsonify({"error": "Interest not found on your profile"}), 404

    db.session.delete(row)
    db.session.commit()

    user = User.query.get(user_id)
    return jsonify(serialize_profile(user)), 200


@profile_bp.route("/skills/catalog", methods=["GET"])
def list_all_skills():
    skills = Skill.query.order_by(Skill.name).all()
    return jsonify({"skills": [{"id": s.id, "name": s.name, "category": s.category} for s in skills]}), 200


@profile_bp.route("/interests/catalog", methods=["GET"])
def list_all_interests():
    interests = Interest.query.order_by(Interest.name).all()
    return jsonify({"interests": [{"id": i.id, "name": i.name} for i in interests]}), 200
