"""
SQLAlchemy ORM models.

Phase 2 gave us `User`. Phase 3 (RBAC) adds:

    roles              -- e.g. Admin, Lead, HR, QA, Employee
    permissions        -- fine-grained capability codes, e.g. "users.invite"
    role_permissions   -- many-to-many join between roles and permissions
    user_roles         -- many-to-many join between users and roles
                          (matches the USER_ROLES entity in the ER diagram;
                          a user can hold more than one role at once)

Future modules (Project, Bug, Task, Sprint, Release, ...) can be added as
new model classes in this file, each with a ForeignKey back to User.id for
ownership/audit tracking, without touching the models below.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# RBAC — roles & permissions (Phase 3)
# ---------------------------------------------------------------------------

# Many-to-many join table between roles and permissions. A plain Table
# (not a model class) is enough here since it carries no extra columns
# of its own.
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "permission_id",
        Integer,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Role(Base):
    """A global role, e.g. Admin / Lead / HR / QA / Employee."""

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, index=True, nullable=False)
    description = Column(String(255), nullable=True)
    is_system = Column(
        Boolean, default=True, nullable=False
    )  # system roles seeded by the app aren't deletable from the UI
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    permissions = relationship("Permission", secondary=role_permissions, back_populates="roles")

    # Read-only convenience view of every user holding this role. Writes
    # go through the UserRole association object below (it carries
    # `assigned_at`), not through this collection directly.
    users = relationship("User", secondary="user_roles", viewonly=True, back_populates="roles")
    user_links = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")


class Permission(Base):
    """A single fine-grained capability, e.g. 'users.invite' or 'users.delete'."""

    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(100), unique=True, index=True, nullable=False)
    description = Column(String(255), nullable=True)

    roles = relationship("Role", secondary=role_permissions, back_populates="permissions")


class UserRole(Base):
    """
    Join table between users and roles (matches USER_ROLES in the ER
    diagram). Modeled as a real ORM class rather than a plain Table
    because — per the ER diagram — it carries its own `id` and
    `assigned_at` columns, not just the two foreign keys.
    """

    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
    )

    user = relationship("User", back_populates="role_links")
    role = relationship("Role", back_populates="user_links")


# ---------------------------------------------------------------------------
# User (Phase 2, extended in Phase 3/4)
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # --- Phase 3: RBAC (many-to-many via user_roles) ----------------------
    # Read-only convenience list of this user's Role objects. Writes go
    # through `role_links` / role_service.set_user_roles(), which manage
    # the underlying UserRole rows (and their `assigned_at` timestamps).
    roles = relationship("Role", secondary="user_roles", viewonly=True, back_populates="users")
    role_links = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")

    @property
    def role(self):
        """Backward-compat convenience: the user's first assigned role
        (or None). The frontend's existing pages read `user.role.name`
        from before roles became many-to-many; `roles` below is the full,
        ER-diagram-accurate list backed by the `user_roles` join table.
        """
        return self.roles[0] if self.roles else None

    # --- Phase 4: User management ---------------------------------------
    # Set when an account is created via the admin "Invite user" flow
    # instead of public self-signup. Lets the UI show "Invited" vs
    # "Active" and, later, drive "resend invite" logic.
    invited_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    must_change_password = Column(Boolean, default=False, nullable=False)
    last_login_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    # --- Phase 5: relationships to Projects/Bugs/Tasks -------------------
    owned_projects = relationship(
        "Project", back_populates="owner", foreign_keys="Project.owner_id"
    )
    reported_bugs = relationship(
        "Bug", back_populates="reporter", foreign_keys="Bug.reported_by"
    )
    assigned_bugs = relationship(
        "Bug", back_populates="assignee", foreign_keys="Bug.assigned_to"
    )
    assigned_tasks = relationship(
        "Task", back_populates="assignee", foreign_keys="Task.assigned_to"
    )


# ---------------------------------------------------------------------------
# Projects / Bugs / Tasks / Sprints (Phase 5)
# ---------------------------------------------------------------------------
class Project(Base):
    """A project workspace that Bugs, Tasks and Sprints belong to."""

    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    owner = relationship("User", back_populates="owned_projects", foreign_keys=[owner_id])
    bugs = relationship("Bug", back_populates="project", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    sprints = relationship("Sprint", back_populates="project", cascade="all, delete-orphan")
    # Team membership: who's allowed to access this project and be
    # assigned its tasks/bugs/subtasks. See app/services/project_access.py.
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")


class ProjectMember(Base):
    """Team membership for a project. Admin/Lead (whoever has
    projects.edit) assign users here after creating a project; everyone
    else's access to that project — and eligibility to be assigned its
    tasks/bugs/subtasks — is scoped to this list (see project_access.py).
    """

    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member"),)

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="members")
    user = relationship("User")


class Sprint(Base):
    """A time-boxed sprint that scopes a subset of a project's bugs."""

    __tablename__ = "sprints"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    status = Column(String(30), default="Planned", nullable=False)  # Planned/Active/Completed
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="sprints")
    bugs = relationship("Bug", back_populates="sprint")
    tasks = relationship("Task", back_populates="sprint")


class Bug(Base):
    """A bug/defect, optionally produced by the AI Bug Generator."""

    __tablename__ = "bugs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    sprint_id = Column(Integer, ForeignKey("sprints.id", ondelete="SET NULL"), nullable=True)
    reported_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    title = Column(String(255), nullable=False)
    severity = Column(String(20), nullable=False, default="Medium")  # Critical/High/Medium/Low
    priority = Column(String(10), nullable=False, default="P2")  # P0/P1/P2/P3
    status = Column(String(30), nullable=False, default="Open")  # Open/In Progress/Resolved/Closed

    # --- Extra fields so AI Bug Generator output (BugReportAI) can be
    # persisted as-is instead of being thrown away after generation.
    summary = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    environment = Column(String(255), nullable=True)
    module = Column(String(100), nullable=True)
    bug_type = Column(String(50), nullable=True)
    expected_result = Column(Text, nullable=True)
    actual_result = Column(Text, nullable=True)
    possible_root_cause = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)
    steps_to_reproduce = Column(Text, nullable=True)  # stored as JSON-encoded list
    is_ai_generated = Column(Boolean, default=False, nullable=False)

    # --- Image evidence: the screenshot uploaded to the AI Bug Generator
    # (or attached manually) is persisted on disk under settings.upload_dir
    # and this stores the public URL path so the frontend can render a
    # preview thumbnail wherever the bug is shown (list, detail, etc).
    image_url = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # --- Phase 6: link an (AI-generated or manual) bug to a task, e.g. so
    # the AI Bug Generator's "save" flow can assign the new bug straight
    # onto a task the user picks from a dropdown.
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)

    project = relationship("Project", back_populates="bugs")
    sprint = relationship("Sprint", back_populates="bugs")
    task = relationship("Task", back_populates="bugs", foreign_keys=[task_id])
    reporter = relationship("User", back_populates="reported_bugs", foreign_keys=[reported_by])
    assignee = relationship("User", back_populates="assigned_bugs", foreign_keys=[assigned_to])


class Task(Base):
    """A task within a project, optionally assigned to a user."""

    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    # --- Phase 6: a task can optionally be scoped to a sprint. Nullable —
    # a task doesn't have to be in a sprint (e.g. backlog tasks).
    sprint_id = Column(Integer, ForeignKey("sprints.id", ondelete="SET NULL"), nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Who created this task — mirrors Bug.reported_by. Nullable because
    # existing rows created before this column existed won't have one.
    reported_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="To Do")  # To Do/In Progress/Done
    due_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="tasks")
    sprint = relationship("Sprint", back_populates="tasks")
    assignee = relationship("User", back_populates="assigned_tasks", foreign_keys=[assigned_to])
    reporter = relationship("User", foreign_keys=[reported_by])
    # Bugs saved from the AI Bug Generator (or manually) against this task.
    bugs = relationship("Bug", back_populates="task", foreign_keys="Bug.task_id")
    subtasks = relationship("SubTask", back_populates="task", cascade="all, delete-orphan")


class SubTask(Base):
    """A subtask nested under a Task — matches the hierarchy requested by
    the team lead: Project -> Sprint -> Task -> SubTask. Kept as its own
    table (rather than a self-referencing Task) so a subtask can never
    itself have a project/sprint assigned directly — it always inherits
    those through its parent task.
    """

    __tablename__ = "subtasks"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    assigned_to = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reported_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="To Do")  # To Do/In Progress/Done
    due_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    task = relationship("Task", back_populates="subtasks")
    assignee = relationship("User", foreign_keys=[assigned_to])
    reporter = relationship("User", foreign_keys=[reported_by])


# ---------------------------------------------------------------------------
# Audit Log (tracks who did what, when, across Projects/Sprints/Tasks/
# SubTasks/Bugs) — visible to QA, Lead ("Project Manager") and Admin.
# ---------------------------------------------------------------------------
class AuditLog(Base):
    """One row per tracked action. Deliberately denormalized (stores a
    human-readable `description` alongside the structured fields) so the
    audit trail keeps reading correctly even if the referenced entity is
    later renamed or deleted.
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_name = Column(String(120), nullable=True)  # snapshot, survives actor deletion

    entity_type = Column(String(30), nullable=False)  # Project/Sprint/Task/SubTask/Bug
    entity_id = Column(Integer, nullable=False)
    entity_name = Column(String(255), nullable=True)  # snapshot of title/name at the time

    action = Column(String(30), nullable=False)  # created/updated/moved/status_changed/deleted
    field_changed = Column(String(60), nullable=True)  # e.g. "status"
    old_value = Column(String(255), nullable=True)
    new_value = Column(String(255), nullable=True)

    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    description = Column(String(500), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    actor = relationship("User", foreign_keys=[actor_id])
