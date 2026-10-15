"""Canonical persisted document and safe API schemas."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import settings


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=240)
    markdown: str = Field(default="", max_length=1000000)


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    sections: list[Section] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_document(self):
        identifiers = [section.id for section in self.sections]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("IDs de seções devem ser únicos")
        if len(json.dumps(self.model_dump(), ensure_ascii=False).encode()) > settings.max_document_bytes:
            raise ValueError("Documento excede o limite de tamanho")
        return self


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    name: str
    is_admin: bool


def canonical_document(value: dict) -> dict:
    return Document.model_validate(value).model_dump()
