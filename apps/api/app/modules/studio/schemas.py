# SPDX-License-Identifier: MIT
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import Document


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WriteupCreate(StrictInput):
    title: str = Field(min_length=1, max_length=240)
    document: Document | None = None
    challenge_id: str | None = None
    team_id: str | None = None
    template_id: str | None = None
    visibility: Literal["private", "team"] = "private"
    tags: list[str] = Field(default_factory=list, max_length=50)
    tools: list[str] = Field(default_factory=list, max_length=50)
    languages: list[str] = Field(default_factory=list, max_length=30)


class WriteupUpdate(StrictInput):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    document: Document | None = None
    status: Literal["draft", "in_progress", "completed"] | None = None
    visibility: Literal["private", "team"] | None = None
    expected_version: int = Field(ge=1)
    message: str = Field(default="", max_length=500)
    tags: list[str] | None = Field(default=None, max_length=50)
    tools: list[str] | None = Field(default=None, max_length=50)
    languages: list[str] | None = Field(default=None, max_length=30)


class RestoreInput(StrictInput):
    expected_version: int = Field(ge=1)


class EvidenceLink(StrictInput):
    evidence_id: str
    section_id: str | None = None
    position: int = Field(default=0, ge=0, le=10000)


class ExportInput(StrictInput):
    format: Literal["markdown", "html", "pdf", "json"]
    include_evidences: bool = False
    include_originals: bool = False
    cover: bool = True
    theme: Literal["dark", "light"] = "light"
    brand: str = Field(default="CTF Writeup Studio", max_length=160)
    header: str = Field(default="", max_length=240)
    footer: str = Field(default="", max_length=240)


class PublishInput(StrictInput):
    visibility: Literal["private", "team", "public"]
    expected_version: int = Field(ge=1)
    confirm_public: bool = False
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    expires_at: datetime | None = None


TASKS = Literal[
    "structure_notes", "organize_logs", "suggest_sections", "explain_commands",
    "summarize_evidence", "relate_evidence", "documentation_gaps", "improve_writing",
    "executive_summary", "suggest_references", "compare_versions", "review_consistency",
    "draft_report", "ask_evidence",
]


class AIInput(StrictInput):
    task: TASKS
    notes: str = Field(default="", max_length=100000)
    writeup_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list, max_length=30)
    provider: Literal["ollama", "external"] = "ollama"
    external_consent: bool = False
