"""Initial relational schema. Supports adoption of legacy create_all databases."""

from alembic import op
import sqlalchemy as sa
import app.db

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    if op.get_context().as_sql:
        existing = set()
    else:
        existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "permissions" not in existing:
        op.create_table(
            "permissions",
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )
    if "roles" not in existing:
        op.create_table(
            "roles",
            sa.Column("name", sa.String(length=40), nullable=False),
            sa.Column("description", sa.String(length=200), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )
    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("email", sa.String(length=320), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("is_admin", sa.Boolean(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if "users" not in existing:
        op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    if "application_settings" not in existing:
        op.create_table(
            "application_settings",
            sa.Column("key", sa.String(length=100), nullable=False),
            sa.Column("value", sa.JSON(), nullable=False),
            sa.Column("updated_by", sa.String(length=36), nullable=True),
            sa.Column("updated_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("key"),
        )
    if "audit_logs" not in existing:
        op.create_table(
            "audit_logs",
            sa.Column("actor_id", sa.String(length=36), nullable=True),
            sa.Column("action", sa.String(length=100), nullable=False),
            sa.Column("entity_type", sa.String(length=80), nullable=False),
            sa.Column("entity_id", sa.String(length=100), nullable=False),
            sa.Column("details", sa.JSON(), nullable=False),
            sa.Column("correlation_id", sa.String(length=64), nullable=True),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    if "audit_logs" not in existing:
        op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"], unique=False)
        op.create_index(op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"], unique=False)
        op.create_index(op.f("ix_audit_logs_correlation_id"), "audit_logs", ["correlation_id"], unique=False)
    if "notifications" not in existing:
        op.create_table(
            "notifications",
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("kind", sa.String(length=60), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("entity_id", sa.String(length=36), nullable=True),
            sa.Column("read_at", app.db.UTCDateTime(timezone=True), nullable=True),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    if "notifications" not in existing:
        op.create_index(op.f("ix_notifications_read_at"), "notifications", ["read_at"], unique=False)
        op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False)
    if "role_permissions" not in existing:
        op.create_table(
            "role_permissions",
            sa.Column("role_id", sa.String(length=36), nullable=False),
            sa.Column("permission_id", sa.String(length=36), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
        )
    if "sessions" not in existing:
        op.create_table(
            "sessions",
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("csrf_token", sa.String(length=64), nullable=False),
            sa.Column("expires_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", app.db.UTCDateTime(timezone=True), nullable=True),
            sa.Column("user_agent", sa.String(length=500), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    if "sessions" not in existing:
        op.create_index(op.f("ix_sessions_expires_at"), "sessions", ["expires_at"], unique=False)
        op.create_index(op.f("ix_sessions_revoked_at"), "sessions", ["revoked_at"], unique=False)
        op.create_index(op.f("ix_sessions_token_hash"), "sessions", ["token_hash"], unique=True)
        op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    if "tags" not in existing:
        op.create_table(
            "tags",
            sa.Column("owner_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("owner_id", "name", name="uq_tag_owner_name"),
        )
    if "teams" not in existing:
        op.create_table(
            "teams",
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("owner_id", sa.String(length=36), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("updated_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
        )
    if "teams" not in existing:
        op.create_index(op.f("ix_teams_owner_id"), "teams", ["owner_id"], unique=False)
    if "categories" not in existing:
        op.create_table(
            "categories",
            sa.Column("owner_id", sa.String(length=36), nullable=True),
            sa.Column("team_id", sa.String(length=36), nullable=True),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("description", sa.String(length=500), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
        )
    if "categories" not in existing:
        op.create_index(op.f("ix_categories_name"), "categories", ["name"], unique=False)
        op.create_index(op.f("ix_categories_owner_id"), "categories", ["owner_id"], unique=False)
        op.create_index(op.f("ix_categories_team_id"), "categories", ["team_id"], unique=False)
    if "competitions" not in existing:
        op.create_table(
            "competitions",
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("platform", sa.String(length=120), nullable=False),
            sa.Column("url", sa.String(length=500), nullable=False),
            sa.Column("start_at", app.db.UTCDateTime(timezone=True), nullable=True),
            sa.Column("end_at", app.db.UTCDateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("mode", sa.String(length=40), nullable=False),
            sa.Column("tags", sa.JSON(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("owner_id", sa.String(length=36), nullable=False),
            sa.Column("team_id", sa.String(length=36), nullable=True),
            sa.Column("visibility", sa.String(length=20), nullable=False),
            sa.Column("deleted_at", app.db.UTCDateTime(timezone=True), nullable=True),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("updated_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.CheckConstraint("visibility != 'team' OR team_id IS NOT NULL", name="ck_competition_team"),
            sa.CheckConstraint("visibility IN ('private','team')", name="ck_competition_visibility"),
            sa.CheckConstraint("end_at IS NULL OR start_at IS NULL OR end_at >= start_at", name="ck_competition_dates"),
            sa.CheckConstraint("version >= 1", name="ck_competition_version"),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
        )
    if "competitions" not in existing:
        op.create_index(op.f("ix_competitions_deleted_at"), "competitions", ["deleted_at"], unique=False)
        op.create_index(op.f("ix_competitions_name"), "competitions", ["name"], unique=False)
        op.create_index(op.f("ix_competitions_owner_id"), "competitions", ["owner_id"], unique=False)
        op.create_index(op.f("ix_competitions_status"), "competitions", ["status"], unique=False)
        op.create_index(op.f("ix_competitions_team_id"), "competitions", ["team_id"], unique=False)
        op.create_index(op.f("ix_competitions_visibility"), "competitions", ["visibility"], unique=False)
    if "team_invites" not in existing:
        op.create_table(
            "team_invites",
            sa.Column("team_id", sa.String(length=36), nullable=False),
            sa.Column("email", sa.String(length=320), nullable=False),
            sa.Column("role", sa.String(length=30), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.Column("accepted_at", app.db.UTCDateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.String(length=36), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.CheckConstraint("role IN ('manager','editor','reviewer','viewer')", name="ck_team_invite_role"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
        )
    if "team_invites" not in existing:
        op.create_index(op.f("ix_team_invites_email"), "team_invites", ["email"], unique=False)
        op.create_index(op.f("ix_team_invites_team_id"), "team_invites", ["team_id"], unique=False)
    if "team_members" not in existing:
        op.create_table(
            "team_members",
            sa.Column("team_id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("role", sa.String(length=30), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.CheckConstraint("role IN ('manager','editor','reviewer','viewer')", name="ck_team_member_role"),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("team_id", "user_id", name="uq_team_member"),
        )
    if "team_members" not in existing:
        op.create_index(op.f("ix_team_members_team_id"), "team_members", ["team_id"], unique=False)
        op.create_index(op.f("ix_team_members_user_id"), "team_members", ["user_id"], unique=False)
    if "writeup_templates" not in existing:
        op.create_table(
            "writeup_templates",
            sa.Column("owner_id", sa.String(length=36), nullable=True),
            sa.Column("team_id", sa.String(length=36), nullable=True),
            sa.Column("visibility", sa.String(length=20), nullable=False),
            sa.Column("deleted_at", app.db.UTCDateTime(timezone=True), nullable=True),
            sa.Column("name", sa.String(length=180), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("document", sa.JSON(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("updated_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
        )
    if "writeup_templates" not in existing:
        op.create_index(op.f("ix_writeup_templates_owner_id"), "writeup_templates", ["owner_id"], unique=False)
        op.create_index(op.f("ix_writeup_templates_team_id"), "writeup_templates", ["team_id"], unique=False)
    if "challenges" not in existing:
        op.create_table(
            "challenges",
            sa.Column("competition_id", sa.String(length=36), nullable=True),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("category", sa.String(length=80), nullable=False),
            sa.Column("difficulty", sa.String(length=40), nullable=False),
            sa.Column("points", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("references", sa.JSON(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False),
            sa.Column("tags", sa.JSON(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("owner_id", sa.String(length=36), nullable=False),
            sa.Column("team_id", sa.String(length=36), nullable=True),
            sa.Column("visibility", sa.String(length=20), nullable=False),
            sa.Column("deleted_at", app.db.UTCDateTime(timezone=True), nullable=True),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("updated_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.CheckConstraint("visibility != 'team' OR team_id IS NOT NULL", name="ck_challenge_team"),
            sa.CheckConstraint("visibility IN ('private','team')", name="ck_challenge_visibility"),
            sa.CheckConstraint("points >= 0", name="ck_challenge_points"),
            sa.CheckConstraint("version >= 1", name="ck_challenge_version"),
            sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
        )
    if "challenges" not in existing:
        op.create_index("ix_challenge_category_status", "challenges", ["category", "status"], unique=False)
        op.create_index(op.f("ix_challenges_category"), "challenges", ["category"], unique=False)
        op.create_index(op.f("ix_challenges_competition_id"), "challenges", ["competition_id"], unique=False)
        op.create_index(op.f("ix_challenges_deleted_at"), "challenges", ["deleted_at"], unique=False)
        op.create_index(op.f("ix_challenges_name"), "challenges", ["name"], unique=False)
        op.create_index(op.f("ix_challenges_owner_id"), "challenges", ["owner_id"], unique=False)
        op.create_index(op.f("ix_challenges_status"), "challenges", ["status"], unique=False)
        op.create_index(op.f("ix_challenges_team_id"), "challenges", ["team_id"], unique=False)
        op.create_index(op.f("ix_challenges_visibility"), "challenges", ["visibility"], unique=False)
    if "competition_members" not in existing:
        op.create_table(
            "competition_members",
            sa.Column("competition_id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("role", sa.String(length=30), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("competition_id", "user_id", name="uq_competition_member"),
        )
    if "competition_members" not in existing:
        op.create_index(
            op.f("ix_competition_members_competition_id"), "competition_members", ["competition_id"], unique=False
        )
        op.create_index(op.f("ix_competition_members_user_id"), "competition_members", ["user_id"], unique=False)
    if "template_revisions" not in existing:
        op.create_table(
            "template_revisions",
            sa.Column("template_id", sa.String(length=36), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=180), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("document", sa.JSON(), nullable=False),
            sa.Column("author_id", sa.String(length=36), nullable=True),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["template_id"], ["writeup_templates.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("template_id", "version", name="uq_template_revision"),
        )
    if "template_revisions" not in existing:
        op.create_index(op.f("ix_template_revisions_template_id"), "template_revisions", ["template_id"], unique=False)
    if "challenge_assignments" not in existing:
        op.create_table(
            "challenge_assignments",
            sa.Column("challenge_id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("assigned_by", sa.String(length=36), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["challenge_id"], ["challenges.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("challenge_id", "user_id", name="uq_challenge_assignment"),
        )
    if "challenge_assignments" not in existing:
        op.create_index(
            op.f("ix_challenge_assignments_challenge_id"), "challenge_assignments", ["challenge_id"], unique=False
        )
        op.create_index(op.f("ix_challenge_assignments_user_id"), "challenge_assignments", ["user_id"], unique=False)
    if "evidences" not in existing:
        op.create_table(
            "evidences",
            sa.Column("challenge_id", sa.String(length=36), nullable=True),
            sa.Column("name", sa.String(length=240), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("origin", sa.String(length=500), nullable=False),
            sa.Column("captured_at", app.db.UTCDateTime(timezone=True), nullable=True),
            sa.Column("received_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("size", sa.Integer(), nullable=False),
            sa.Column("mime_type", sa.String(length=120), nullable=False),
            sa.Column("extension", sa.String(length=20), nullable=False),
            sa.Column("storage_key", sa.String(length=500), nullable=False),
            sa.Column("thumbnail_key", sa.String(length=500), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("tags", sa.JSON(), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("owner_id", sa.String(length=36), nullable=False),
            sa.Column("team_id", sa.String(length=36), nullable=True),
            sa.Column("visibility", sa.String(length=20), nullable=False),
            sa.Column("deleted_at", app.db.UTCDateTime(timezone=True), nullable=True),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("updated_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.CheckConstraint("visibility != 'team' OR team_id IS NOT NULL", name="ck_evidence_team"),
            sa.CheckConstraint("visibility IN ('private','team')", name="ck_evidence_visibility"),
            sa.CheckConstraint("size >= 0", name="ck_evidence_size"),
            sa.CheckConstraint("version >= 1", name="ck_evidence_version"),
            sa.ForeignKeyConstraint(["challenge_id"], ["challenges.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("storage_key"),
        )
    if "evidences" not in existing:
        op.create_index(op.f("ix_evidences_challenge_id"), "evidences", ["challenge_id"], unique=False)
        op.create_index(op.f("ix_evidences_deleted_at"), "evidences", ["deleted_at"], unique=False)
        op.create_index(op.f("ix_evidences_owner_id"), "evidences", ["owner_id"], unique=False)
        op.create_index(op.f("ix_evidences_sha256"), "evidences", ["sha256"], unique=False)
        op.create_index(op.f("ix_evidences_team_id"), "evidences", ["team_id"], unique=False)
        op.create_index(op.f("ix_evidences_visibility"), "evidences", ["visibility"], unique=False)
    if "writeups" not in existing:
        op.create_table(
            "writeups",
            sa.Column("challenge_id", sa.String(length=36), nullable=True),
            sa.Column("title", sa.String(length=240), nullable=False),
            sa.Column("document", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("approved_revision", sa.Integer(), nullable=True),
            sa.Column("published_at", app.db.UTCDateTime(timezone=True), nullable=True),
            sa.Column("tags", sa.JSON(), nullable=False),
            sa.Column("tools", sa.JSON(), nullable=False),
            sa.Column("languages", sa.JSON(), nullable=False),
            sa.Column("owner_id", sa.String(length=36), nullable=False),
            sa.Column("team_id", sa.String(length=36), nullable=True),
            sa.Column("visibility", sa.String(length=20), nullable=False),
            sa.Column("deleted_at", app.db.UTCDateTime(timezone=True), nullable=True),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("updated_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.CheckConstraint("visibility != 'team' OR team_id IS NOT NULL", name="ck_writeup_team"),
            sa.CheckConstraint("visibility IN ('private','team')", name="ck_writeup_visibility"),
            sa.CheckConstraint("version >= 1", name="ck_writeup_version"),
            sa.ForeignKeyConstraint(["challenge_id"], ["challenges.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
        )
    if "writeups" not in existing:
        op.create_index(op.f("ix_writeups_challenge_id"), "writeups", ["challenge_id"], unique=False)
        op.create_index(op.f("ix_writeups_deleted_at"), "writeups", ["deleted_at"], unique=False)
        op.create_index(op.f("ix_writeups_owner_id"), "writeups", ["owner_id"], unique=False)
        op.create_index(op.f("ix_writeups_status"), "writeups", ["status"], unique=False)
        op.create_index(op.f("ix_writeups_team_id"), "writeups", ["team_id"], unique=False)
        op.create_index(op.f("ix_writeups_title"), "writeups", ["title"], unique=False)
        op.create_index(op.f("ix_writeups_visibility"), "writeups", ["visibility"], unique=False)
    if "ai_jobs" not in existing:
        op.create_table(
            "ai_jobs",
            sa.Column("owner_id", sa.String(length=36), nullable=False),
            sa.Column("team_id", sa.String(length=36), nullable=True),
            sa.Column("writeup_id", sa.String(length=36), nullable=True),
            sa.Column("task", sa.String(length=80), nullable=False),
            sa.Column("provider", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("input_data", sa.JSON(), nullable=False),
            sa.Column("output_data", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("config_snapshot", sa.JSON(), nullable=False),
            sa.Column("external_consent", sa.Boolean(), nullable=False),
            sa.Column("cancel_requested", sa.Boolean(), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("updated_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["writeup_id"], ["writeups.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
        )
    if "ai_jobs" not in existing:
        op.create_index(op.f("ix_ai_jobs_owner_id"), "ai_jobs", ["owner_id"], unique=False)
        op.create_index(op.f("ix_ai_jobs_status"), "ai_jobs", ["status"], unique=False)
        op.create_index(op.f("ix_ai_jobs_writeup_id"), "ai_jobs", ["writeup_id"], unique=False)
    if "comments" not in existing:
        op.create_table(
            "comments",
            sa.Column("writeup_id", sa.String(length=36), nullable=False),
            sa.Column("author_id", sa.String(length=36), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("section_id", sa.String(length=100), nullable=True),
            sa.Column("resolved_at", app.db.UTCDateTime(timezone=True), nullable=True),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["writeup_id"], ["writeups.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    if "comments" not in existing:
        op.create_index(op.f("ix_comments_writeup_id"), "comments", ["writeup_id"], unique=False)
    if "evidence_annotations" not in existing:
        op.create_table(
            "evidence_annotations",
            sa.Column("evidence_id", sa.String(length=36), nullable=False),
            sa.Column("author_id", sa.String(length=36), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("data", sa.JSON(), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["evidence_id"], ["evidences.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("evidence_id", "version", name="uq_evidence_annotation"),
        )
    if "evidence_annotations" not in existing:
        op.create_index(
            op.f("ix_evidence_annotations_evidence_id"), "evidence_annotations", ["evidence_id"], unique=False
        )
    if "evidence_events" not in existing:
        op.create_table(
            "evidence_events",
            sa.Column("evidence_id", sa.String(length=36), nullable=False),
            sa.Column("actor_id", sa.String(length=36), nullable=False),
            sa.Column("event_type", sa.String(length=60), nullable=False),
            sa.Column("details", sa.JSON(), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["evidence_id"], ["evidences.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    if "evidence_events" not in existing:
        op.create_index(op.f("ix_evidence_events_evidence_id"), "evidence_events", ["evidence_id"], unique=False)
    if "evidence_versions" not in existing:
        op.create_table(
            "evidence_versions",
            sa.Column("evidence_id", sa.String(length=36), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("storage_key", sa.String(length=500), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("size", sa.Integer(), nullable=False),
            sa.Column("mime_type", sa.String(length=120), nullable=False),
            sa.Column("author_id", sa.String(length=36), nullable=False),
            sa.Column("kind", sa.String(length=30), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["evidence_id"], ["evidences.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("evidence_id", "version", "kind", name="uq_evidence_version"),
            sa.UniqueConstraint("storage_key"),
        )
    if "evidence_versions" not in existing:
        op.create_index(op.f("ix_evidence_versions_evidence_id"), "evidence_versions", ["evidence_id"], unique=False)
    if "exports" not in existing:
        op.create_table(
            "exports",
            sa.Column("writeup_id", sa.String(length=36), nullable=False),
            sa.Column("requested_by", sa.String(length=36), nullable=False),
            sa.Column("format", sa.String(length=20), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("options", sa.JSON(), nullable=False),
            sa.Column("storage_key", sa.String(length=500), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("cancel_requested", sa.Boolean(), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("updated_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["writeup_id"], ["writeups.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    if "exports" not in existing:
        op.create_index(op.f("ix_exports_requested_by"), "exports", ["requested_by"], unique=False)
        op.create_index(op.f("ix_exports_status"), "exports", ["status"], unique=False)
        op.create_index(op.f("ix_exports_writeup_id"), "exports", ["writeup_id"], unique=False)
    if "publications" not in existing:
        op.create_table(
            "publications",
            sa.Column("writeup_id", sa.String(length=36), nullable=False),
            sa.Column("owner_id", sa.String(length=36), nullable=False),
            sa.Column("team_id", sa.String(length=36), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=240), nullable=False),
            sa.Column("document", sa.JSON(), nullable=False),
            sa.Column("evidence_manifest", sa.JSON(), nullable=False),
            sa.Column("visibility", sa.String(length=20), nullable=False),
            sa.Column("expires_at", app.db.UTCDateTime(timezone=True), nullable=True),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["writeup_id"], ["writeups.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    if "publications" not in existing:
        op.create_index(op.f("ix_publications_visibility"), "publications", ["visibility"], unique=False)
        op.create_index(op.f("ix_publications_writeup_id"), "publications", ["writeup_id"], unique=False)
    if "review_requests" not in existing:
        op.create_table(
            "review_requests",
            sa.Column("writeup_id", sa.String(length=36), nullable=False),
            sa.Column("requester_id", sa.String(length=36), nullable=False),
            sa.Column("reviewer_id", sa.String(length=36), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("comment", sa.Text(), nullable=False),
            sa.Column("decided_at", app.db.UTCDateTime(timezone=True), nullable=True),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["requester_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["writeup_id"], ["writeups.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    if "review_requests" not in existing:
        op.create_index(op.f("ix_review_requests_reviewer_id"), "review_requests", ["reviewer_id"], unique=False)
        op.create_index(op.f("ix_review_requests_writeup_id"), "review_requests", ["writeup_id"], unique=False)
    if "writeup_evidences" not in existing:
        op.create_table(
            "writeup_evidences",
            sa.Column("writeup_id", sa.String(length=36), nullable=False),
            sa.Column("evidence_id", sa.String(length=36), nullable=False),
            sa.Column("section_id", sa.String(length=100), nullable=True),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.ForeignKeyConstraint(["evidence_id"], ["evidences.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["writeup_id"], ["writeups.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("writeup_id", "evidence_id", name="uq_writeup_evidence"),
        )
    if "writeup_evidences" not in existing:
        op.create_index(op.f("ix_writeup_evidences_evidence_id"), "writeup_evidences", ["evidence_id"], unique=False)
        op.create_index(op.f("ix_writeup_evidences_writeup_id"), "writeup_evidences", ["writeup_id"], unique=False)
    if "writeup_revisions" not in existing:
        op.create_table(
            "writeup_revisions",
            sa.Column("writeup_id", sa.String(length=36), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=240), nullable=False),
            sa.Column("document", sa.JSON(), nullable=False),
            sa.Column("author_id", sa.String(length=36), nullable=False),
            sa.Column("message", sa.String(length=500), nullable=False),
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", app.db.UTCDateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["writeup_id"], ["writeups.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("writeup_id", "version", name="uq_writeup_revision"),
        )
    if "writeup_revisions" not in existing:
        op.create_index(op.f("ix_writeup_revisions_writeup_id"), "writeup_revisions", ["writeup_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_writeup_revisions_writeup_id"), table_name="writeup_revisions")
    op.drop_table("writeup_revisions")
    op.drop_index(op.f("ix_writeup_evidences_writeup_id"), table_name="writeup_evidences")
    op.drop_index(op.f("ix_writeup_evidences_evidence_id"), table_name="writeup_evidences")
    op.drop_table("writeup_evidences")
    op.drop_index(op.f("ix_review_requests_writeup_id"), table_name="review_requests")
    op.drop_index(op.f("ix_review_requests_reviewer_id"), table_name="review_requests")
    op.drop_table("review_requests")
    op.drop_index(op.f("ix_publications_writeup_id"), table_name="publications")
    op.drop_index(op.f("ix_publications_visibility"), table_name="publications")
    op.drop_table("publications")
    op.drop_index(op.f("ix_exports_writeup_id"), table_name="exports")
    op.drop_index(op.f("ix_exports_status"), table_name="exports")
    op.drop_index(op.f("ix_exports_requested_by"), table_name="exports")
    op.drop_table("exports")
    op.drop_index(op.f("ix_evidence_versions_evidence_id"), table_name="evidence_versions")
    op.drop_table("evidence_versions")
    op.drop_index(op.f("ix_evidence_events_evidence_id"), table_name="evidence_events")
    op.drop_table("evidence_events")
    op.drop_index(op.f("ix_evidence_annotations_evidence_id"), table_name="evidence_annotations")
    op.drop_table("evidence_annotations")
    op.drop_index(op.f("ix_comments_writeup_id"), table_name="comments")
    op.drop_table("comments")
    op.drop_index(op.f("ix_ai_jobs_writeup_id"), table_name="ai_jobs")
    op.drop_index(op.f("ix_ai_jobs_status"), table_name="ai_jobs")
    op.drop_index(op.f("ix_ai_jobs_owner_id"), table_name="ai_jobs")
    op.drop_table("ai_jobs")
    op.drop_index(op.f("ix_writeups_visibility"), table_name="writeups")
    op.drop_index(op.f("ix_writeups_title"), table_name="writeups")
    op.drop_index(op.f("ix_writeups_team_id"), table_name="writeups")
    op.drop_index(op.f("ix_writeups_status"), table_name="writeups")
    op.drop_index(op.f("ix_writeups_owner_id"), table_name="writeups")
    op.drop_index(op.f("ix_writeups_deleted_at"), table_name="writeups")
    op.drop_index(op.f("ix_writeups_challenge_id"), table_name="writeups")
    op.drop_table("writeups")
    op.drop_index(op.f("ix_evidences_visibility"), table_name="evidences")
    op.drop_index(op.f("ix_evidences_team_id"), table_name="evidences")
    op.drop_index(op.f("ix_evidences_sha256"), table_name="evidences")
    op.drop_index(op.f("ix_evidences_owner_id"), table_name="evidences")
    op.drop_index(op.f("ix_evidences_deleted_at"), table_name="evidences")
    op.drop_index(op.f("ix_evidences_challenge_id"), table_name="evidences")
    op.drop_table("evidences")
    op.drop_index(op.f("ix_challenge_assignments_user_id"), table_name="challenge_assignments")
    op.drop_index(op.f("ix_challenge_assignments_challenge_id"), table_name="challenge_assignments")
    op.drop_table("challenge_assignments")
    op.drop_index(op.f("ix_template_revisions_template_id"), table_name="template_revisions")
    op.drop_table("template_revisions")
    op.drop_index(op.f("ix_competition_members_user_id"), table_name="competition_members")
    op.drop_index(op.f("ix_competition_members_competition_id"), table_name="competition_members")
    op.drop_table("competition_members")
    op.drop_index(op.f("ix_challenges_visibility"), table_name="challenges")
    op.drop_index(op.f("ix_challenges_team_id"), table_name="challenges")
    op.drop_index(op.f("ix_challenges_status"), table_name="challenges")
    op.drop_index(op.f("ix_challenges_owner_id"), table_name="challenges")
    op.drop_index(op.f("ix_challenges_name"), table_name="challenges")
    op.drop_index(op.f("ix_challenges_deleted_at"), table_name="challenges")
    op.drop_index(op.f("ix_challenges_competition_id"), table_name="challenges")
    op.drop_index(op.f("ix_challenges_category"), table_name="challenges")
    op.drop_index("ix_challenge_category_status", table_name="challenges")
    op.drop_table("challenges")
    op.drop_index(op.f("ix_writeup_templates_team_id"), table_name="writeup_templates")
    op.drop_index(op.f("ix_writeup_templates_owner_id"), table_name="writeup_templates")
    op.drop_table("writeup_templates")
    op.drop_index(op.f("ix_team_members_user_id"), table_name="team_members")
    op.drop_index(op.f("ix_team_members_team_id"), table_name="team_members")
    op.drop_table("team_members")
    op.drop_index(op.f("ix_team_invites_team_id"), table_name="team_invites")
    op.drop_index(op.f("ix_team_invites_email"), table_name="team_invites")
    op.drop_table("team_invites")
    op.drop_index(op.f("ix_competitions_visibility"), table_name="competitions")
    op.drop_index(op.f("ix_competitions_team_id"), table_name="competitions")
    op.drop_index(op.f("ix_competitions_status"), table_name="competitions")
    op.drop_index(op.f("ix_competitions_owner_id"), table_name="competitions")
    op.drop_index(op.f("ix_competitions_name"), table_name="competitions")
    op.drop_index(op.f("ix_competitions_deleted_at"), table_name="competitions")
    op.drop_table("competitions")
    op.drop_index(op.f("ix_categories_team_id"), table_name="categories")
    op.drop_index(op.f("ix_categories_owner_id"), table_name="categories")
    op.drop_index(op.f("ix_categories_name"), table_name="categories")
    op.drop_table("categories")
    op.drop_index(op.f("ix_teams_owner_id"), table_name="teams")
    op.drop_table("teams")
    op.drop_table("tags")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_token_hash"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_revoked_at"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_expires_at"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("role_permissions")
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_read_at"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_audit_logs_correlation_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_action"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("application_settings")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    op.drop_table("roles")
    op.drop_table("permissions")
