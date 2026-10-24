from datetime import datetime
from extensions import db, bcrypt


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    college = db.Column(db.String(150), nullable=True)
    role = db.Column(db.String(20), nullable=False, default="student")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, raw_password):
        self.password_hash = bcrypt.generate_password_hash(raw_password).decode("utf-8")

    def check_password(self, raw_password):
        return bcrypt.check_password_hash(self.password_hash, raw_password)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "college": self.college,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class StudentProfile(db.Model):
    __tablename__ = "student_profiles"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    bio = db.Column(db.String(500))
    availability_hours = db.Column(db.Integer, default=0)
    experience_level = db.Column(db.String(20), default="beginner")
    department = db.Column(db.String(100), default="Computer Science")
    preferred_event = db.Column(db.String(150), default="AI Hackathon")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Skill(db.Model):
    __tablename__ = "skills"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    category = db.Column(db.String(50))


class StudentSkill(db.Model):
    __tablename__ = "student_skills"
    __table_args__ = (db.UniqueConstraint("user_id", "skill_id", name="unique_user_skill"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    proficiency = db.Column(db.String(20), default="beginner")


class Interest(db.Model):
    __tablename__ = "interests"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)


class StudentInterest(db.Model):
    __tablename__ = "student_interests"
    __table_args__ = (db.UniqueConstraint("user_id", "interest_id", name="unique_user_interest"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    interest_id = db.Column(db.Integer, db.ForeignKey("interests.id", ondelete="CASCADE"), nullable=False)


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.String(1000))
    difficulty = db.Column(db.String(20), default="medium")
    team_size = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default="open")
    interest_id = db.Column(db.Integer, db.ForeignKey("interests.id"), nullable=True)
    expected_hours_per_week = db.Column(db.Integer, default=5)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ProjectSkill(db.Model):
    __tablename__ = "project_skills"
    __table_args__ = (db.UniqueConstraint("project_id", "skill_id", name="unique_project_skill"),)

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)


class Match(db.Model):
    __tablename__ = "matches"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    score = db.Column(db.Float, nullable=False)
    skill_match = db.Column(db.Float, default=0)
    interest_match = db.Column(db.Float, default=0)
    availability_match = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# MODULE 4: Team Formation
# ============================================================

class Application(db.Model):
    __tablename__ = "applications"
    __table_args__ = (db.UniqueConstraint("project_id", "user_id", name="unique_project_applicant"),)

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = db.Column(db.String(20), default="pending")
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# MODULE 6: Skill Gap Analysis
# ============================================================

class TargetRole(db.Model):
    __tablename__ = "target_roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)


class TargetRoleSkill(db.Model):
    __tablename__ = "target_role_skills"
    __table_args__ = (db.UniqueConstraint("role_id", "skill_id", name="unique_role_skill"),)

    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey("target_roles.id", ondelete="CASCADE"), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)


# ============================================================
# MODULE 7: Suggested Teammates, Matching & Chat
# ============================================================

class TeammateMatch(db.Model):
    __tablename__ = "team_matches"
    __table_args__ = (
        db.UniqueConstraint("sender_id", "receiver_id", "event_name", name="unique_team_match_request"),
    )

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_name = db.Column(db.String(150), default="AI Hackathon")
    status = db.Column(db.String(20), default="pending")  # "pending", "matched", "rejected"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    message_text = db.Column(db.Text, nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    notif_type = db.Column(db.String(50), default="match")  # "match", "chat", "team", "system"
    is_read = db.Column(db.Boolean, default=False)
    link_action = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Team(db.Model):
    __tablename__ = "teams"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    event_name = db.Column(db.String(150), default="AI Hackathon")
    project_idea = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TeamMember(db.Model):
    __tablename__ = "team_members"
    __table_args__ = (
        db.UniqueConstraint("team_id", "user_id", name="unique_team_member"),
    )

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = db.Column(db.String(100), default="Member")
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

