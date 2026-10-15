# SPDX-License-Identifier: MIT
from __future__ import annotations

import base64
import io
import json
from datetime import datetime, timezone
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User
from app.modules.evidence.service import create_evidence, evidence_out, get_evidence
from app.modules.evidence.storage import read_object
from app.security import audit, authorize_team, get_actor, rate_limit, require_csrf

from .client import MCPClient, MCPError

router = APIRouter(tags=["Kali MCP"])
DB = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(get_actor)]
Writer = Annotated[User, Depends(require_csrf)]
SUPPORTED = {"system_info", "artifact_hash", "artifact_file", "artifact_strings", "artifact_json_summary"}


def enabled():
    if not settings.kali_enabled or not settings.kali_mcp_url:
        raise HTTPException(503, "Kali MCP está desabilitado")


def make_client():
    return MCPClient(
        settings.kali_mcp_url, settings.kali_mcp_token, settings.kali_timeout_seconds, settings.kali_max_output_bytes
    )


def approved_tools(tools):
    allowed = SUPPORTED.intersection(item.strip() for item in settings.kali_allowed_tools.split(","))
    return [
        {
            "name": item["name"],
            "description": str(item.get("description", ""))[:1000],
            "inputSchema": item.get("inputSchema", {"type": "object"}),
        }
        for item in tools
        if isinstance(item, dict) and item.get("name") in allowed
    ]


@router.get("/kali/status")
async def status(actor: Actor):
    if not settings.kali_enabled:
        return {"enabled": False, "connected": False, "tools": []}
    try:
        async with make_client() as client:
            metadata = await client.initialize()
            tools = approved_tools(await client.tools())
        return {"enabled": True, "connected": True, "tools": tools, "protocol_version": metadata["protocolVersion"]}
    except (httpx.HTTPError, MCPError, ValueError, KeyError):
        return {"enabled": True, "connected": False, "tools": [], "error": "Servidor MCP indisponível"}


@router.get("/kali/tools")
async def tools(actor: Actor):
    enabled()
    result = await status(actor)
    if not result["connected"]:
        raise HTTPException(502, "Servidor MCP indisponível")
    return {"items": result["tools"], "total": len(result["tools"])}


class Run(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal["system_info", "artifact_hash", "artifact_file", "artifact_strings", "artifact_json_summary"]
    arguments: dict = Field(default_factory=dict)
    evidence_id: str | None = None
    team_id: str | None = None
    confirm: bool = False


@router.post("/kali/run", status_code=201)
async def run(data: Run, db: DB, actor: Writer):
    enabled()
    if not data.confirm:
        raise HTTPException(428, "Confirme a execução")
    allowed = {item.strip() for item in settings.kali_allowed_tools.split(",")}
    if data.tool not in allowed:
        raise HTTPException(403, "Ferramenta desabilitada pela operação")
    arguments = {}
    source = None
    if data.tool == "system_info":
        if data.arguments or data.evidence_id:
            raise HTTPException(422, "system_info não aceita argumentos")
        if data.team_id:
            authorize_team(db, actor, data.team_id, "manage")
        elif not actor.is_admin:
            raise HTTPException(403, "Informações do ambiente exigem gestor ou administrador")
    else:
        if not data.evidence_id:
            raise HTTPException(422, "Selecione uma evidência autorizada")
        source = get_evidence(db, actor, data.evidence_id, "write")
        if data.team_id and source.team_id != data.team_id:
            raise HTTPException(422, "Equipe e evidência não correspondem")
        if source.size > settings.kali_max_artifact_bytes:
            raise HTTPException(413, "Evidência excede o limite da integração")
        if data.arguments:
            raise HTTPException(422, "A origem e os parâmetros do artefato são definidos pelo servidor")
        blob = read_object(source.storage_key, settings.kali_max_artifact_bytes)
        arguments = {"artifact_base64": base64.b64encode(blob).decode(), "name": source.name}
    rate_limit("kali:" + actor.id, settings.kali_max_jobs_per_minute, 60)
    started = datetime.now(timezone.utc)
    try:
        async with make_client() as client:
            await client.initialize()
            names = {item["name"] for item in approved_tools(await client.tools())}
            if data.tool not in names:
                raise MCPError("Ferramenta não oferecida pelo servidor")
            result = await client.call(data.tool, arguments)
    except (httpx.HTTPError, MCPError, ValueError, KeyError) as exc:
        audit(
            db,
            actor,
            "kali.failed",
            "evidence",
            source.id if source else actor.id,
            {"tool": data.tool, "error_type": type(exc).__name__},
        )
        db.commit()
        raise HTTPException(502, "Execução MCP falhou ou excedeu o timeout") from exc
    finished = datetime.now(timezone.utc)
    structured = result.get("structuredContent", {})
    stdout = structured.get("stdout", "") if isinstance(structured, dict) else ""
    stderr = structured.get("stderr", "") if isinstance(structured, dict) else ""
    exit_code = structured.get("exit_code") if isinstance(structured, dict) else None
    provenance = {
        "source": "kali-mcp",
        "tool": data.tool,
        "source_evidence_id": source.id if source else None,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "human_review_required": True,
    }
    artifact = json.dumps({"result": result, "provenance": provenance}, ensure_ascii=False).encode()
    if len(artifact) > min(settings.max_upload_bytes, settings.kali_max_output_bytes):
        raise HTTPException(413, "Resultado excede o limite de evidência")
    row = create_evidence(
        db,
        actor,
        io.BytesIO(artifact),
        data.tool + ".json",
        "application/json",
        origin="kali-mcp:" + data.tool,
        captured_at=finished,
        team_id=source.team_id if source else data.team_id,
        visibility=source.visibility if source else ("team" if data.team_id else "private"),
        challenge_id=source.challenge_id if source else None,
        metadata={"provenance": provenance},
    )
    audit(
        db,
        actor,
        "kali.executed",
        "evidence",
        row.id,
        {"tool": data.tool, "source_evidence_id": provenance["source_evidence_id"], "sha256": row.sha256},
    )
    db.commit()
    return {
        "evidence_id": row.id,
        "evidence": evidence_out(row),
        "result": result,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "sha256": row.sha256,
        "started_at": started,
        "finished_at": finished,
        "provenance": provenance,
    }
