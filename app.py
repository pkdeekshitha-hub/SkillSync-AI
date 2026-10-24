import os
from flask import Flask, jsonify, send_file
from flask_cors import CORS

from config import Config
from extensions import db, jwt, bcrypt
from routes.auth_routes import auth_bp
from routes.profile_routes import profile_bp
from routes.matching_routes import matching_bp
from routes.team_routes import team_bp
from routes.finder_routes import finder_bp
from routes.gap_routes import gap_bp
from routes.admin_routes import admin_bp
from routes.teammate_routes import teammate_bp
from routes.chat_routes import chat_bp
from routes.notification_routes import notif_bp


def seed_reference_data():
    from models import Skill, Interest

    if Skill.query.count() == 0:
        starter_skills = [
            ("Python", "Programming"), ("JavaScript", "Programming"),
            ("Flask", "Backend"), ("React", "Frontend"),
            ("MySQL", "Database"), ("Machine Learning", "AI/ML"),
            ("Figma", "Design"), ("UI/UX Design", "Design"),
            ("Data Visualization", "AI/ML"), ("Statistics", "AI/ML"),
            ("Node.js", "Backend"), ("Docker", "DevOps"), ("AWS", "DevOps"),
            ("Git", "Tools"), ("Testing", "QA"), ("Agile/Scrum", "Process"),
            ("Mobile Development", "Programming"), ("Cybersecurity", "Security"),
            ("Product Management", "Business"), ("Business Analysis", "Business"),
            ("Communication", "Soft Skills"),
        ]
        for name, category in starter_skills:
            db.session.add(Skill(name=name, category=category))

    if Interest.query.count() == 0:
        starter_interests = ["AI Projects", "Healthcare", "Fintech", "EdTech", "Sustainability"]
        for name in starter_interests:
            db.session.add(Interest(name=name))

    db.session.commit()

    from models import TargetRole, TargetRoleSkill

    if TargetRole.query.count() == 0:
        role_skill_map = {
            "Data Scientist": ["Python", "MySQL", "Statistics", "Machine Learning", "Data Visualization"],
            "Frontend Developer": ["JavaScript", "React", "UI/UX Design"],
            "Backend Developer": ["Python", "Flask", "MySQL"],
            "ML Engineer": ["Python", "Machine Learning", "Statistics"],
            "UI/UX Designer": ["Figma", "UI/UX Design"],
            "Full Stack Developer": ["JavaScript", "React", "Node.js", "MySQL", "Flask"],
            "DevOps Engineer": ["Docker", "AWS", "Git", "Python"],
            "Product Manager": ["Product Management", "Communication", "Agile/Scrum", "Data Visualization"],
            "QA Engineer": ["Testing", "Python", "Communication"],
            "Mobile Developer": ["Mobile Development", "JavaScript", "UI/UX Design"],
            "Cloud Engineer": ["AWS", "Docker", "Python"],
            "Cybersecurity Analyst": ["Cybersecurity", "Python", "MySQL"],
            "Business Analyst": ["Business Analysis", "Data Visualization", "Communication", "Statistics"],
        }
        for role_name, skill_names in role_skill_map.items():
            role = TargetRole(name=role_name)
            db.session.add(role)
            db.session.commit()
            for skill_name in skill_names:
                skill = Skill.query.filter(db.func.lower(Skill.name) == skill_name.lower()).first()
                if skill:
                    db.session.add(TargetRoleSkill(role_id=role.id, skill_id=skill.id))
        db.session.commit()


def seed_teammate_and_chat_demo():
    from models import User, StudentProfile, TeammateMatch, Message, Notification, Team, TeamMember
    from datetime import datetime, timedelta

    # Ensure Lisa, Rohan, Rose, Yoha exist and have department & preferred_event
    lisa = User.query.filter_by(email="lisa@mrcas.com").first()
    rohan = User.query.filter_by(email="rohan@mrcas.com").first()
    rose = User.query.filter_by(email="rose@mrcas.com").first()
    yoha = User.query.filter_by(email="yoha@mrcas.edu.in").first()

    if lisa:
        lp = StudentProfile.query.get(lisa.id)
        if lp:
            if not lp.department:
                lp.department = "Computer Science"
            if not lp.preferred_event:
                lp.preferred_event = "AI Hackathon"

    if rohan:
        rp = StudentProfile.query.get(rohan.id)
        if rp:
            if not rp.department:
                rp.department = "AI & Data Science"
            if not rp.preferred_event:
                rp.preferred_event = "AI Hackathon"

    if rose:
        rop = StudentProfile.query.get(rose.id)
        if rop:
            if not rop.department:
                rop.department = "Information Technology"
            if not rop.preferred_event:
                rop.preferred_event = "Web3 Summit"

    if yoha:
        yp = StudentProfile.query.get(yoha.id)
        if yp:
            if not yp.department:
                yp.department = "Computer Science"
            if not yp.preferred_event:
                yp.preferred_event = "AI Hackathon"

    db.session.commit()

    if lisa and rohan:
        # Check mutual match between Lisa and Rohan
        m1 = TeammateMatch.query.filter_by(sender_id=lisa.id, receiver_id=rohan.id, event_name="AI Hackathon").first()
        m2 = TeammateMatch.query.filter_by(sender_id=rohan.id, receiver_id=lisa.id, event_name="AI Hackathon").first()
        if not m1 and not m2:
            db.session.add(TeammateMatch(sender_id=rohan.id, receiver_id=lisa.id, event_name="AI Hackathon", status="matched"))
            db.session.add(TeammateMatch(sender_id=lisa.id, receiver_id=rohan.id, event_name="AI Hackathon", status="matched"))
            db.session.commit()

        # Seed sample chat messages if none exist
        existing_msgs = Message.query.filter(
            ((Message.sender_id == lisa.id) & (Message.receiver_id == rohan.id)) |
            ((Message.sender_id == rohan.id) & (Message.receiver_id == lisa.id))
        ).count()

        if existing_msgs == 0:
            t0 = datetime.utcnow() - timedelta(minutes=15)
            t1 = datetime.utcnow() - timedelta(minutes=12)
            t2 = datetime.utcnow() - timedelta(minutes=10)
            db.session.add(Message(sender_id=rohan.id, receiver_id=lisa.id, message_text="Hey! I saw we got matched for the AI hackathon.", sent_at=t0, is_read=True))
            db.session.add(Message(sender_id=lisa.id, receiver_id=rohan.id, message_text="Hey! Yes, I was thinking about a healthcare AI project.", sent_at=t1, is_read=True))
            db.session.add(Message(sender_id=rohan.id, receiver_id=lisa.id, message_text="That sounds good! Shall we discuss the idea and divide the work?", sent_at=t2, is_read=True))
            db.session.commit()

        # Seed sample notifications if none exist
        if Notification.query.filter_by(user_id=lisa.id).count() == 0:
            db.session.add(Notification(
                user_id=lisa.id,
                title="🎉 Match Accepted!",
                message="You and Rohan are matched for AI Hackathon! Start chatting now.",
                notif_type="match",
                link_action=f"chat:{rohan.id}",
                is_read=False,
            ))
            db.session.add(Notification(
                user_id=lisa.id,
                title="💬 New message from Rohan",
                message="That sounds good! Shall we discuss the idea and divide the work?",
                notif_type="chat",
                link_action=f"chat:{rohan.id}",
                is_read=False,
            ))
            db.session.commit()

        # Seed sample team if none exist
        if Team.query.filter_by(created_by=lisa.id).count() == 0:
            team = Team(
                name="HealthAI Innovators",
                event_name="AI Hackathon",
                project_idea="AI-powered preliminary healthcare triage and skin diagnostic tool for rural clinics",
                created_by=lisa.id,
            )
            db.session.add(team)
            db.session.commit()
            db.session.add(TeamMember(team_id=team.id, user_id=lisa.id, role="Team Lead"))
            db.session.add(TeamMember(team_id=team.id, user_id=rohan.id, role="ML Engineer"))
            if rose:
                db.session.add(TeamMember(team_id=team.id, user_id=rose.id, role="UI/UX Designer"))
            db.session.commit()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app)

    db.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(matching_bp)
    app.register_blueprint(team_bp)
    app.register_blueprint(finder_bp)
    app.register_blueprint(gap_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(teammate_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(notif_bp)

    @app.route("/", methods=["GET"])
    @app.route("/dashboard", methods=["GET"])
    def serve_dashboard():
        html_path = os.path.join(app.root_path, "skillsync_dashboard (1).html")
        return send_file(html_path)

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "modules": [
                "User Registration & Login",
                "Student Skill Profile",
                "Smart Matching System",
                "Suggested Teammates & Mutual Acceptance",
                "Private In-Platform Chat",
                "Team Formation & Management",
                "In-App Notifications",
                "Project & Hackathon Finder",
                "Skill Gap Analysis",
                "Admin Module"
            ]
        }), 200

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Route not found"}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal server error"}), 500

    with app.app_context():
        db.create_all()
        seed_reference_data()
        seed_teammate_and_chat_demo()

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)


