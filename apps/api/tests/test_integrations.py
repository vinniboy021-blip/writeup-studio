# SPDX-License-Identifier: MIT
"""Protocol, authorization and provenance tests; MCP transports are explicitly local test fixtures."""

import asyncio
import base64
import hashlib
import json

import httpx
import pytest
from sqlalchemy import select

from app.config import settings
from app.models import AuditLog, Evidence
from app.modules.integrations import routes
from app.modules.integrations.client import MCPClient, MCPError
from app.modules.integrations.kali_bridge import app as bridge, execute


@pytest.fixture
def mcp_transport(monkeypatch):
    calls = []

    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert request.headers["authorization"] == "Bearer test-kali-token"
        method = payload["method"]
        if method == "notifications/initialized":
            return httpx.Response(202)
        result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}}
        if method == "tools/list":
            result = {
                "tools": [
                    {"name": "artifact_hash", "description": "Hash", "inputSchema": {"type": "object"}},
                    {"name": "arbitrary_shell", "inputSchema": {"type": "object"}},
                ]
            }
        if method == "tools/call":
            args = payload["params"]["arguments"]
            blob = base64.b64decode(args["artifact_base64"])
            result = {
                "content": [{"type": "text", "text": "Test fixture output"}],
                "structuredContent": {"stdout": hashlib.sha256(blob).hexdigest(), "stderr": "", "exit_code": 0},
            }
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result})

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(settings, "kali_enabled", True)
    monkeypatch.setattr(settings, "kali_mcp_url", "https://kali.example.invalid/mcp")
    monkeypatch.setattr(settings, "kali_mcp_token", "test-kali-token")
    monkeypatch.setattr(
        routes,
        "make_client",
        lambda: MCPClient(
            settings.kali_mcp_url, settings.kali_mcp_token, 5, settings.kali_max_output_bytes, transport=transport
        ),
    )
    return calls


def test_disabled_and_authentication(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "kali_enabled", False)
    assert client.get("/api/v1/kali/status").json()["enabled"] is False
    assert (
        client.post(
            "/api/v1/kali/run", json={"tool": "system_info", "confirm": True}, headers=auth["headers"]
        ).status_code
        == 503
    )
    client.cookies.clear()
    assert client.get("/api/v1/kali/status").status_code == 401


def test_initialize_filters_tools_and_never_leaks_connection_token(client, auth, mcp_transport):
    response = client.get("/api/v1/kali/status")
    assert response.status_code == 200
    data = response.json()
    assert data["connected"]
    assert [tool["name"] for tool in data["tools"]] == ["artifact_hash"]
    assert "test-kali-token" not in response.text
    assert [call["method"] for call in mcp_transport] == ["initialize", "notifications/initialized", "tools/list"]
    assert client.get("/api/v1/kali/tools").json()["total"] == 1


def test_execution_requires_csrf_confirm_and_authorized_evidence(client, auth, auth_factory, mcp_transport):
    uploaded = client.post(
        "/api/v1/evidences",
        files={"file": ("capture.txt", b"authentic supplied note", "text/plain")},
        data={"origin": "test fixture"},
        headers=auth["headers"],
    )
    assert uploaded.status_code == 201, uploaded.text
    evidence_id = uploaded.json()["id"]
    body = {"tool": "artifact_hash", "evidence_id": evidence_id, "confirm": True}
    assert client.post("/api/v1/kali/run", json=body).status_code == 403
    assert client.post("/api/v1/kali/run", json={**body, "confirm": False}, headers=auth["headers"]).status_code == 428
    assert (
        client.post(
            "/api/v1/kali/run", json={**body, "arguments": {"path": "/etc/passwd"}}, headers=auth["headers"]
        ).status_code
        == 422
    )
    assert not mcp_transport
    other = auth_factory("other@example.org")
    assert client.post("/api/v1/kali/run", json=body, headers=other["headers"]).status_code == 404
    assert not mcp_transport


def test_authorized_output_persisted_with_hash_and_audit(client, auth, db, mcp_transport):
    blob = b"real user supplied test input"
    original = client.post(
        "/api/v1/evidences", files={"file": ("notes.txt", blob, "text/plain")}, headers=auth["headers"]
    ).json()
    response = client.post(
        "/api/v1/kali/run",
        json={"tool": "artifact_hash", "evidence_id": original["id"], "confirm": True},
        headers=auth["headers"],
    )
    assert response.status_code == 201, response.text
    result = response.json()
    downloaded = client.get(f"/api/v1/evidences/{result['evidence_id']}/download")
    assert downloaded.status_code == 200
    assert hashlib.sha256(downloaded.content).hexdigest() == result["sha256"]
    artifact = downloaded.json()
    assert artifact["provenance"]["source_evidence_id"] == original["id"]
    assert artifact["provenance"]["human_review_required"] is True
    assert result["stdout"] == hashlib.sha256(blob).hexdigest()
    assert db.get(Evidence, result["evidence_id"]).owner_id == auth["user"]["id"]
    assert db.scalar(select(AuditLog).where(AuditLog.action == "kali.executed")) is not None
    tool_call = next(call for call in mcp_transport if call["method"] == "tools/call")
    assert set(tool_call["params"]["arguments"]) == {"artifact_base64", "name"}


def test_mcp_failed_call_is_recorded_not_presented_as_execution(client, auth, db, monkeypatch, mcp_transport):
    async def failing(*_):
        raise MCPError("Upstream failure containing potential secrets")

    monkeypatch.setattr(MCPClient, "call", failing)
    original = client.post(
        "/api/v1/evidences", files={"file": ("notes.txt", b"captured", "text/plain")}, headers=auth["headers"]
    ).json()
    response = client.post(
        "/api/v1/kali/run",
        json={"tool": "artifact_hash", "evidence_id": original["id"], "confirm": True},
        headers=auth["headers"],
    )
    assert response.status_code == 502
    assert "potential secrets" not in response.text
    assert db.scalar(select(AuditLog).where(AuditLog.action == "kali.failed")) is not None


def test_system_info_requires_manager_or_admin_and_rejects_shell_input(client, auth, mcp_transport):
    assert (
        client.post(
            "/api/v1/kali/run", json={"tool": "system_info", "confirm": True}, headers=auth["headers"]
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/kali/run",
            json={"tool": "artifact_hash", "command": "cat /etc/passwd", "confirm": True},
            headers=auth["headers"],
        ).status_code
        == 422
    )


def test_streamable_http_initializes_real_bridge_and_validates_rpc_auth(monkeypatch):
    monkeypatch.setenv("KALI_BRIDGE_TOKEN", "b" * 40)

    async def scenario():
        transport = httpx.ASGITransport(app=bridge)
        async with MCPClient("http://bridge/mcp", "b" * 40, 5, 1024 * 1024, transport=transport) as client:
            assert (await client.initialize())["protocolVersion"] == "2025-03-26"
            assert len(await client.tools()) == 5
            result = await client.call(
                "artifact_json_summary",
                {"name": "capture.json", "artifact_base64": base64.b64encode(b'{"observed":42}').decode()},
            )
            assert json.loads(result["structuredContent"]["stdout"])["keys"] == ["observed"]
            assert result["structuredContent"]["source_sha256"] == hashlib.sha256(b'{"observed":42}').hexdigest()
        async with httpx.AsyncClient(transport=transport, base_url="http://bridge") as client:
            assert (
                await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            ).status_code == 401

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "params",
    [
        {"path": "/etc/passwd"},
        {"artifact_base64": "bad", "name": "capture.txt"},
        {"artifact_base64": "YQ==", "name": "x\nheader"},
    ],
)
def test_bridge_rejects_paths_and_invalid_artifact(params):
    with pytest.raises(ValueError):
        execute("artifact_file", params)


def test_rpc_response_bounds_id_validation_and_sse():
    async def scenario():
        def sse(request):
            payload = json.loads(request.content)
            content = (
                "data: " + json.dumps({"jsonrpc": "2.0", "id": payload["id"], "result": {"ok": True}}) + "\r\n\r\n"
            )
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=content)

        async with MCPClient("http://bridge/mcp", "", 1, 4096, transport=httpx.MockTransport(sse)) as client:
            assert await client.request("ping") == {"ok": True}
        for payload in ({"jsonrpc": "2.0", "id": "wrong", "result": {}}, {"large": "x" * 5000}):
            async with MCPClient(
                "http://bridge/mcp",
                "",
                1,
                1024,
                transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
            ) as client:
                with pytest.raises(MCPError):
                    await client.request("ping")

    asyncio.run(scenario())
