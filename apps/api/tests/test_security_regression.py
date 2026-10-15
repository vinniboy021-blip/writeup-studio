# SPDX-License-Identifier: MIT
"""Security regression flows across identity, collaboration and protected artifacts.

These tests use real HTTP authentication, migrated isolated databases and synthetic
local artifacts. External providers and HTTP transports are never contacted.
"""

import hashlib
import io
import json
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import utcnow
from app.models import AIJob, Export, ReviewRequest, SessionModel, TeamMember, User, Writeup
from app.modules.evidence import jobs as evidence_jobs
from app.modules.studio import jobs, routes as studio_routes
from app.modules.studio.exporting import export_document
from app.security import digest


PASSWORD = "Security-test-password-123!"


@pytest.fixture
def secure_workspace(client, engine, monkeypatch):
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(settings, "login_rate_limit", 100)
    monkeypatch.setattr(settings, "cookie_secure", False)
    monkeypatch.setattr(settings, "queue_enabled", False)
    monkeypatch.setattr(settings, "ai_enabled", False)
    monkeypatch.setattr(jobs, "SessionLocal", factory)
    monkeypatch.setattr(evidence_jobs, "SessionLocal", factory)
    actors = {}
    for role in ("manager", "editor", "reviewer", "viewer", "outsider"):
        peer = TestClient(client.app)
        result = peer.post("/api/v1/auth/register", json={
            "name": role, "email": role + "@security.example.org", "password": PASSWORD,
        })
        assert result.status_code == 201, result.text
        data = result.json()
        peer.headers["X-CSRF-Token"] = data["csrf_token"]
        actors[role] = {"client": peer, "id": data["user"]["id"], "csrf": data["csrf_token"]}
    manager = actors["manager"]["client"]
    team = manager.post("/api/v1/teams", json={"name": "Equipe de segurança"})
    assert team.status_code == 201, team.text
    team_id = team.json()["id"]
    for role in ("editor", "reviewer", "viewer"):
        member = manager.post(f"/api/v1/teams/{team_id}/members", json={"user_id": actors[role]["id"], "role": role})
        assert member.status_code == 201, member.text
    yield {"actors": actors, "team_id": team_id, "factory": factory, "app": client.app}
    for actor in actors.values():
        actor["client"].close()


def peer(env, role="manager"):
    return env["actors"][role]["client"]


def document(content="Nota observada no laboratório"):
    return {"schema_version": 1, "sections": [{"id": "analysis", "title": "Análise", "markdown": content}]}


def writeup(env, shared=True, title="Documento protegido", content=None, role="manager"):
    body = {"title": title, "document": document(content or "Nota observada no laboratório")}
    if shared:
        body.update(team_id=env["team_id"], visibility="team")
    result = peer(env, role).post("/api/v1/writeups", json=body)
    assert result.status_code == 201, result.text
    return result.json()


def evidence(env, shared=True, *, image=False, private_team=False, role="manager"):
    if image:
        output = io.BytesIO()
        Image.new("RGB", (32, 24), "white").save(output, "PNG")
        content, name, mime = output.getvalue(), "capture.png", "image/png"
    else:
        content, name, mime = b"AUTHENTIC-LOCAL-OBSERVATION\n", "capture.log", "text/plain"
    fields = {"origin": "Synthetic local regression fixture"}
    if shared or private_team:
        fields["team_id"] = env["team_id"]
    if shared:
        fields["visibility"] = "team"
    result = peer(env, role).post("/api/v1/evidences", files={"file": (name, content, mime)}, data=fields)
    assert result.status_code == 201, result.text
    return result.json(), content


def approve(env, item):
    review = peer(env).post(f'/api/v1/writeups/{item["id"]}/reviews', json={"reviewer_id": env["actors"]["reviewer"]["id"]})
    assert review.status_code == 201, review.text
    result = peer(env, "reviewer").post(f'/api/v1/reviews/{review.json()["id"]}/decision', json={"decision": "approved"})
    assert result.status_code == 200, result.text


def change_role(env, role, new_role):
    result = peer(env).patch(f'/api/v1/teams/{env["team_id"]}/members/{env["actors"][role]["id"]}', json={"role": new_role})
    assert result.status_code == 200, result.text


def test_private_content_and_histories_never_leak_to_team_or_outsider(secure_workspace):
    env = secure_workspace
    item = writeup(env, shared=False, content="PRIVATE-HISTORY-MARKER")
    ev, _ = evidence(env, shared=False, image=True)
    template = peer(env).post("/api/v1/templates", json={"name": "Modelo secreto", "document": document("PRIVATE-HISTORY-MARKER")}).json()
    for role in ("viewer", "outsider"):
        for path in (f'/writeups/{item["id"]}', f'/writeups/{item["id"]}/revisions',
                     f'/writeups/{item["id"]}/diff?from_version=1&to_version=1',
                     f'/writeups/{item["id"]}/comments', f'/writeups/{item["id"]}/reviews',
                     f'/templates/{template["id"]}/revisions', f'/evidences/{ev["id"]}/annotations',
                     f'/evidences/{ev["id"]}/versions', f'/evidences/{ev["id"]}/timeline',
                     f'/evidences/{ev["id"]}/download', f'/timeline?writeup_id={item["id"]}'):
            result = peer(env, role).get("/api/v1" + path)
            assert result.status_code == 404, (path, result.text)
            assert "PRIVATE-HISTORY-MARKER" not in result.text
        for path in ("/writeups", "/evidences", "/timeline", "/dashboard", "/search?q=PRIVATE-HISTORY-MARKER"):
            result = peer(env, role).get("/api/v1" + path)
            assert result.status_code == 200, result.text
            assert "PRIVATE-HISTORY-MARKER" not in result.text


def test_viewer_can_read_and_export_but_cannot_mutate_collaboration(secure_workspace):
    env = secure_workspace
    item = writeup(env)
    ev, _ = evidence(env, image=True)
    uri = f'/api/v1/writeups/{item["id"]}'
    viewer = peer(env, "viewer")
    requests = [
        ("patch", uri, {"expected_version": 1, "title": "Forbidden"}),
        ("post", uri + "/comments", {"body": "Forbidden"}),
        ("post", uri + "/reviews", {"reviewer_id": env["actors"]["reviewer"]["id"]}),
        ("post", uri + "/evidences", {"evidence_id": ev["id"]}),
        ("patch", f'/api/v1/evidences/{ev["id"]}', {"expected_version": 1, "name": "Forbidden"}),
        ("post", f'/api/v1/evidences/{ev["id"]}/annotations', {"expected_version": 1, "data": {"width": 32, "height": 24, "shapes": []}}),
        ("post", f'/api/v1/teams/{env["team_id"]}/invites', {"email": "new@example.org"}),
        ("post", "/api/v1/templates", {"name": "Forbidden", "team_id": env["team_id"], "document": document()}),
    ]
    for method, path, payload in requests:
        result = getattr(viewer, method)(path, json=payload)
        assert result.status_code == 403, (path, result.text)
    assert viewer.get(uri).status_code == 200
    exported = viewer.post(uri + "/exports", json={"format": "json"})
    assert exported.status_code == 202, exported.text
    assert viewer.get(f'/api/v1/exports/{exported.json()["id"]}/download').status_code == 200


def test_removed_team_member_loses_prior_export_ticket_history_and_search(secure_workspace):
    env = secure_workspace
    item = writeup(env)
    ev, _ = evidence(env)
    viewer = peer(env, "viewer")
    exported = viewer.post(f'/api/v1/writeups/{item["id"]}/exports', json={"format": "json"}).json()
    ticket = viewer.post(f'/api/v1/evidences/{ev["id"]}/download-ticket', json={}).json()
    removed = peer(env).delete(f'/api/v1/teams/{env["team_id"]}/members/{env["actors"]["viewer"]["id"]}')
    assert removed.status_code == 200, removed.text
    for path in (f'/api/v1/writeups/{item["id"]}', f'/api/v1/writeups/{item["id"]}/revisions',
                 f'/api/v1/exports/{exported["id"]}', f'/api/v1/exports/{exported["id"]}/download', ticket["url"]):
        assert viewer.get(path).status_code == 403
    assert viewer.get("/api/v1/writeups").json()["items"] == []
    assert viewer.get("/api/v1/search?q=protegido").json()["items"] == []


def test_removed_owner_does_not_recover_team_snapshot_through_dashboard(secure_workspace):
    env = secure_workspace
    item = writeup(env, content="REVOKED-TEAM-SNAPSHOT-CONTENT")
    approve(env, item)
    publication = peer(env).post(f'/api/v1/writeups/{item["id"]}/publish', json={"visibility": "team", "expected_version": 1})
    assert publication.status_code == 201, publication.text
    change_role(env, "editor", "manager")
    removed = peer(env, "editor").delete(f'/api/v1/teams/{env["team_id"]}/members/{env["actors"]["manager"]["id"]}')
    assert removed.status_code == 200, removed.text
    assert peer(env).get(f'/api/v1/publications/{publication.json()["id"]}').status_code == 403
    dashboard = peer(env).get("/api/v1/dashboard")
    assert dashboard.status_code == 200
    assert "REVOKED-TEAM-SNAPSHOT-CONTENT" not in dashboard.text
    assert publication.json()["id"] not in dashboard.text


def test_downgraded_comment_author_cannot_mutate_own_team_comment(secure_workspace):
    env = secure_workspace
    item = writeup(env)
    comment = peer(env, "editor").post(f'/api/v1/writeups/{item["id"]}/comments', json={"body": "Observação"})
    assert comment.status_code == 201, comment.text
    change_role(env, "editor", "viewer")
    result = peer(env, "editor").patch(f'/api/v1/comments/{comment.json()["id"]}', json={"resolved": True})
    assert result.status_code == 403, result.text


def test_removed_member_cannot_share_private_evidence_back_into_team(secure_workspace):
    env = secure_workspace
    ev, _ = evidence(env, shared=False, private_team=True, role="editor")
    result = peer(env).delete(f'/api/v1/teams/{env["team_id"]}/members/{env["actors"]["editor"]["id"]}')
    assert result.status_code == 200, result.text
    result = peer(env, "editor").patch(f'/api/v1/evidences/{ev["id"]}', json={"expected_version": 1, "visibility": "team"})
    assert result.status_code == 403, result.text
    assert peer(env, "viewer").get(f'/api/v1/evidences/{ev["id"]}').status_code == 404


def test_author_cannot_approve_even_with_manager_role_and_forged_request(secure_workspace):
    env = secure_workspace
    item = writeup(env)
    own = env["actors"]["manager"]["id"]
    request = peer(env).post(f'/api/v1/writeups/{item["id"]}/reviews', json={"reviewer_id": own})
    assert request.status_code == 422
    with env["factory"]() as db:
        review = ReviewRequest(writeup_id=item["id"], requester_id=env["actors"]["editor"]["id"], reviewer_id=own, version=1)
        db.add(review)
        db.commit()
        review_id = review.id
    decision = peer(env).post(f"/api/v1/reviews/{review_id}/decision", json={"decision": "approved"})
    assert decision.status_code == 403
    assert peer(env).get(f'/api/v1/writeups/{item["id"]}').json()["approved_revision"] is None


def test_latest_revision_author_cannot_approve_and_stale_review_cannot_publish(secure_workspace):
    env = secure_workspace
    item = writeup(env)
    uri = f'/api/v1/writeups/{item["id"]}'
    pending = peer(env).post(uri + "/reviews", json={"reviewer_id": env["actors"]["reviewer"]["id"]})
    assert pending.status_code == 201
    saved = peer(env, "editor").patch(uri, json={"expected_version": 1, "document": document("Edição da versão atual")})
    assert saved.status_code == 200 and saved.json()["version"] == 2
    decision = peer(env, "reviewer").post(f'/api/v1/reviews/{pending.json()["id"]}/decision', json={"decision": "approved"})
    assert decision.status_code == 409
    change_role(env, "editor", "manager")
    requested = peer(env).post(uri + "/reviews", json={"reviewer_id": env["actors"]["editor"]["id"]})
    assert requested.status_code == 422
    assert peer(env).patch(uri, json={"expected_version": 2, "status": "approved"}).status_code == 422
    publish = peer(env).post(uri + "/publish", json={"visibility": "public", "expected_version": 2, "confirm_public": True})
    assert publish.status_code == 409


def test_expired_and_deactivated_sessions_cannot_read_or_mutate(secure_workspace):
    env = secure_workspace
    item = writeup(env)
    viewer = peer(env, "viewer")
    with env["factory"]() as db:
        session = db.scalar(select(SessionModel).where(SessionModel.token_hash == digest(viewer.cookies["ctf_session"])))
        session.expires_at = utcnow() - timedelta(seconds=1)
        editor = db.get(User, env["actors"]["editor"]["id"])
        editor.is_active = False
        db.commit()
    for role in ("viewer", "editor"):
        assert peer(env, role).get(f'/api/v1/writeups/{item["id"]}').status_code == 401
        assert peer(env, role).post("/api/v1/writeups", json={"title": "Forbidden"}).status_code == 401


@pytest.mark.parametrize("headers", [
    {"Origin": "https://untrusted.example.org"},
    {"Sec-Fetch-Site": "cross-site"},
    {"X-CSRF-Token": "forged"},
])
def test_session_token_alone_cannot_bypass_origin_or_csrf(secure_workspace, headers):
    owner = peer(secure_workspace)
    result = owner.post("/api/v1/writeups", json={"title": "Forbidden"}, headers=headers)
    assert result.status_code == 403
    assert owner.get("/api/v1/writeups").json()["items"] == []


def test_download_ticket_is_actor_resource_version_and_expiry_bound(secure_workspace, monkeypatch):
    env = secure_workspace
    first, content = evidence(env)
    second, _ = evidence(env)
    result = peer(env).post(f'/api/v1/evidences/{first["id"]}/download-ticket', json={})
    assert result.status_code == 200, result.text
    ticket = result.json()["url"]
    assert peer(env).get(ticket).content == content
    assert peer(env, "viewer").get(ticket).status_code == 403
    assert peer(env).get(ticket.replace(first["id"], second["id"])).status_code == 403
    assert peer(env).get(ticket + "tampered").status_code == 403
    from app.modules.evidence import routes as evidence_routes
    monkeypatch.setattr(evidence_routes.time, "time", lambda: result.json()["expires_at"] + 1)
    assert peer(env).get(ticket).status_code == 403


def test_queued_exports_recheck_membership_before_reading_frozen_content(secure_workspace, monkeypatch):
    env = secure_workspace
    item = writeup(env)
    monkeypatch.setattr(studio_routes, "enqueue", lambda *_: None)
    requested = peer(env, "viewer").post(f'/api/v1/writeups/{item["id"]}/exports', json={"format": "json"})
    assert requested.status_code == 202 and requested.json()["status"] == "queued"
    removed = peer(env).delete(f'/api/v1/teams/{env["team_id"]}/members/{env["actors"]["viewer"]["id"]}')
    assert removed.status_code == 200
    jobs.execute_export(requested.json()["id"])
    with env["factory"]() as db:
        row = db.get(Export, requested.json()["id"])
        assert row.status == "failed" and row.storage_key is None


def test_ai_private_source_gating_and_revocation_before_job_or_result(secure_workspace, monkeypatch):
    env = secure_workspace
    secret = writeup(env, shared=False, content="PRIVATE-AI-SOURCE")
    protected, _ = evidence(env, shared=False)
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(studio_routes, "enqueue", lambda *_: None)
    calls = []
    monkeypatch.setattr(jobs, "generate_result", lambda *args: calls.append(args) or {"draft": "SHARED-AI-RESULT"})
    for body in ({"writeup_id": secret["id"]}, {"evidence_ids": [protected["id"]]}):
        result = peer(env, "outsider").post("/api/v1/ai/jobs", json={"task": "structure_notes", **body})
        assert result.status_code == 404
    shared = writeup(env)
    requested = peer(env, "editor").post("/api/v1/ai/jobs", json={"task": "structure_notes", "writeup_id": shared["id"]})
    assert requested.status_code == 202, requested.text
    job_id = requested.json()["id"]
    removed = peer(env).delete(f'/api/v1/teams/{env["team_id"]}/members/{env["actors"]["editor"]["id"]}')
    assert removed.status_code == 200
    jobs.execute_ai(job_id)
    assert calls == []
    with env["factory"]() as db:
        row = db.get(AIJob, job_id)
        assert row.status == "failed" and row.output_data is None
    assert peer(env, "editor").get("/api/v1/ai/jobs/" + job_id).status_code == 403
    listing = peer(env, "editor").get("/api/v1/ai/jobs")
    assert listing.status_code == 200 and listing.json()["items"] == []
    assert "PRIVATE-AI-SOURCE" not in listing.text


def test_ai_disabled_and_external_consent_fail_before_provider(secure_workspace, monkeypatch):
    owner = peer(secure_workspace)
    body = {"task": "structure_notes", "notes": "Observation supplied by test"}
    assert owner.post("/api/v1/ai/jobs", json=body).status_code == 503
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_external_enabled", True)
    assert owner.post("/api/v1/ai/jobs", json={**body, "provider": "external"}).status_code == 403
    monkeypatch.setattr(settings, "ai_external_enabled", False)
    assert owner.post("/api/v1/ai/jobs", json={**body, "provider": "external", "external_consent": True}).status_code == 403


@pytest.mark.parametrize("format_name", ["html", "pdf"])
def test_exports_never_fetch_document_network_or_filesystem_urls(monkeypatch, format_name):
    def forbidden_request(*_args, **_kwargs):
        pytest.fail("Renderer attempted a network request from document content")
    monkeypatch.setattr(httpx.Client, "request", forbidden_request)
    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden_request)
    snapshot = {"title": "<script>title()</script>", "version": 1, "document": document(
        '<script>alert(1)</script>\n[JS](javascript:alert%281%29)\n![Local](file:///etc/passwd)\n'
        '![Remote](http://127.0.0.1:666/private)\n![Cloud](http://169.254.169.254/latest/meta-data/)\n'
        '[Encoded](data:text/html;base64,PHNjcmlwdD4=)\n'
        '```sh\nprintf "<authentic command>"\n```'), "evidences": []}
    result, mime, _filename = export_document(snapshot, {"format": format_name})
    assert mime.startswith("text/html") if format_name == "html" else mime == "application/pdf"
    if format_name == "html":
        rendered = result.decode()
        assert "<script>" not in rendered
        assert 'href="javascript:' not in rendered and 'src="http:' not in rendered and 'src="file:' not in rendered
        assert 'href="data:' not in rendered
    else:
        assert result.startswith(b"%PDF-")


def test_markdown_export_strips_active_links_and_markup_but_preserves_literal_commands():
    snapshot = {"title": "<img src=x onerror=alert(1)>", "version": 1, "document": document(
        '[JS](javascript:alert%281%29)\n[Encoded](data:text/html;base64,PHNjcmlwdD4=)\n'
        '<script>alert(1)</script>\n```sh\nprintf "<observed>"\n```'), "evidences": []}
    snapshot["document"]["sections"][0]["title"] = "<img src=x onerror=alert(1)>"
    result, _mime, _filename = export_document(snapshot, {"format": "markdown"})
    text = result.decode()
    assert "<img" not in text and "<script>" not in text
    assert "](javascript:" not in text and "](data:" not in text
    assert 'printf "<observed>"' in text


def test_spoofed_upload_and_intrinsic_metadata_cannot_forge_evidence(secure_workspace):
    env = secure_workspace
    owner = peer(env)
    forged = owner.post("/api/v1/evidences", files={"file": ("x.png", b"<script>fake</script>", "image/png")})
    assert forged.status_code == 422
    empty = owner.post("/api/v1/evidences", files={"file": ("x.log", b"", "text/plain")})
    assert empty.status_code == 422
    ev, content = evidence(env, image=True)
    patch = owner.patch(f'/api/v1/evidences/{ev["id"]}', json={"expected_version": 1,
        "metadata": {"width": 1, "height": 1, "frames": 900, "detected_mime": "text/plain"}})
    assert patch.status_code == 200, patch.text
    assert patch.json()["metadata"]["width"] == 32 and patch.json()["metadata"]["height"] == 24
    assert patch.json()["metadata"]["frames"] == 1
    assert owner.get(f'/api/v1/evidences/{ev["id"]}/download').content == content
    assert hashlib.sha256(content).hexdigest() == ev["sha256"]
