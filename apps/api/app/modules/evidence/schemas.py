# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Shape(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    type: Literal["arrow", "rect", "circle", "line", "text", "highlight", "step", "blur", "redact"]
    x: float = Field(ge=0, le=24000, allow_inf_nan=False)
    y: float = Field(ge=0, le=24000, allow_inf_nan=False)
    x2: float | None = Field(default=None, ge=0, le=24000, allow_inf_nan=False)
    y2: float | None = Field(default=None, ge=0, le=24000, allow_inf_nan=False)
    width: float | None = Field(default=None, gt=0, le=24000, allow_inf_nan=False)
    height: float | None = Field(default=None, gt=0, le=24000, allow_inf_nan=False)
    text: str | None = Field(default=None, max_length=2000)
    color: str = Field(default="#ef4444", pattern=r"^#[0-9a-fA-F]{6}$")
    stroke_width: float = Field(default=3, ge=1, le=100, alias="strokeWidth", allow_inf_nan=False)
    number: int | None = Field(default=None, ge=1, le=1000)

    @model_validator(mode="after")
    def required_geometry(self):
        if self.type in {"arrow", "line"} and (self.x2 is None or self.y2 is None):
            raise ValueError("Linha e seta exigem x2/y2")
        if self.type in {"rect", "circle", "highlight", "blur", "redact"} and (
            self.width is None or self.height is None
        ):
            raise ValueError("Forma exige largura e altura")
        if self.type == "text" and not self.text:
            raise ValueError("Texto vazio")
        return self


class Crop(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0, le=24000)
    height: int = Field(gt=0, le=24000)


class AnnotationData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    width: int = Field(gt=0, le=24000)
    height: int = Field(gt=0, le=24000)
    shapes: list[Shape] = Field(default_factory=list, max_length=500)
    crop: Crop | None = None

    @model_validator(mode="after")
    def bounded(self):
        if self.width * self.height > 24_000_000:
            raise ValueError("Imagem acima do limite de pixels")
        if len({shape.id for shape in self.shapes}) != len(self.shapes):
            raise ValueError("IDs das formas devem ser únicos")
        step = 0
        for shape in self.shapes:
            if shape.x >= self.width or shape.y >= self.height:
                raise ValueError("Forma fora da imagem")
            if shape.x2 is not None and shape.x2 > self.width:
                raise ValueError("Coordenada x2 fora da imagem")
            if shape.y2 is not None and shape.y2 > self.height:
                raise ValueError("Coordenada y2 fora da imagem")
            if shape.width is not None and shape.x + shape.width > self.width:
                raise ValueError("Largura fora da imagem")
            if shape.height is not None and shape.y + shape.height > self.height:
                raise ValueError("Altura fora da imagem")
            if shape.type == "step":
                step += 1
                if shape.number is None:
                    shape.number = step
        if self.crop and (self.crop.x + self.crop.width > self.width or self.crop.y + self.crop.height > self.height):
            raise ValueError("Recorte fora da imagem")
        return self


class AnnotationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    data: AnnotationData


class EvidencePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=10000)
    origin: str | None = Field(default=None, max_length=1000)
    captured_at: datetime | None = None
    tags: list[str] | None = Field(default=None, max_length=30)
    metadata: dict | None = None
    visibility: Literal["private", "team"] | None = None

    @field_validator("captured_at")
    @classmethod
    def utc_capture(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Horário declarado deve incluir fuso horário")
        return value.astimezone(timezone.utc) if value else None

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value):
        if value is None:
            return value
        if any(not t.strip() or len(t) > 80 for t in value):
            raise ValueError("Tag inválida")
        return list(dict.fromkeys(t.strip() for t in value))

    @field_validator("metadata")
    @classmethod
    def bounded_metadata(cls, value):
        import json
        if value is not None and len(json.dumps(value, ensure_ascii=False).encode()) > 32768:
            raise ValueError("Metadados acima de 32 KiB")
        return value
