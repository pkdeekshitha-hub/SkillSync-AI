from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import db
from models import User, StudentProfile, Message, TeammateMatch, Notification

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")


@chat_bp.route("/conversations", methods=["GET"])
@jwt_required()
def get_conversations():
    user_id = int(get_jwt_identity())

    # Find all mutually matched users
    matches_sent = TeammateMatch.query.filter_by(sender_id=user_id, status="matched").all()
    matches_recv = TeammateMatch.query.filter_by(receiver_id=user_id, status="matched").all()

    matched_users = {}
    for m in matches_sent:
        matched_users[m.receiver_id] = m.event_name
    for m in matches_recv:
        matched_users[m.sender_id] = m.event_name

    # Also find any users with whom messages have been exchanged
    msg_users = db.session.query(Message.sender_id, Message.receiver_id).filter(
        (Message.sender_id == user_id) | (Message.receiver_id == user_id)
    ).all()

    for s_id, r_id in msg_users:
        other_id = r_id if s_id == user_id else s_id
        if other_id not in matched_users:
            matched_users[other_id] = "Hackathon Chat"

    conversations = []
    for other_id, event_name in matched_users.items():
        other_user = User.query.get(other_id)
        if not other_user:
            continue

        profile = StudentProfile.query.get(other_id)
        dept = profile.department if profile and profile.department else "Computer Science"

        # Get last message
        last_msg = Message.query.filter(
            ((Message.sender_id == user_id) & (Message.receiver_id == other_id)) |
            ((Message.sender_id == other_id) & (Message.receiver_id == user_id))
        ).order_by(Message.sent_at.desc()).first()

        # Unread count
        unread = Message.query.filter_by(
            sender_id=other_id, receiver_id=user_id, is_read=False
        ).count()

        conversations.append({
            "user": {
                "id": other_user.id,
                "name": other_user.name,
                "college": other_user.college or "College of Engineering",
                "department": dept,
            },
            "event_name": event_name,
            "last_message": {
                "id": last_msg.id if last_msg else None,
                "text": last_msg.message_text if last_msg else "No messages yet — say hi!",
                "sent_at": last_msg.sent_at.isoformat() if last_msg else None,
                "is_me": (last_msg.sender_id == user_id) if last_msg else False,
            } if last_msg else None,
            "unread_count": unread,
        })

    # Sort conversations by last message timestamp or name
    conversations.sort(
        key=lambda c: (c["last_message"]["sent_at"] if c["last_message"] and c["last_message"]["sent_at"] else ""),
        reverse=True
    )

    return jsonify({"conversations": conversations}), 200


@chat_bp.route("/messages/<int:other_user_id>", methods=["GET"])
@jwt_required()
def get_messages(other_user_id):
    user_id = int(get_jwt_identity())
    other_user = User.query.get(other_user_id)
    if not other_user:
        return jsonify({"error": "User not found"}), 404

    # Fetch messages in chronological order
    messages = Message.query.filter(
        ((Message.sender_id == user_id) & (Message.receiver_id == other_user_id)) |
        ((Message.sender_id == other_user_id) & (Message.receiver_id == user_id))
    ).order_by(Message.sent_at.asc()).all()

    # Mark unread messages sent to me as read
    unread_messages = [m for m in messages if m.sender_id == other_user_id and not m.is_read]
    if unread_messages:
        for m in unread_messages:
            m.is_read = True
        db.session.commit()

    profile = StudentProfile.query.get(other_user_id)
    dept = profile.department if profile and profile.department else "Computer Science"

    # Find active event
    match_row = TeammateMatch.query.filter(
        ((TeammateMatch.sender_id == user_id) & (TeammateMatch.receiver_id == other_user_id)) |
        ((TeammateMatch.sender_id == other_user_id) & (TeammateMatch.receiver_id == user_id))
    ).filter_by(status="matched").first()
    event_name = match_row.event_name if match_row else "Project Collaboration"

    return jsonify({
        "other_user": {
            "id": other_user.id,
            "name": other_user.name,
            "college": other_user.college or "College of Engineering",
            "department": dept,
            "event_name": event_name,
        },
        "messages": [{
            "id": m.id,
            "sender_id": m.sender_id,
            "receiver_id": m.receiver_id,
            "message_text": m.message_text,
            "sent_at": m.sent_at.isoformat(),
            "is_read": m.is_read,
            "is_me": (m.sender_id == user_id),
        } for m in messages],
    }), 200


@chat_bp.route("/messages/<int:other_user_id>", methods=["POST"])
@jwt_required()
def send_message(other_user_id):
    user_id = int(get_jwt_identity())
    if user_id == other_user_id:
        return jsonify({"error": "Cannot message yourself"}), 400

    other_user = User.query.get(other_user_id)
    current_user = User.query.get(user_id)
    if not other_user or not current_user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    text = (data.get("message_text") or "").strip()
    if not text:
        return jsonify({"error": "Message text cannot be empty"}), 400

    new_msg = Message(
        sender_id=user_id,
        receiver_id=other_user_id,
        message_text=text,
        sent_at=datetime.utcnow(),
        is_read=False,
    )
    db.session.add(new_msg)

    # In-app notification for receiver
    snippet = text if len(text) <= 60 else text[:57] + "..."
    db.session.add(Notification(
        user_id=other_user_id,
        title=f"💬 New message from {current_user.name}",
        message=snippet,
        notif_type="chat",
        link_action=f"chat:{user_id}",
    ))

    db.session.commit()

    return jsonify({
        "id": new_msg.id,
        "sender_id": new_msg.sender_id,
        "receiver_id": new_msg.receiver_id,
        "message_text": new_msg.message_text,
        "sent_at": new_msg.sent_at.isoformat(),
        "is_read": False,
        "is_me": True,
    }), 201


@chat_bp.route("/unread-count", methods=["GET"])
@jwt_required()
def get_unread_count():
    user_id = int(get_jwt_identity())
    count = Message.query.filter_by(receiver_id=user_id, is_read=False).count()
    return jsonify({"unread_count": count}), 200
