# SPDX-License-Identifier: MIT
import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import Base, get_db, make_engine
from app.models import Challenge, Evidence, EvidenceVersion, Team, TeamMember, User
from app.modules.evidence import jobs, storage
from app.modules.evidence.routes import router
from app.modules.evidence.schemas import AnnotationCreate, AnnotationData
from app.modules.evidence.service import annotate
from app.modules.identity.routes import router as identity_router


def png(color="white", size=(100, 80)):
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format="PNG")
    return out.getvalue()


@pytest.fixture
def evidence_env(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{tmp_path}/evidence-tests.db")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "objects"))
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "queue_enabled", False)
    monkeypatch.setattr(settings, "cookie_secure", False)
    monkeypatch.setattr(settings, "max_upload_bytes", 20 * 1024 * 1024)
    monkeypatch.setattr(settings, "login_rate_limit", 100)
    monkeypatch.setattr(settings, "rate_limit_backend", "memory")
    monkeypatch.setattr(jobs, "SessionLocal", sessions)
    api = FastAPI()
    api.include_router(identity_router, prefix="/api/v1")
    api.include_router(router, prefix="/api/v1")
    def dependency():
        with sessions() as session:
            yield session
    api.dependency_overrides[get_db] = dependency
    clients = []
    def registered(name="alice"):
        client = TestClient(api)
        result = client.post("/api/v1/auth/register", json={"email": f"{name}@example.com", "name": name,
                                                           "password": "CorrectHorse!Battery7"})
        assert result.status_code == 201, result.text
        client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        clients.append(client)
        return client, result.json()["user"]["id"]
    yield api, sessions, registered
    for client in clients:
        client.close()
    engine.dispose()


def upload(client, content=None, filename="capture.png", mime="image/png", **kwargs):
    return client.post("/api/v1/evidences", data=kwargs,
                       files={"file": (filename, png() if content is None else content, mime)})


def annotation(version=1, **kwargs):
    result = {"expected_version": version, "data": {"schema_version": 1, "width": 100, "height": 80,
               "shapes": [{"id": "redact1", "type": "redact", "x": 10, "y": 10, "width": 30, "height": 20}]}}
    result["data"].update(kwargs)
    return result


def test_upload_hash_capture_server_time_original_thumbnail_and_download(evidence_env):
    _, _, register = evidence_env
    client, owner = register()
    original = png()
    result = upload(client, original, captured_at="2026-01-02T03:04:05-03:00", origin="Kali terminal", tags='["web","proof"]')
    assert result.status_code == 201, result.text
    data = result.json()
    assert data["owner_id"] == owner
    assert data["sha256"] == hashlib.sha256(original).hexdigest()
    assert data["metadata"]["width"] == 100
    assert data["captured_at"].startswith("2026-01-02T06:04:05")
    assert data["received_at"] != data["captured_at"]
    assert "storage_key" not in data
    response = client.get(f'/api/v1/evidences/{data["id"]}/download')
    assert response.content == original
    assert response.headers["content-disposition"].startswith("attachment;")
    preview = client.get(f'/api/v1/evidences/{data["id"]}/thumbnail')
    assert preview.status_code == 200
    assert Image.open(io.BytesIO(preview.content)).format == "PNG"
    listed = client.get("/api/v1/evidences?tag=proof").json()
    assert listed["total"] == 1
    timeline = client.get(f'/api/v1/timeline?evidence_id={data["id"]}').json()
    assert timeline["items"][0]["event_type"] == "upload"
    assert timeline["items"][0]["details"]["received_at_server"] != timeline["items"][0]["details"]["captured_at_declared"]


@pytest.mark.parametrize("filename,mime,body", [
    ("evil.png", "image/png", b"<html>fake PNG</html>"),
    ("wrong.jpg", "image/jpeg", png()),
    ("capture.png", "text/plain", png()),
    ("bad.json", "application/json", b"{bad json}"),
    ("nan.json", "application/json", b'{"secret":NaN}'),
    ("binary.txt", "text/plain", b"text\x00binary"),
    ("fake.pdf", "application/pdf", b"%PDF-1.4 missing EOF"),
    ("fake.pcap", "application/vnd.tcpdump.pcap", b"not a capture"),
    ("danger.svg", "image/svg+xml", b'<svg onload="alert(1)"/>'),
])
def test_reject_spoofed_and_malformed_files(evidence_env, filename, mime, body):
    _, _, register = evidence_env
    client, _ = register()
    assert upload(client, body, filename, mime).status_code == 422
    assert client.get("/api/v1/evidences").json()["total"] == 0


def test_limits_csrf_dates_and_archives(evidence_env, monkeypatch):
    _, _, register = evidence_env
    client, _ = register()
    monkeypatch.setattr(settings, "max_upload_bytes", 1024)
    assert upload(client, b"a" * 1025, "huge.log", "text/plain").status_code == 413
    assert upload(client, png(), captured_at="2026-01-02T03:04:05").status_code == 422
    import zipfile
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("proof.txt", "authentic text")
    assert upload(client, archive.getvalue(), "proof.zip", "application/zip").status_code == 422
    client.headers.pop("X-CSRF-Token")
    assert upload(client).status_code == 403


def test_annotations_redact_real_pixels_original_immutable_crop_versions_cas(evidence_env):
    _, _, register = evidence_env
    client, _ = register()
    original = png()
    eid = upload(client, original).json()["id"]
    result = client.post(f"/api/v1/evidences/{eid}/annotations", json=annotation(crop={"x": 0, "y": 0, "width": 70, "height": 60}))
    assert result.status_code == 201, result.text
    data = result.json()
    assert data["version"] == 2
    version_id = data["derived_version"]["id"]
    response = client.get(f"/api/v1/evidences/{eid}/versions/{version_id}/download")
    image = Image.open(io.BytesIO(response.content))
    assert image.size == (70, 60)
    assert image.getpixel((20, 20)) == (0, 0, 0, 255)
    assert image.getpixel((55, 40)) == (255, 255, 255, 255)
    assert client.get(f"/api/v1/evidences/{eid}/download").content == original
    assert data["derived_version"]["sha256"] == hashlib.sha256(response.content).hexdigest()
    assert client.post(f"/api/v1/evidences/{eid}/annotations", json=annotation()).status_code == 409
    assert client.get(f"/api/v1/evidences/{eid}/annotations").json()["total"] == 1
    kinds = {item["kind"] for item in client.get(f"/api/v1/evidences/{eid}/versions").json()["items"]}
    assert kinds == {"original", "thumbnail", "annotated"}


@pytest.mark.parametrize("mutation", [
    {"width": 99},
    {"shapes": [{"id": "x", "type": "redact", "x": 90, "y": 10, "width": 20, "height": 10}]},
    {"shapes": [{"id": "x", "type": "arrow", "x": 1, "y": 1}]},
    {"shapes": [{"id": "x", "type": "text", "x": 1, "y": 1, "text": "x", "color": "url(https://bad)"}]},
    {"crop": {"x": 1, "y": 1, "width": 110, "height": 20}},
    {"shapes": [{"id": "x", "type": "step", "x": 1, "y": 1}, {"id": "x", "type": "step", "x": 2, "y": 2}]},
])
def test_annotation_schema_geometry_validation(evidence_env, mutation):
    _, _, register = evidence_env
    client, _ = register()
    eid = upload(client).json()["id"]
    result = client.post(f"/api/v1/evidences/{eid}/annotations", json=annotation(**mutation))
    assert result.status_code == 422, result.text
    assert client.get(f"/api/v1/evidences/{eid}").json()["version"] == 1


def test_all_private_routes_deny_other_user_and_unsigned_anonymous(evidence_env):
    api, _, register = evidence_env
    owner, _ = register("owner")
    stranger, _ = register("stranger")
    eid = upload(owner).json()["id"]
    vid = owner.get(f"/api/v1/evidences/{eid}/versions").json()["items"][0]["id"]
    ticket = owner.post(f"/api/v1/evidences/{eid}/download-ticket", json={}).json()["url"]
    for path in (f"/api/v1/evidences/{eid}", f"/api/v1/evidences/{eid}/download",
                 f"/api/v1/evidences/{eid}/thumbnail", f"/api/v1/evidences/{eid}/versions",
                 f"/api/v1/evidences/{eid}/annotations", f"/api/v1/evidences/{eid}/versions/{vid}/download", ticket):
        assert stranger.get(path).status_code == 404
    assert stranger.post(f"/api/v1/evidences/{eid}/annotations", json=annotation()).status_code == 404
    assert stranger.get("/api/v1/timeline").json()["total"] == 0
    assert stranger.get("/api/v1/evidences").json()["total"] == 0
    anonymous = TestClient(api)
    assert anonymous.get(ticket).status_code == 401
    assert owner.get(ticket).status_code == 200
    assert owner.get(ticket + "x").status_code == 403


def test_team_viewer_can_download_but_cannot_edit_and_scope_fks(evidence_env):
    _, sessions, register = evidence_env
    owner, owner_id = register("owner")
    viewer, viewer_id = register("viewer")
    outsider, outsider_id = register("outsider")
    with sessions() as db:
        team = Team(name="CTF team", owner_id=owner_id)
        db.add(team)
        db.flush()
        db.add_all([TeamMember(team_id=team.id, user_id=owner_id, role="manager"),
                    TeamMember(team_id=team.id, user_id=viewer_id, role="viewer")])
        challenge = Challenge(owner_id=owner_id, team_id=team.id, name="challenge", category="Web", visibility="team")
        db.add(challenge)
        db.commit()
        tid, cid = team.id, challenge.id
    response = upload(owner, team_id=tid, challenge_id=cid, visibility="team")
    assert response.status_code == 201, response.text
    eid = response.json()["id"]
    assert viewer.get(f"/api/v1/evidences/{eid}/download").status_code == 200
    assert viewer.post(f"/api/v1/evidences/{eid}/annotations", json=annotation()).status_code == 403
    assert viewer.patch(f"/api/v1/evidences/{eid}", json={"expected_version": 1, "name": "edited"}).status_code == 403
    assert outsider.get(f"/api/v1/evidences/{eid}/download").status_code == 403
    assert upload(owner, challenge_id=cid).status_code == 422
    assert upload(outsider, team_id=tid, visibility="team").status_code == 403


def test_metadata_cas_cannot_forge_dimensions_and_soft_delete(evidence_env):
    _, _, register = evidence_env
    client, _ = register()
    eid = upload(client).json()["id"]
    first = client.patch(f"/api/v1/evidences/{eid}", json={"expected_version": 1, "description": "authentic source",
                         "metadata": {"width": 1, "manual_order": 2}})
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 2
    assert first.json()["metadata"]["width"] == 100
    assert client.patch(f"/api/v1/evidences/{eid}", json={"expected_version": 1, "description": "lost"}).status_code == 409
    assert client.delete(f"/api/v1/evidences/{eid}?expected_version=1").status_code == 409
    assert client.delete(f"/api/v1/evidences/{eid}?expected_version=2").status_code == 200
    assert client.get(f"/api/v1/evidences/{eid}/download").status_code == 404
    assert client.get("/api/v1/evidences").json()["total"] == 0


def test_parallel_annotation_has_one_winner_without_lost_revision(evidence_env):
    _, sessions, register = evidence_env
    client, actor_id = register()
    eid = upload(client).json()["id"]
    import threading
    barrier = threading.Barrier(2)
    def save():
        with sessions() as db:
            evidence = db.get(Evidence, eid)
            actor = db.get(User, actor_id)
            barrier.wait(timeout=5)
            try:
                return annotate(db, actor, evidence, AnnotationCreate.model_validate(annotation()))["version"]
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: save(), range(2))) == [2, 409]
    assert client.get(f"/api/v1/evidences/{eid}/annotations").json()["total"] == 1


def test_render_all_shapes_preserves_original_and_order():
    from app.modules.evidence.rendering import render_annotation
    shapes = [
        {"id": "arrow", "type": "arrow", "x": 1, "y": 1, "x2": 20, "y2": 20},
        {"id": "line", "type": "line", "x": 1, "y": 2, "x2": 30, "y2": 30},
        {"id": "rect", "type": "rect", "x": 30, "y": 10, "width": 10, "height": 10},
        {"id": "circle", "type": "circle", "x": 50, "y": 10, "width": 10, "height": 10},
        {"id": "text", "type": "text", "x": 1, "y": 40, "text": "observado"},
        {"id": "highlight", "type": "highlight", "x": 10, "y": 10, "width": 10, "height": 10},
        {"id": "step", "type": "step", "x": 75, "y": 55},
        {"id": "blur", "type": "blur", "x": 1, "y": 40, "width": 50, "height": 25},
        {"id": "redact", "type": "redact", "x": 10, "y": 10, "width": 10, "height": 10},
    ]
    data = AnnotationData.model_validate({"width": 100, "height": 80, "shapes": shapes})
    assert data.shapes[6].number == 1
    image = Image.open(io.BytesIO(render_annotation(png(), data)))
    assert image.getpixel((15, 15)) == (0, 0, 0, 255)
