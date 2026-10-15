# SPDX-License-Identifier: MIT
"""Optional authenticated MCP service for immutable artifact collection on Kali.

The bridge accepts bytes, never caller-controlled paths or shell commands. It can
also run on ordinary Linux for protocol tests; the optional image is Kali Linux.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import platform
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

app = FastAPI(title="CTF Kali Artifact MCP", docs_url=None, redoc_url=None, openapi_url=None)
MAX_ARTIFACT = 20 * 1024 * 1024
MAX_OUTPUT = 512 * 1024
PROTOCOLS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
ARTIFACT_SCHEMA = {
    "type": "object",
    "properties": {
        "artifact_base64": {"type": "string", "maxLength": 28 * 1024 * 1024},
        "name": {"type": "string", "maxLength": 240},
    },
    "required": ["artifact_base64", "name"],
    "additionalProperties": False,
}
TOOL_DESCRIPTIONS = {
    "system_info": "Identifica sistema e versões do ambiente de coleta.",
    "artifact_hash": "Calcula SHA-256 de bytes fornecidos de uma evidência autorizada.",
    "artifact_file": "Identifica o tipo de arquivo com file, sem executar o artefato.",
    "artifact_strings": "Extrai strings imprimíveis; não executa o artefato.",
    "artifact_json_summary": "Descreve estrutura JSON observada sem apresentar valores como inferências.",
}


def token():
    return os.environ.get("KALI_BRIDGE_TOKEN") or os.environ.get("KALI_MCP_TOKEN", "")


def authenticate(request: Request):
    expected = token()
    if len(expected) < 32:
        raise HTTPException(503, "Configure um token do bridge com pelo menos 32 caracteres")
    supplied = request.headers.get("Authorization", "")
    if not secrets.compare_digest(supplied, "Bearer " + expected):
        raise HTTPException(401, "Token MCP inválido")


def tool_specs():
    return [
        {
            "name": name,
            "description": description,
            "inputSchema": ARTIFACT_SCHEMA
            if name != "system_info"
            else {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        }
        for name, description in TOOL_DESCRIPTIONS.items()
    ]


def command(binary: str, artifact: bytes):
    executable = shutil.which(binary)
    if not executable:
        raise ValueError("Ferramenta não instalada no ambiente de coleta")
    with tempfile.TemporaryDirectory(prefix="ctf-artifact-") as directory:
        filename = Path(directory) / "evidence.bin"
        filename.write_bytes(artifact)
        filename.chmod(0o400)
        argv = [executable]
        if binary == "file":
            argv += ["--brief", "--mime-type", "--"]
        elif binary == "strings":
            argv += ["-a", "-n", "6", "--"]
        else:
            argv += ["--"]
        argv.append(str(filename))
        completed = subprocess.run(
            argv,
            shell=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=20,
            check=False,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            start_new_session=True,
        )
        return {
            "stdout": completed.stdout[:MAX_OUTPUT].decode("utf-8", errors="replace"),
            "stderr": completed.stderr[:MAX_OUTPUT].decode("utf-8", errors="replace"),
            "exit_code": completed.returncode,
            "truncated": len(completed.stdout) > MAX_OUTPUT,
            "command": [Path(executable).name, *argv[1:-1], "<authorized-evidence>"],
            "source_sha256": hashlib.sha256(artifact).hexdigest(),
        }


def execute(name: str, arguments: dict):
    if name not in TOOL_DESCRIPTIONS or not isinstance(arguments, dict):
        raise ValueError("Ferramenta ou argumentos inválidos")
    if name == "system_info":
        if arguments:
            raise ValueError("system_info não aceita argumentos")
        result = {
            "stdout": json.dumps(
                {"system": platform.system(), "release": platform.release(), "python": platform.python_version()},
                sort_keys=True,
            ),
            "stderr": "",
            "exit_code": 0,
            "method": "platform library",
        }
    else:
        if set(arguments) != {"artifact_base64", "name"}:
            raise ValueError("Envie somente os bytes e o nome do artefato")
        encoded = arguments["artifact_base64"]
        display_name = arguments["name"]
        if not isinstance(encoded, str) or len(encoded) > (MAX_ARTIFACT * 4 // 3) + 8:
            raise ValueError("Artefato excedeu o limite")
        if not isinstance(display_name, str) or len(display_name) > 240 or any(ord(c) < 32 for c in display_name):
            raise ValueError("Nome inválido")
        try:
            artifact = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Base64 inválido") from exc
        if len(artifact) > MAX_ARTIFACT:
            raise ValueError("Artefato excedeu o limite")
        if name == "artifact_json_summary":
            value = json.loads(artifact)
            summary = {"type": type(value).__name__}
            if isinstance(value, dict):
                summary.update(keys=list(value.keys())[:100], item_count=len(value))
            elif isinstance(value, list):
                summary.update(item_count=len(value), item_types=sorted({type(item).__name__ for item in value[:100]}))
            result = {
                "stdout": json.dumps(summary, ensure_ascii=False),
                "stderr": "",
                "exit_code": 0,
                "source_sha256": hashlib.sha256(artifact).hexdigest(),
            }
        else:
            result = command(
                {"artifact_hash": "sha256sum", "artifact_file": "file", "artifact_strings": "strings"}[name], artifact
            )
    return {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
        "structuredContent": result,
        "isError": result["exit_code"] != 0,
    }


@app.get("/health")
def health():
    return {"status": "ready" if len(token()) >= 32 else "not-configured"}


@app.post("/mcp")
async def mcp(request: Request):
    authenticate(request)
    content_length = request.headers.get("content-length", "")
    if content_length and (not content_length.isdecimal() or int(content_length) > MAX_ARTIFACT * 2):
        raise HTTPException(413, "Requisição acima do limite")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_ARTIFACT * 2:
            raise HTTPException(413, "Requisição acima do limite")
    try:
        data = json.loads(body)
    except ValueError:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Invalid JSON"}}, status_code=400
        )
    if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}}, status_code=400
        )
    request_id = data.get("id")
    method = data.get("method")
    params = data.get("params", {})
    if not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Invalid parameters"}}
    if method == "notifications/initialized" and "id" not in data:
        return Response(status_code=202)
    if "id" not in data:
        return Response(status_code=202)
    if not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
        raise HTTPException(400, "Invalid request id")
    if method == "initialize":
        requested = params.get("protocolVersion")
        result = {
            "protocolVersion": requested if requested in PROTOCOLS else "2025-03-26",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "CTF Kali Artifact MCP", "version": "1.0.0"},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": tool_specs()}
    elif method == "tools/call":
        try:
            # Small bounded fixed operations; worker thread avoids blocking MCP protocol loop.
            import anyio

            result = await anyio.to_thread.run_sync(execute, params.get("name"), params.get("arguments", {}))
        except (ValueError, UnicodeError, OSError, subprocess.TimeoutExpired, RecursionError):
            result = {
                "content": [{"type": "text", "text": "Artefato inválido ou ferramenta indisponível"}],
                "isError": True,
            }
    else:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}
