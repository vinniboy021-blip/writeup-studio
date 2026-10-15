"""Shared relational model for the modular monolith."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime, utcnow


def uuidstr() -> str:
    return str(uuid.uuid4())


class Identified:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuidstr)


class Created:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class Updated(Created):
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False)


class Scoped(Identified, Updated):
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="private", nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)


class User(Identified, Created, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SessionModel(Identified, Created, Base):
    __tablename__ = "sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)
    user_agent: Mapped[str] = mapped_column(String(500), default="")


class Team(Identified, Updated, Base):
    __tablename__ = "teams"
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)


class TeamMember(Identified, Created, Base):
    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_member"),
        CheckConstraint("role IN ('manager','editor','reviewer','viewer')", name="ck_team_member_role"),
    )
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(30), default="viewer")


class TeamInvite(Identified, Created, Base):
    __tablename__ = "team_invites"
    __table_args__ = (CheckConstraint("role IN ('manager','editor','reviewer','viewer')", name="ck_team_invite_role"),)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[str] = mapped_column(String(30))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class Role(Identified, Base):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(40), unique=True)
    description: Mapped[str] = mapped_column(String(200), default="")


class Permission(Identified, Base):
    __tablename__ = "permissions"
    name: Mapped[str] = mapped_column(String(80), unique=True)


class RolePermission(Identified, Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    permission_id: Mapped[str] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"))


class Competition(Scoped, Base):
    __tablename__ = "competitions"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_competition_version"),
        CheckConstraint("visibility IN ('private','team')", name="ck_competition_visibility"),
        CheckConstraint("visibility != 'team' OR team_id IS NOT NULL", name="ck_competition_team"),
        CheckConstraint("end_at IS NULL OR start_at IS NULL OR end_at >= start_at", name="ck_competition_dates"),
    )
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    platform: Mapped[str] = mapped_column(String(120), default="")
    url: Mapped[str] = mapped_column(String(500), default="")
    start_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    end_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(30), default="planned", index=True)
    mode: Mapped[str] = mapped_column(String(40), default="jeopardy")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)


class CompetitionMember(Identified, Created, Base):
    __tablename__ = "competition_members"
    __table_args__ = (UniqueConstraint("competition_id", "user_id", name="uq_competition_member"),)
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(30), default="participant")


class Challenge(Scoped, Base):
    __tablename__ = "challenges"
    __table_args__ = (
        CheckConstraint("points >= 0", name="ck_challenge_points"),
        CheckConstraint("version >= 1", name="ck_challenge_version"),
        CheckConstraint("visibility IN ('private','team')", name="ck_challenge_visibility"),
        CheckConstraint("visibility != 'team' OR team_id IS NOT NULL", name="ck_challenge_team"),
        Index("ix_challenge_category_status", "category", "status"),
    )
    competition_id: Mapped[str | None] = mapped_column(ForeignKey("competitions.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    difficulty: Mapped[str] = mapped_column(String(40), default="medium")
    points: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="todo", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    references: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)


class ChallengeAssignment(Identified, Created, Base):
    __tablename__ = "challenge_assignments"
    __table_args__ = (UniqueConstraint("challenge_id", "user_id", name="uq_challenge_assignment"),)
    challenge_id: Mapped[str] = mapped_column(ForeignKey("challenges.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    assigned_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class Writeup(Scoped, Base):
    __tablename__ = "writeups"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_writeup_version"),
        CheckConstraint("visibility IN ('private','team')", name="ck_writeup_visibility"),
        CheckConstraint("visibility != 'team' OR team_id IS NOT NULL", name="ck_writeup_team"),
    )
    challenge_id: Mapped[str | None] = mapped_column(ForeignKey("challenges.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(String(240), index=True)
    document: Mapped[dict] = mapped_column(JSON, default=lambda: {"schema_version": 1, "sections": []})
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    approved_revision: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    tags: Mapped[list] = mapped_column(JSON, default=list)
    tools: Mapped[list] = mapped_column(JSON, default=list)
    languages: Mapped[list] = mapped_column(JSON, default=list)


class WriteupRevision(Identified, Created, Base):
    __tablename__ = "writeup_revisions"
    __table_args__ = (UniqueConstraint("writeup_id", "version", name="uq_writeup_revision"),)
    writeup_id: Mapped[str] = mapped_column(ForeignKey("writeups.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(240))
    document: Mapped[dict] = mapped_column(JSON)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    message: Mapped[str] = mapped_column(String(500), default="")


class WriteupTemplate(Identified, Updated, Base):
    __tablename__ = "writeup_templates"
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="private")
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    document: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)


class TemplateRevision(Identified, Created, Base):
    __tablename__ = "template_revisions"
    __table_args__ = (UniqueConstraint("template_id", "version", name="uq_template_revision"),)
    template_id: Mapped[str] = mapped_column(ForeignKey("writeup_templates.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(180), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    document: Mapped[dict] = mapped_column(JSON)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class Evidence(Scoped, Base):
    __tablename__ = "evidences"
    __table_args__ = (
        CheckConstraint("size >= 0", name="ck_evidence_size"),
        CheckConstraint("version >= 1", name="ck_evidence_version"),
        CheckConstraint("visibility IN ('private','team')", name="ck_evidence_visibility"),
        CheckConstraint("visibility != 'team' OR team_id IS NOT NULL", name="ck_evidence_team"),
    )
    challenge_id: Mapped[str | None] = mapped_column(ForeignKey("challenges.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(500))
    captured_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(120))
    extension: Mapped[str] = mapped_column(String(20), default="")
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, default=1)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class EvidenceVersion(Identified, Created, Base):
    __tablename__ = "evidence_versions"
    __table_args__ = (UniqueConstraint("evidence_id", "version", "kind", name="uq_evidence_version"),)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidences.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(120))
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(30), default="annotated")


class EvidenceAnnotation(Identified, Created, Base):
    __tablename__ = "evidence_annotations"
    __table_args__ = (UniqueConstraint("evidence_id", "version", name="uq_evidence_annotation"),)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidences.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)


class EvidenceEvent(Identified, Created, Base):
    __tablename__ = "evidence_events"
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidences.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    event_type: Mapped[str] = mapped_column(String(60))
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class WriteupEvidence(Identified, Base):
    __tablename__ = "writeup_evidences"
    __table_args__ = (UniqueConstraint("writeup_id", "evidence_id", name="uq_writeup_evidence"),)
    writeup_id: Mapped[str] = mapped_column(ForeignKey("writeups.id", ondelete="CASCADE"), index=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidences.id", ondelete="RESTRICT"), index=True)
    section_id: Mapped[str | None] = mapped_column(String(100))
    position: Mapped[int] = mapped_column(Integer, default=0)


class Comment(Identified, Created, Base):
    __tablename__ = "comments"
    writeup_id: Mapped[str] = mapped_column(ForeignKey("writeups.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    body: Mapped[str] = mapped_column(Text)
    section_id: Mapped[str | None] = mapped_column(String(100))
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class ReviewRequest(Identified, Created, Base):
    __tablename__ = "review_requests"
    writeup_id: Mapped[str] = mapped_column(ForeignKey("writeups.id", ondelete="CASCADE"), index=True)
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    version: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Notification(Identified, Created, Base):
    __tablename__ = "notifications"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    entity_id: Mapped[str | None] = mapped_column(String(36))
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)


class Export(Identified, Updated, Base):
    __tablename__ = "exports"
    writeup_id: Mapped[str] = mapped_column(ForeignKey("writeups.id", ondelete="CASCADE"), index=True)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    format: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    storage_key: Mapped[str | None] = mapped_column(String(500))
    error: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)


class AIJob(Identified, Updated, Base):
    __tablename__ = "ai_jobs"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"))
    writeup_id: Mapped[str | None] = mapped_column(ForeignKey("writeups.id", ondelete="RESTRICT"), index=True)
    task: Mapped[str] = mapped_column(String(80))
    provider: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    input_data: Mapped[dict] = mapped_column(JSON)
    output_data: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    config_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    external_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)


class Publication(Identified, Created, Base):
    __tablename__ = "publications"
    writeup_id: Mapped[str] = mapped_column(ForeignKey("writeups.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(240))
    document: Mapped[dict] = mapped_column(JSON)
    evidence_manifest: Mapped[list] = mapped_column(JSON, default=list)
    visibility: Mapped[str] = mapped_column(String(20), default="private", index=True)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class AuditLog(Identified, Created, Base):
    __tablename__ = "audit_logs"
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)


class ApplicationSetting(Base):
    __tablename__ = "application_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class Category(Identified, Created, Base):
    __tablename__ = "categories"
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(80), index=True)
    description: Mapped[str] = mapped_column(String(500), default="")


class Tag(Identified, Base):
    __tablename__ = "tags"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_tag_owner_name"),)


# Source-compatible names used by earlier releases.
Revision = WriteupRevision
Template = WriteupTemplate
Review = ReviewRequest
Annotation = EvidenceAnnotation
