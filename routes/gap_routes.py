from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import db
from models import Skill, StudentSkill, TargetRole, TargetRoleSkill

gap_bp = Blueprint("gap", __name__, url_prefix="/api")


@gap_bp.route("/target-roles", methods=["GET"])
def list_target_roles():
    roles = TargetRole.query.order_by(TargetRole.name).all()
    return jsonify({"roles": [{"id": r.id, "name": r.name} for r in roles]}), 200


@gap_bp.route("/target-roles", methods=["POST"])
@jwt_required()
def create_target_role():
    data = request.get_json(silent=True) or {}
    role_name = (data.get("name") or "").strip()
    skill_names = data.get("skill_names") or []

    if not role_name:
        return jsonify({"error": "name is required"}), 400
    if not isinstance(skill_names, list) or not skill_names:
        return jsonify({"error": "skill_names must be a non-empty list"}), 400

    existing = TargetRole.query.filter(TargetRole.name.ilike(role_name)).first()
    if existing:
        return jsonify({"error": f"'{role_name}' already exists — just select it from the list"}), 409

    role = TargetRole(name=role_name)
    db.session.add(role)
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
        db.session.add(TargetRoleSkill(role_id=role.id, skill_id=skill.id))
    db.session.commit()

    return jsonify({"id": role.id, "name": role.name}), 201


@gap_bp.route("/skill-gap", methods=["GET"])
@jwt_required()
def skill_gap():
    user_id = int(get_jwt_identity())
    role_name = request.args.get("role")
    if not role_name:
        return jsonify({"error": "role query parameter is required"}), 400

    role = TargetRole.query.filter(TargetRole.name.ilike(role_name)).first()
    if not role:
        return jsonify({"error": f"No target role found matching '{role_name}'"}), 404

    required_skills = (
        Skill.query.join(TargetRoleSkill, TargetRoleSkill.skill_id == Skill.id)
        .filter(TargetRoleSkill.role_id == role.id).all()
    )
    required_ids = {s.id for s in required_skills}
    student_skill_ids = {row.skill_id for row in StudentSkill.query.filter_by(user_id=user_id).all()}
    matched_ids = required_ids & student_skill_ids
    missing_ids = required_ids - student_skill_ids

    matched_skills = [s.name for s in required_skills if s.id in matched_ids]
    missing_skills = [s.name for s in required_skills if s.id in missing_ids]
    match_percentage = round((len(matched_ids) / len(required_ids)) * 100, 1) if required_ids else 0.0

    return jsonify({
        "target_role": role.name, "required_skills": [s.name for s in required_skills],
        "matched_skills": matched_skills, "missing_skills": missing_skills,
        "match_percentage": match_percentage,
    }), 200
