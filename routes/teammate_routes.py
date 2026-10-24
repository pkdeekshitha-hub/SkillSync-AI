from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import db
from models import (
    User, StudentProfile, Skill, StudentSkill, Interest, StudentInterest,
    TeammateMatch, Notification
)

teammate_bp = Blueprint("teammates", __name__, url_prefix="/api/teammates")


def calculate_teammate_score(my_skills, my_interests, my_dept, my_event,
                             other_skills, other_interests, other_dept, other_event):
    """
    Computes a match score (0-100%) between two students based on:
    - Skills (complementary & shared) - 40%
    - Interests - 30%
    - Event alignment - 20%
    - Department synergy - 10%
    """
    my_skill_set = {s.lower() for s in my_skills}
    other_skill_set = {s.lower() for s in other_skills}

    shared_skills = my_skill_set & other_skill_set
    all_skills = my_skill_set | other_skill_set

    # Complementary skills bonus: having different but complementary skills is great for teams
    skill_score = 0.5
    if all_skills:
        # Balanced mix of shared skills (common ground) and unique skills (specialization)
        overlap_ratio = len(shared_skills) / len(all_skills)
        if len(shared_skills) > 0 and len(all_skills) > len(shared_skills):
            skill_score = 0.65 + min(0.35, overlap_ratio * 0.7)
        elif len(shared_skills) > 0:
            skill_score = 0.75
        elif len(all_skills) >= 2:
            skill_score = 0.55  # Good complementary diversity

    # Interests score
    my_int_set = {i.lower() for i in my_interests}
    other_int_set = {i.lower() for i in other_interests}
    shared_interests = my_int_set & other_int_set
    total_interests = my_int_set | other_int_set

    if total_interests:
        int_score = len(shared_interests) / len(total_interests)
        if shared_interests:
            int_score = max(int_score, 0.6)  # Having at least 1 shared interest gives strong baseline
    else:
        int_score = 0.5

    # Event alignment score
    event_score = 0.5
    if my_event and other_event:
        if my_event.strip().lower() == other_event.strip().lower():
            event_score = 1.0
        elif any(w in other_event.lower() for w in my_event.lower().split()):
            event_score = 0.8
    elif not my_event or not other_event:
        event_score = 0.7

    # Department synergy
    dept_score = 0.6
    if my_dept and other_dept:
        if my_dept.strip().lower() == other_dept.strip().lower():
            dept_score = 0.9
        else:
            # Cross-department tech collaboration
            dept_score = 0.8

    total = (0.40 * skill_score) + (0.30 * int_score) + (0.20 * event_score) + (0.10 * dept_score)
    final_score = round(min(99.0, max(45.0, total * 100.0)), 1)

    reasons = []
    if shared_interests:
        reasons.append(f"{len(shared_interests)} shared interest{'s' if len(shared_interests)>1 else ''}")
    if shared_skills:
        reasons.append(f"Shared skill{'s' if len(shared_skills)>1 else ''}: {', '.join(list(shared_skills)[:2])}")
    if event_score >= 0.8 and other_event:
        reasons.append(f"Targeting {other_event}")
    if not reasons:
        reasons.append("Complementary skillsets for hackathon teams")

    return final_score, " · ".join(reasons)


def get_user_skills_and_interests(user_id):
    skills = (
        db.session.query(Skill.name, StudentSkill.proficiency)
        .join(StudentSkill, StudentSkill.skill_id == Skill.id)
        .filter(StudentSkill.user_id == user_id)
        .all()
    )
    interests = (
        db.session.query(Interest.name)
        .join(StudentInterest, StudentInterest.interest_id == Interest.id)
        .filter(StudentInterest.user_id == user_id)
        .all()
    )
    return skills, [i[0] for i in interests]


def get_match_relationship(user_a_id, user_b_id, event_name=None):
    """
    Determines relationship between user_a (current user) and user_b (candidate).
    Returns ("none" | "pending_sent" | "pending_received" | "matched" | "rejected", event_name)
    """
    # Check if user_a sent to user_b
    q1 = TeammateMatch.query.filter_by(sender_id=user_a_id, receiver_id=user_b_id)
    if event_name:
        q1 = q1.filter(TeammateMatch.event_name.ilike(event_name))
    sent = q1.order_by(TeammateMatch.updated_at.desc()).first()

    # Check if user_b sent to user_a
    q2 = TeammateMatch.query.filter_by(sender_id=user_b_id, receiver_id=user_a_id)
    if event_name:
        q2 = q2.filter(TeammateMatch.event_name.ilike(event_name))
    received = q2.order_by(TeammateMatch.updated_at.desc()).first()

    if (sent and sent.status == "matched") or (received and received.status == "matched"):
        ev = (sent.event_name if sent else received.event_name) or "AI Hackathon"
        return "matched", ev
    if sent and sent.status == "rejected":
        return "rejected", sent.event_name
    if received and received.status == "rejected":
        return "rejected", received.event_name
    if sent and sent.status == "pending":
        return "pending_sent", sent.event_name
    if received and received.status == "pending":
        return "pending_received", received.event_name

    return "none", event_name or "AI Hackathon"


@teammate_bp.route("/suggested", methods=["GET"])
@jwt_required()
def suggested_teammates():
    user_id = int(get_jwt_identity())
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    my_profile = StudentProfile.query.get(user_id)
    my_dept = my_profile.department if my_profile else "Computer Science"
    my_event = my_profile.preferred_event if my_profile else "AI Hackathon"
    my_skills_raw, my_interests = get_user_skills_and_interests(user_id)
    my_skills = [s[0] for s in my_skills_raw]

    # Filters
    event_filter = request.args.get("event", "").strip()
    dept_filter = request.args.get("department", "").strip()
    skill_filter = request.args.get("skill", "").strip()
    search = request.args.get("search", "").strip().lower()

    # Find candidates
    candidates = User.query.filter(User.id != user_id, User.role == "student").all()
    results = []

    for c in candidates:
        c_profile = StudentProfile.query.get(c.id)
        c_dept = (c_profile.department if c_profile and c_profile.department else "Computer Science").strip()
        c_event = (c_profile.preferred_event if c_profile and c_profile.preferred_event else "AI Hackathon").strip()
        c_skills_raw, c_interests = get_user_skills_and_interests(c.id)
        c_skills = [s[0] for s in c_skills_raw]

        # Apply filters
        if event_filter and event_filter.lower() != "all":
            if event_filter.lower() not in c_event.lower():
                continue

        if dept_filter and dept_filter.lower() != "all":
            if dept_filter.lower() not in c_dept.lower():
                continue

        if skill_filter:
            if not any(skill_filter.lower() in s.lower() for s in c_skills):
                continue

        if search:
            match_name = search in c.name.lower()
            match_skill = any(search in s.lower() for s in c_skills)
            match_interest = any(search in i.lower() for i in c_interests)
            if not (match_name or match_skill or match_interest):
                continue

        score, reason = calculate_teammate_score(
            my_skills, my_interests, my_dept, my_event,
            c_skills, c_interests, c_dept, c_event
        )

        status, active_event = get_match_relationship(user_id, c.id, c_event)

        results.append({
            "id": c.id,
            "name": c.name,
            "college": c.college or "College of Engineering",
            "department": c_dept,
            "preferred_event": c_event,
            "bio": c_profile.bio if c_profile else "",
            "experience_level": c_profile.experience_level if c_profile else "beginner",
            "availability_hours": c_profile.availability_hours if c_profile else 0,
            "skills": [{"name": s[0], "proficiency": s[1]} for s in c_skills_raw],
            "interests": c_interests,
            "score": score,
            "match_reason": reason,
            "status": status,
            "event_name": active_event or c_event,
        })

    # Sort candidates by status (pending_received first, then matched, then none by score)
    def sort_key(item):
        priority = 3
        if item["status"] == "pending_received":
            priority = 0
        elif item["status"] == "matched":
            priority = 1
        elif item["status"] == "none":
            priority = 2
        elif item["status"] == "pending_sent":
            priority = 4
        else:
            priority = 5
        return (priority, -item["score"])

    results.sort(key=sort_key)

    return jsonify({
        "my_event": my_event,
        "my_department": my_dept,
        "suggested_teammates": results,
    }), 200


@teammate_bp.route("/<int:target_user_id>/profile", methods=["GET"])
@jwt_required()
def get_teammate_profile(target_user_id):
    user_id = int(get_jwt_identity())
    target = User.query.get(target_user_id)
    if not target:
        return jsonify({"error": "Student not found"}), 404

    target_profile = StudentProfile.query.get(target_user_id)
    t_dept = target_profile.department if target_profile and target_profile.department else "Computer Science"
    t_event = target_profile.preferred_event if target_profile and target_profile.preferred_event else "AI Hackathon"
    skills_raw, interests = get_user_skills_and_interests(target_user_id)

    my_profile = StudentProfile.query.get(user_id)
    my_dept = my_profile.department if my_profile else "Computer Science"
    my_event = my_profile.preferred_event if my_profile else "AI Hackathon"
    my_skills_raw, my_interests = get_user_skills_and_interests(user_id)
    my_skills = [s[0] for s in my_skills_raw]

    score, reason = calculate_teammate_score(
        my_skills, my_interests, my_dept, my_event,
        [s[0] for s in skills_raw], interests, t_dept, t_event
    )

    status, active_event = get_match_relationship(user_id, target_user_id, t_event)

    # Privacy notice: email and phone are strictly protected and never exposed
    return jsonify({
        "id": target.id,
        "name": target.name,
        "college": target.college or "College of Engineering",
        "department": t_dept,
        "preferred_event": t_event,
        "bio": target_profile.bio if target_profile else "",
        "experience_level": target_profile.experience_level if target_profile else "beginner",
        "availability_hours": target_profile.availability_hours if target_profile else 0,
        "skills": [{"name": s[0], "proficiency": s[1]} for s in skills_raw],
        "interests": interests,
        "score": score,
        "match_reason": reason,
        "status": status,
        "event_name": active_event or t_event,
    }), 200


@teammate_bp.route("/<int:target_user_id>/action", methods=["POST"])
@jwt_required()
def handle_teammate_action(target_user_id):
    user_id = int(get_jwt_identity())
    if user_id == target_user_id:
        return jsonify({"error": "Cannot match with yourself"}), 400

    target = User.query.get(target_user_id)
    current_user = User.query.get(user_id)
    if not target or not current_user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "").lower().strip()
    event_name = (data.get("event_name") or "AI Hackathon").strip()

    if action not in ("accept", "reject"):
        return jsonify({"error": "action must be 'accept' or 'reject'"}), 400

    # Look for existing request in either direction
    sent_req = TeammateMatch.query.filter_by(
        sender_id=user_id, receiver_id=target_user_id, event_name=event_name
    ).first()

    received_req = TeammateMatch.query.filter_by(
        sender_id=target_user_id, receiver_id=user_id, event_name=event_name
    ).first()

    if action == "accept":
        # Check if target user has already sent an accept/pending request to current user
        if received_req and received_req.status == "pending":
            # Mutual acceptance!
            received_req.status = "matched"
            if sent_req:
                sent_req.status = "matched"
            else:
                sent_req = TeammateMatch(
                    sender_id=user_id, receiver_id=target_user_id,
                    event_name=event_name, status="matched"
                )
                db.session.add(sent_req)

            # Notifications for both users
            db.session.add(Notification(
                user_id=target_user_id,
                title="🎉 Match Accepted!",
                message=f"You and {current_user.name} are now matched for {event_name}! Start chatting now.",
                notif_type="match",
                link_action=f"chat:{user_id}",
            ))
            db.session.add(Notification(
                user_id=user_id,
                title="🎉 Match Accepted!",
                message=f"You and {target.name} are now matched for {event_name}! Start chatting now.",
                notif_type="match",
                link_action=f"chat:{target_user_id}",
            ))

            db.session.commit()
            return jsonify({
                "status": "matched",
                "message": f"🎉 Mutual Match! You and {target.name} are matched for {event_name}.",
                "target_id": target_user_id,
                "target_name": target.name,
            }), 200

        else:
            # First student accepting/sending request
            if not sent_req:
                sent_req = TeammateMatch(
                    sender_id=user_id, receiver_id=target_user_id,
                    event_name=event_name, status="pending"
                )
                db.session.add(sent_req)
            else:
                sent_req.status = "pending"

            # Notify target student
            db.session.add(Notification(
                user_id=target_user_id,
                title="⭐ New Match Request",
                message=f"{current_user.name} accepted/requested to match with you for {event_name}.",
                notif_type="match",
                link_action="teammates",
            ))

            db.session.commit()
            return jsonify({
                "status": "pending_sent",
                "message": f"Match request sent to {target.name}. Waiting for mutual acceptance.",
                "target_id": target_user_id,
                "target_name": target.name,
            }), 200

    elif action == "reject":
        if sent_req:
            sent_req.status = "rejected"
        else:
            sent_req = TeammateMatch(
                sender_id=user_id, receiver_id=target_user_id,
                event_name=event_name, status="rejected"
            )
            db.session.add(sent_req)

        if received_req:
            received_req.status = "rejected"

        db.session.commit()
        return jsonify({
            "status": "rejected",
            "message": f"Match suggestion for {target.name} dismissed.",
            "target_id": target_user_id,
        }), 200


@teammate_bp.route("/matches", methods=["GET"])
@jwt_required()
def get_my_matches():
    user_id = int(get_jwt_identity())

    # Find all matches where status == "matched"
    matches_sent = TeammateMatch.query.filter_by(sender_id=user_id, status="matched").all()
    matches_recv = TeammateMatch.query.filter_by(receiver_id=user_id, status="matched").all()

    matched_user_ids = {}
    for m in matches_sent:
        matched_user_ids[m.receiver_id] = m.event_name
    for m in matches_recv:
        matched_user_ids[m.sender_id] = m.event_name

    results = []
    for other_id, event_name in matched_user_ids.items():
        other_user = User.query.get(other_id)
        if not other_user:
            continue
        other_profile = StudentProfile.query.get(other_id)
        dept = other_profile.department if other_profile and other_profile.department else "Computer Science"
        skills_raw, interests = get_user_skills_and_interests(other_id)

        results.append({
            "id": other_user.id,
            "name": other_user.name,
            "college": other_user.college or "College of Engineering",
            "department": dept,
            "event_name": event_name,
            "bio": other_profile.bio if other_profile else "",
            "skills": [s[0] for s in skills_raw],
            "interests": interests,
            "status": "matched",
        })

    return jsonify({"matches": results}), 200
