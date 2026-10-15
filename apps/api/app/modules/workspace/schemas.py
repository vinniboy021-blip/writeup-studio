# SPDX-License-Identifier: MIT
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas import Document

RoleName = Literal["manager", "editor", "reviewer", "viewer"]
Visibility = Literal["private", "team"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Named(Input):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=50000)


class Resource(Input):
    team_id: str | None = None
    visibility: Visibility = "private"
    tags: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("team_id")
    @classmethod
    def valid_uuid(cls, value):
        if value is not None:
            return str(UUID(value))
        return value

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value):
        if any(not tag.strip() or len(tag) > 80 for tag in value):
            raise ValueError("Tags devem ter entre 1 e 80 caracteres")
        return list(dict.fromkeys(tag.strip() for tag in value))


class CompetitionCreate(Named, Resource):
    platform: str = Field(default="", max_length=120)
    url: str = Field(default="", max_length=500)
    start_at: datetime | None = None
    end_at: datetime | None = None
    status: Literal["planned", "active", "completed", "archived"] = "planned"
    mode: str = Field(default="online", max_length=40)

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        if value and not value.startswith(("https://", "http://")):
            raise ValueError("Use uma URL HTTP ou HTTPS")
        return value

    @field_validator("start_at", "end_at")
    @classmethod
    def utc_datetime(cls, value):
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("Informe o fuso horário da data")
            return value.astimezone(timezone.utc)
        return value

    @model_validator(mode="after")
    def dates_order(self):
        if self.start_at and self.end_at and self.end_at < self.start_at:
            raise ValueError("Data final anterior à inicial")
        return self


class CompetitionPatch(Input):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=50000)
    platform: str | None = Field(default=None, max_length=120)
    url: str | None = Field(default=None, max_length=500)
    start_at: datetime | None = None
    end_at: datetime | None = None
    status: Literal["planned", "active", "completed", "archived"] | None = None
    mode: str | None = Field(default=None, max_length=40)
    tags: list[str] | None = Field(default=None, max_length=50)
    team_id: str | None = None
    visibility: Visibility | None = None


class ChallengeCreate(Named, Resource):
    competition_id: str | None = None
    category: str = Field(default="Misc", min_length=1, max_length=80)
    difficulty: Literal["easy", "medium", "hard", "insane", "unknown"] = "medium"
    points: int = Field(default=0, ge=0, le=10000000)
    status: Literal["todo", "in_progress", "solved", "blocked", "archived"] = "todo"
    references: list[str] = Field(default_factory=list, max_length=100)
    notes: str = Field(default="", max_length=100000)
    assignee_ids: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("references")
    @classmethod
    def safe_references(cls, values):
        if any(len(value) > 2000 or not value.startswith(("https://", "http://")) for value in values):
            raise ValueError("Referências devem ser URLs HTTP/HTTPS")
        return values


class ChallengePatch(Input):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=50000)
    competition_id: str | None = None
    category: str | None = Field(default=None, min_length=1, max_length=80)
    difficulty: Literal["easy", "medium", "hard", "insane", "unknown"] | None = None
    points: int | None = Field(default=None, ge=0, le=10000000)
    status: Literal["todo", "in_progress", "solved", "blocked", "archived"] | None = None
    references: list[str] | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=100000)
    assignee_ids: list[str] | None = Field(default=None, max_length=50)
    tags: list[str] | None = Field(default=None, max_length=50)
    team_id: str | None = None
    visibility: Visibility | None = None


class TeamCreate(Named):
    name: str = Field(min_length=2, max_length=160)


class TeamPatch(Input):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=50000)


class MemberInput(Input):
    user_id: str
    role: RoleName = "viewer"


class MemberPatch(Input):
    role: RoleName


class CompetitionParticipant(Input):
    user_id: str
    role: Literal["participant", "captain"] = "participant"


class InviteInput(Input):
    email: str = Field(min_length=3, max_length=320)
    role: RoleName = "viewer"

    @field_validator("email")
    @classmethod
    def email_format(cls, value):
        value = value.lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Email inválido")
        return value


class AcceptInvite(Input):
    token: str = Field(min_length=20, max_length=200)


class CategoryCreate(Input):
    name: str = Field(min_length=1, max_length=80)
    team_id: str | None = None


class TemplateCreate(Named):
    name: str = Field(min_length=1, max_length=180)
    team_id: str | None = None
    document: Document


class TemplatePatch(Input):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=50000)
    document: Document | None = None


class TemplateImport(Input):
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=50000)
    document: Document
    team_id: str | None = None


class CommentCreate(Input):
    body: str = Field(min_length=1, max_length=20000)
    section_id: str | None = Field(default=None, max_length=100)


class CommentPatch(Input):
    resolved: bool


class ReviewCreate(Input):
    reviewer_id: str
    comment: str = Field(default="", max_length=20000)


class ReviewDecision(Input):
    decision: Literal["approved", "changes_requested"]
    comment: str = Field(default="", max_length=20000)


class NotificationPatch(Input):
    read: bool = True


class AdminUserPatch(Input):
    is_active: bool | None = None
    is_admin: bool | None = None


class SettingsPatch(Input):
    registration_enabled: bool | None = None
    retention_days: int | None = Field(default=None, ge=1, le=36500)
    backup_rpo_hours: int | None = Field(default=None, ge=1, le=8760)
    backup_rto_hours: int | None = Field(default=None, ge=1, le=8760)
    ai_enabled: bool | None = None
