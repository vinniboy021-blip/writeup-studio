# SPDX-License-Identifier: MIT
import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import httpx
from PIL import Image
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import Base, get_db, make_engine, utcnow
from app.models import AIJob, Evidence, Export, Publication, ReviewRequest, Team, TeamMember, User, Writeup, WriteupRevision
from app.modules.evidence import jobs as evidence_jobs
from app.modules.evidence.routes import router as evidence_router
from app.modules.identity.routes import router as identity_router
from app.modules.studio import ai, jobs
from app.modules.studio.exporting import export_document
from app.modules.studio.routes import router
from app.modules.studio.services import save_revision
from app.modules.workspace.routes import router as workspace_router


@pytest.fixture
def studio(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{tmp_path / 'studio.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "objects"))
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "queue_enabled", False)
    monkeypatch.setattr(settings, "cookie_secure", False)
    monkeypatch.setattr(settings, "ai_enabled", False)
    monkeypatch.setattr(settings, "login_rate_limit", 100)
    monkeypatch.setattr(settings, "rate_limit_backend", "memory")
    monkeypatch.setattr(jobs, "SessionLocal", factory)
    monkeypatch.setattr(evidence_jobs, "SessionLocal", factory)
    api = FastAPI()
    for imported in (identity_router, router, workspace_router, evidence_router):
        api.include_router(imported, prefix="/api/v1")
    def db_override():
        with factory() as session:
            yield session
    api.dependency_overrides[get_db] = db_override
    clients = {}
    users = {}
    for name in ("owner", "editor", "reviewer", "viewer", "outsider"):
        client = TestClient(api)
        result = client.post("/api/v1/auth/register", json={"email": name + "@studio.example.org", "name": name,
                                                           "password": "CorrectHorse!Battery7"})
        assert result.status_code == 201, result.text
        client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        clients[name] = client; users[name] = result.json()["user"]["id"]
    with factory() as db:
        team = Team(owner_id=users["owner"], name="Studio equipe")
        db.add(team); db.flush()
        for role in ("owner", "editor", "reviewer", "viewer"):
            db.add(TeamMember(team_id=team.id, user_id=users[role], role="manager" if role == "owner" else role))
        db.commit(); team_id = team.id
    yield clients, users, team_id, factory
    for client in clients.values():
        client.close()
    engine.dispose()


def doc(text="Observação autêntica", section_id="objective"):
    return {"schema_version": 1, "sections": [{"id": section_id, "title": "Objetivo", "markdown": text}]}


def create(env, shared=False, text="Observação autêntica"):
    clients, _, team, _ = env
    body = {"title": "Writeup real", "document": doc(text)}
    if shared:
        body.update(team_id=team, visibility="team")
    result = clients["owner"].post("/api/v1/writeups", json=body)
    assert result.status_code == 201, result.text
    return result.json()


def png():
    output = io.BytesIO(); Image.new("RGB", (100, 80), "white").save(output, "PNG")
    return output.getvalue()


def upload(env, shared=False, text=False):
    clients, _, team, _ = env
    result = clients["owner"].post("/api/v1/evidences", files={"file":
        ("capture.log", b"$ whoami\nalice\n", "text/plain") if text else ("capture.png", png(), "image/png")},
        data={"origin": "Terminal Kali autorizado", **({"team_id": team, "visibility": "team"} if shared else {})})
    assert result.status_code == 201, result.text
    return result.json()


def approved(env, writeup):
    clients, users, _, _ = env
    result = clients["owner"].post(f'/api/v1/writeups/{writeup["id"]}/reviews', json={"reviewer_id": users["reviewer"]})
    assert result.status_code == 201, result.text
    review_id = result.json()["id"]
    decision = clients["reviewer"].post(f"/api/v1/reviews/{review_id}/decision", json={"decision": "approved"})
    assert decision.status_code == 200, decision.text


def test_real_auth_create_schema_defaults_and_pagination(studio):
    clients, _, _, _ = studio
    result = create(studio)
    assert result["version"] == 1
    assert clients["owner"].get("/api/v1/writeups").json()["total"] == 1
    assert clients["outsider"].get("/api/v1/writeups").json()["items"] == []
    assert clients["outsider"].get(f'/api/v1/writeups/{result["id"]}').status_code == 404
    assert clients["outsider"].get(f'/api/v1/writeups/{result["id"]}/revisions').status_code == 404
    default = clients["owner"].post("/api/v1/writeups", json={"title": "Padrão"})
    assert len(default.json()["document"]["sections"]) == 17
    duplicate = doc(); duplicate["sections"] += duplicate["sections"]
    assert clients["owner"].post("/api/v1/writeups", json={"title": "Inválido", "document": duplicate}).status_code == 422
    assert clients["owner"].post("/api/v1/writeups", json={"title": "Inválido", "document": {"schema_version": 2, "sections": []}}).status_code == 422
    assert clients["owner"].get("/api/v1/writeups?page_size=101").status_code == 422
    assert clients["owner"].get("/api/v1/writeups?q=real&status=draft").json()["total"] == 1
    clients["owner"].headers.pop("X-CSRF-Token")
    assert clients["owner"].post("/api/v1/writeups", json={"title": "CSRF"}).status_code == 403


def test_team_roles_restore_diff_and_conflict_no_loss(studio):
    clients, _, _, _ = studio
    writeup = create(studio, shared=True)
    uri = f'/api/v1/writeups/{writeup["id"]}'
    assert clients["viewer"].get(uri).status_code == 200
    assert clients["viewer"].patch(uri, json={"expected_version": 1, "title": "X"}).status_code == 403
    response = clients["editor"].patch(uri, json={"expected_version": 1, "title": "Título V2", "document": doc("Nova análise")})
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 2
    assert clients["owner"].patch(uri, json={"expected_version": 1, "title": "Perda"}).status_code == 409
    assert clients["owner"].get(uri).json()["title"] == "Título V2"
    difference = clients["owner"].get(uri + "/diff?from_version=1&to_version=2").json()["diff"]
    assert "-# Writeup real" in difference and "+# Título V2" in difference
    revisions = clients["owner"].get(uri + "/revisions").json()["items"]
    old_id = next(row["id"] for row in revisions if row["version"] == 1)
    restored = clients["editor"].post(uri + f"/revisions/{old_id}/restore", json={"expected_version": 2})
    assert restored.status_code == 200, restored.text
    assert restored.json()["version"] == 3 and restored.json()["title"] == writeup["title"]
    assert clients["editor"].post(uri + f"/revisions/{old_id}/restore", json={"expected_version": 2}).status_code == 409
    assert clients["owner"].get(uri + "/diff?from_version=1&to_version=999").status_code == 404
    assert clients["owner"].post(uri + "/revisions/missing/restore", json={"expected_version": 3}).status_code == 404


def test_two_independent_database_sessions_real_cas(studio):
    _, users, _, factory = studio
    item = create(studio)
    # Both sessions load the same version before either writes.
    with factory() as first, factory() as second:
        a = first.get(Writeup, item["id"]); b = second.get(Writeup, item["id"])
        owner_a = first.get(User, users["owner"]); owner_b = second.get(User, users["owner"])
        assert a.version == b.version == 1
        saved = save_revision(first, owner_a, a, 1, {"title": "Primeiro"})
        with pytest.raises(HTTPException) as conflict:
            save_revision(second, owner_b, b, 1, {"title": "Segundo"})
        assert conflict.value.status_code == 409 and saved.version == 2
    with factory() as db:
        assert db.get(Writeup, item["id"]).title == "Primeiro"
        assert [row.version for row in db.scalars(select(WriteupRevision).where(WriteupRevision.writeup_id == item["id"]).order_by(WriteupRevision.version))] == [1, 2]


def test_evidence_links_scope_section_version_and_removal(studio):
    clients, _, _, _ = studio
    writeup = create(studio, shared=True)
    private = upload(studio)
    uri = f'/api/v1/writeups/{writeup["id"]}/evidences'
    assert clients["owner"].post(uri, json={"evidence_id": private["id"]}).status_code == 422
    evidence = upload(studio, shared=True)
    assert clients["owner"].post(uri, json={"evidence_id": evidence["id"], "section_id": "missing"}).status_code == 422
    added = clients["owner"].post(uri, json={"evidence_id": evidence["id"], "section_id": "objective"})
    assert added.status_code == 201, added.text
    assert added.json()["writeup_version"] == 2
    assert clients["reviewer"].get(uri).json()["items"][0]["evidence_id"] == evidence["id"]
    reordered = clients["editor"].post(uri, json={"evidence_id": evidence["id"], "position": 4})
    assert reordered.json()["writeup_version"] == 3
    assert clients["viewer"].delete(uri + "/" + evidence["id"]).status_code == 403
    assert clients["owner"].delete(uri + "/" + evidence["id"]).json()["writeup_version"] == 4
    assert clients["owner"].delete(uri + "/" + evidence["id"]).status_code == 404


def test_approval_invalidated_by_save_and_public_expiry_revocation(studio):
    clients, _, _, factory = studio
    writeup = create(studio, shared=True, text="![Privado](evidence:00000000-0000-0000-0000-000000000000)\n<script>alert(1)</script>\n[Interno](/api/v1/writeups/private)")
    uri = f'/api/v1/writeups/{writeup["id"]}'
    assert clients["owner"].post(uri + "/publish", json={"visibility": "public", "expected_version": 1, "confirm_public": True}).status_code == 409
    approved(studio, writeup)
    assert clients["owner"].post(uri + "/publish", json={"visibility": "public", "expected_version": 1}).status_code == 422
    response = clients["owner"].post(uri + "/publish", json={"visibility": "public", "expected_version": 1, "confirm_public": True})
    assert response.status_code == 201, response.text
    pub = response.json()
    public = TestClient(clients["owner"].app)
    read = public.get("/api/v1/public/writeups/" + pub["id"])
    assert read.status_code == 200
    text = read.json()["document"]["sections"][0]["markdown"]
    assert "00000000" not in text and "<script>" not in text and "/api/v1/writeups/private" not in text
    assert public.get("/api/v1/public/writeups/" + writeup["id"]).status_code == 404
    changed = clients["editor"].patch(uri, json={"expected_version": 1, "title": "Novo"})
    assert changed.json()["approved_revision"] is None and changed.json()["version"] == 2
    # Published snapshot remains immutable until explicitly revoked/expired.
    assert public.get("/api/v1/public/writeups/" + pub["id"]).json()["title"] == "Writeup real"
    assert clients["owner"].post(uri + "/publish", json={"visibility": "public", "expected_version": 2, "confirm_public": True}).status_code == 409
    assert clients["owner"].delete("/api/v1/publications/" + pub["id"]).status_code == 200
    assert public.get("/api/v1/public/writeups/" + pub["id"]).status_code == 404
    public.close()


@pytest.mark.parametrize("visibility", ["private", "team"])
def test_private_publication_never_available_anonymously(studio, visibility):
    clients, _, _, _ = studio
    writeup = create(studio, shared=True)
    approved(studio, writeup)
    result = clients["owner"].post(f'/api/v1/writeups/{writeup["id"]}/publish', json={"visibility": visibility, "expected_version": 1})
    assert result.status_code == 201, result.text
    pubid = result.json()["id"]
    assert clients["outsider"].get("/api/v1/public/writeups/" + pubid).status_code == 404
    assert clients["owner"].get("/api/v1/publications/" + pubid).status_code == 200
    assert clients["outsider"].get("/api/v1/publications/" + pubid).status_code in {403, 404}


@pytest.mark.parametrize("format_name,marker", [("markdown", b"# Writeup real"), ("html", b"<!doctype html>"), ("json", b'"schema_version": 1'), ("pdf", b"%PDF-")])
def test_real_exports_download_rendering_and_authorization(studio, format_name, marker):
    clients, _, _, _ = studio
    item = create(studio, text="## Subtítulo\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n```python\nprint('<authentic>')\n```\n\n<script>alert(1)</script>\n![remote](http://127.0.0.1:666/secret)")
    uri = f'/api/v1/writeups/{item["id"]}'
    result = clients["owner"].post(uri + "/exports", json={"format": format_name, "header": "Equipe", "footer": "Confidencial"})
    assert result.status_code == 202, result.text
    job = result.json()
    assert job["status"] == "completed", job
    downloaded = clients["owner"].get(f'/api/v1/exports/{job["id"]}/download')
    assert marker in downloaded.content
    assert hashlib.sha256(downloaded.content).hexdigest() == job["sha256"]
    assert clients["outsider"].get(f'/api/v1/exports/{job["id"]}/download').status_code == 404
    if format_name == "html":
        assert "<table>" in downloaded.text and 'class="highlight"' in downloaded.text
        assert "<script>" not in downloaded.text and 'src="http:' not in downloaded.text
    if format_name == "markdown":
        assert "print('<authentic>')" in downloaded.text
    if format_name == "json":
        assert downloaded.json()["document"] == item["document"]
    assert clients["owner"].post(f'/api/v1/exports/{job["id"]}/cancel').status_code == 409


def test_export_frozen_derivative_images_zip_original_optin_and_public_image(studio):
    clients, _, _, factory = studio
    item = create(studio, shared=True)
    evidence = upload(studio, shared=True)
    uri = f'/api/v1/writeups/{item["id"]}'
    linked = clients["owner"].post(uri + "/evidences", json={"evidence_id": evidence["id"]})
    assert linked.status_code == 201
    # Public evidence selection must use a derived version, never the protected original.
    approved(studio, {**item, "version": 2})
    denied = clients["owner"].post(uri + "/publish", json={"visibility": "public", "expected_version": 2, "confirm_public": True, "evidence_ids": [evidence["id"]]})
    assert denied.status_code == 422, denied.text
    annotated = clients["owner"].post(f'/api/v1/evidences/{evidence["id"]}/annotations', json={"expected_version": 1,
        "data": {"schema_version": 1, "width": 100, "height": 80, "shapes": [{"id": "redacted", "type": "redact", "x": 0, "y": 0, "width": 20, "height": 20}]}})
    assert annotated.status_code == 201, annotated.text
    # Annotation invalidates an earlier document approval.
    approved(studio, {**item, "version": 2})
    pub = clients["owner"].post(uri + "/publish", json={"visibility": "public", "expected_version": 2, "confirm_public": True, "evidence_ids": [evidence["id"]]})
    assert pub.status_code == 201, pub.text
    public = TestClient(clients["owner"].app)
    public_image = public.get(f'/api/v1/public/writeups/{pub.json()["id"]}/evidences/{evidence["id"]}')
    assert public_image.status_code == 200
    assert Image.open(io.BytesIO(public_image.content)).getpixel((5, 5))[:3] == (0, 0, 0)
    assert public.get(f'/api/v1/evidences/{evidence["id"]}/download').status_code == 401
    assert public.get(f'/api/v1/public/writeups/{pub.json()["id"]}/evidences/missing').status_code == 404
    assert "storage_key" not in json.dumps(pub.json())
    export = clients["owner"].post(uri + "/exports", json={"format": "html", "include_evidences": True}).json()
    content = clients["owner"].get(f'/api/v1/exports/{export["id"]}/download').text
    assert "data:image/png;base64," in content and evidence["sha256"] not in content
    # Viewer may export redacted derivatives but cannot request original attachments.
    assert clients["viewer"].post(uri + "/exports", json={"format": "html", "include_evidences": True, "include_originals": True}).status_code == 403
    zipped = clients["owner"].post(uri + "/exports", json={"format": "markdown", "include_originals": True}).json()
    import zipfile
    archive = zipfile.ZipFile(io.BytesIO(clients["owner"].get(f'/api/v1/exports/{zipped["id"]}/download').content))
    assert archive.read("writeup-v2.md").startswith(b"# Writeup real")
    attachment = next(name for name in archive.namelist() if name.startswith("attachments/"))
    assert archive.read(attachment) == png()
    public.close()


def test_deleted_writeup_revoke_snapshots_and_exports(studio):
    clients, _, _, _ = studio
    item = create(studio, shared=True)
    approved(studio, item)
    uri = f'/api/v1/writeups/{item["id"]}'
    pub = clients["owner"].post(uri + "/publish", json={"visibility": "public", "confirm_public": True, "expected_version": 1}).json()
    export = clients["owner"].post(uri + "/exports", json={"format": "json"}).json()
    assert clients["owner"].delete(uri + "?expected_version=999").status_code == 409
    assert clients["owner"].delete(uri + "?expected_version=1").status_code == 200
    assert clients["owner"].get(uri).status_code == 404
    assert clients["owner"].get(f'/api/v1/exports/{export["id"]}/download').status_code == 404
    assert clients["outsider"].get(f'/api/v1/public/writeups/{pub["id"]}').status_code == 404


def test_ai_disabled_external_consent_real_provider_mock_transport_and_provenance(studio, monkeypatch):
    clients, _, _, _ = studio
    client = clients["owner"]
    assert client.get("/api/v1/ai/providers").json()["enabled"] is False
    assert client.post("/api/v1/ai/jobs", json={"task": "structure_notes", "notes": "real"}).status_code == 503
    monkeypatch.setattr(settings, "ai_enabled", True)
    assert client.post("/api/v1/ai/jobs", json={"task": "structure_notes", "notes": "real", "provider": "external", "external_consent": True}).status_code == 403
    assert client.post("/api/v1/ai/jobs", json={"task": "structure_notes"}).status_code == 422
    evidence = upload(studio, text=True)
    assert clients["outsider"].post("/api/v1/ai/jobs", json={"task": "ask_evidence", "evidence_ids": [evidence["id"]]}).status_code == 404
    captured = []
    def handle(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": json.dumps({"draft": "Rascunho [submitted-notes]", "inferences": ["Hipótese para revisão"], "gaps": ["Falta captura"]})}})
    real_client = httpx.Client
    monkeypatch.setattr(ai.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    response = client.post("/api/v1/ai/jobs", json={"task": "explain_commands", "notes": "$ whoami\nalice", "evidence_ids": [evidence["id"]]})
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["status"] == "completed", job
    assert job["output_data"]["human_review_required"] is True
    assert job["output_data"]["facts"][0]["observed_excerpt"] == "$ whoami\nalice"
    assert job["output_data"]["provenance"][1]["sha256"] == evidence["sha256"]
    assert job["output_data"]["draft_status"] == "unverified_ai_suggestion"
    assert captured[0]["stream"] is False and "não confiáveis" in captured[0]["messages"][0]["content"]
    assert clients["outsider"].get(f'/api/v1/ai/jobs/{job["id"]}').status_code == 404
    assert client.get("/api/v1/ai/jobs").json()["total"] == 1
    assert client.post(f'/api/v1/ai/jobs/{job["id"]}/cancel').status_code == 409


def test_ai_provider_failure_persists_and_quota(studio, monkeypatch):
    clients, _, _, _ = studio
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_max_jobs_per_hour", 1)
    def fail(*args):
        raise httpx.ReadTimeout("secret text must never be logged")
    monkeypatch.setattr(ai.OllamaProvider, "generate", fail)
    response = clients["owner"].post("/api/v1/ai/jobs", json={"task": "structure_notes", "notes": "real"})
    assert response.json()["status"] == "failed" and "secret" not in response.json()["error"]
    assert clients["owner"].post("/api/v1/ai/jobs", json={"task": "structure_notes", "notes": "real"}).status_code == 429
    cancelled = clients["owner"].post(f'/api/v1/ai/jobs/{response.json()["id"]}/cancel')
    assert cancelled.json()["status"] == "cancelled"


def test_export_size_limits_and_queue_unavailable_are_real_failure(studio, monkeypatch):
    clients, _, _, factory = studio
    item = create(studio)
    monkeypatch.setattr(settings, "max_export_bytes", 10)
    failed = clients["owner"].post(f'/api/v1/writeups/{item["id"]}/exports', json={"format": "markdown"})
    assert failed.json()["status"] == "failed"
    assert clients["owner"].get(f'/api/v1/exports/{failed.json()["id"]}/download').status_code == 409
    assert clients["owner"].post(f'/api/v1/exports/{failed.json()["id"]}/cancel').json()["status"] == "cancelled"
    monkeypatch.setattr(settings, "queue_enabled", True)
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
    response = clients["owner"].post(f'/api/v1/writeups/{item["id"]}/exports', json={"format": "json"})
    assert response.status_code == 503
    with factory() as db:
        row = db.get(Export, response.json()["detail"]["export_id"])
        assert row.status == "failed"


def test_frozen_export_preserves_requested_version_and_cancelled_claim(studio, monkeypatch):
    clients, users, _, factory = studio
    item = create(studio)
    from app.modules.studio import routes
    monkeypatch.setattr(routes, "enqueue", lambda *args: None)
    response = clients["owner"].post(f'/api/v1/writeups/{item["id"]}/exports', json={"format": "markdown"})
    job = response.json()
    assert job["status"] == "queued"
    clients["owner"].patch(f'/api/v1/writeups/{item["id"]}', json={"title": "Nova versão", "expected_version": 1})
    jobs.execute_export(job["id"])
    downloaded = clients["owner"].get(f'/api/v1/exports/{job["id"]}/download')
    assert downloaded.content.startswith(b"# Writeup real") and "Nova versão" not in downloaded.text
    cancelled = clients["owner"].post(f'/api/v1/writeups/{item["id"]}/exports', json={"format": "json"}).json()
    clients["owner"].post(f'/api/v1/exports/{cancelled["id"]}/cancel')
    jobs.execute_export(cancelled["id"])
    assert clients["owner"].get(f'/api/v1/exports/{cancelled["id"]}').json()["status"] == "cancelled"
