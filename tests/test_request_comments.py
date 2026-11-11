"""Comments and files on mentor requests (P15): the intern answers, the admin replies.

Intern routes are scoped by the session profile id like the other request routes (another intern's request
or file is 404); admin routes need the token. Files: .pdf/.docx/.png/.jpg by extension and magic bytes, at
most 3 of at most 5 MiB, JSON base64; downloads are attachments, never cached or sniffed. Deleting a request
deletes its thread and files. Comment text and files never reach the assistant or the turn logs."""

from __future__ import annotations

import base64
import io
import re
import uuid
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from app.agent import build_agent
from app.config import get_settings
from app.main import create_app
from app.request_comments import safe_filename
from app.schemas import (
    ErrorBody,
    InternSession,
    InternsResponse,
    MentorRequest,
    MentorRequestList,
    RequestComment,
    RequestThread,
)
from app.store import LocalStore

UNKNOWN = "6f1c2b9e-4d3a-4e8b-9c71-2a5d0e7f3b14"
PDF = b"%PDF-1.4\n% reply\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
Env = tuple[TestClient, dict[str, str], LocalStore]


def docx(with_document: bool = True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        if with_document:
            zf.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


def f64(name: str, data: bytes) -> dict[str, str]:
    return {"filename": name, "content_b64": base64.b64encode(data).decode("ascii")}


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    s = get_settings().model_copy(update={"data_live": tmp_path})
    store = LocalStore(tmp_path)
    client = TestClient(create_app(s, agent=build_agent(s, store=store), store=store))
    token = client.post("/api/admin/login", json={"password": s.admin_password.get_secret_value()}).json()["token"]
    yield client, {"Authorization": f"Bearer {token}"}, store
    store.close()


def err(r: Any, status: int, code: str, field: str | None = None) -> None:
    assert r.status_code == status, r.text
    body = ErrorBody.model_validate(r.json())
    assert body.error.code == code
    if field is not None:
        assert body.error.field == field, body.error


def setup(client: TestClient, auth: dict[str, str]) -> tuple[str, str, str, str]:
    """(sara's profile, omar's profile, sara's request, omar's request)."""
    interns = InternsResponse.model_validate(client.get("/api/interns").json()).interns
    sara, omar = interns[:2]
    pids = [InternSession.model_validate(client.post(f"/api/interns/{i.id}/session").json()).profile_id
            for i in (sara, omar)]
    rids = []
    for i in (sara, omar):
        r = client.post("/api/admin/requests", json={"intern_id": i.id, "kind": "read", "title": "اقرأ"}, headers=auth)
        rids.append(MentorRequestList.model_validate(r.json()).requests[0].id)
    return pids[0], pids[1], rids[0], rids[1]


def post(client: TestClient, rid: str, pid: str, body: str = "", files: list[dict[str, str]] | None = None) -> Any:
    return client.post(f"/api/requests/{rid}/comments", json={"profile_id": pid, "body": body, "files": files or []})


def test_thread_both_ways_with_files_and_counts(env: Env) -> None:
    client, auth, _ = env
    pid, _, rid, _ = setup(client, auth)
    r = post(client, rid, pid, "  قرأتها،\n\n\n\nوتعلمت أن النزاهة أولاً  ", [f64("ملخص القيم.pdf", PDF)])
    assert r.status_code == 201, r.text
    mine = RequestComment.model_validate(r.json())
    assert mine.author == "intern" and mine.body == "قرأتها،\n\nوتعلمت أن النزاهة أولاً" and mine.request_id == rid
    (pdf,) = mine.files
    assert (pdf.filename, pdf.content_type, pdf.size_bytes) == ("ملخص القيم.pdf", "application/pdf", len(PDF))

    r = client.post(f"/api/admin/requests/{rid}/comments", json={"body": "ممتاز", "files": [f64("مثال.PNG", PNG)]},
                    headers=auth)
    assert r.status_code == 201, r.text
    reply = RequestComment.model_validate(r.json())
    assert reply.author == "admin" and reply.files[0].content_type == "image/png"
    assert client.post(f"/api/admin/requests/{rid}/comments", json={"files": [f64("a.jpeg", JPG)]},
                       headers=auth).status_code == 201  # a file without text

    for thread in (client.get(f"/api/requests/{rid}/comments?profile_id={pid}"),
                   client.get(f"/api/admin/requests/{rid}/comments", headers=auth)):
        assert thread.status_code == 200, thread.text
        t = RequestThread.model_validate(thread.json())
        assert t.request_id == rid and [c.author for c in t.comments] == ["intern", "admin", "admin"]
        assert t.comments[0].id == mine.id

    listed = MentorRequestList.model_validate(client.get(f"/api/requests?profile_id={pid}").json())
    assert listed.requests[0].comment_count == 3
    admin_list = MentorRequestList.model_validate(client.get("/api/admin/requests", headers=auth).json())
    assert {r.id: r.comment_count for r in admin_list.requests}[rid] == 3
    patched = client.patch(f"/api/requests/{rid}", json={"profile_id": pid, "status": "done"})
    assert MentorRequest.model_validate(patched.json()).comment_count == 3
    edited = client.patch(f"/api/admin/requests/{rid}", json={"title": "عنوان"}, headers=auth)
    assert MentorRequest.model_validate(edited.json()).comment_count == 3


def test_downloads_are_attachments_through_the_app(env: Env) -> None:
    client, auth, _ = env
    pid, _, rid, _ = setup(client, auth)
    c = RequestComment.model_validate(post(client, rid, pid, "", [f64("تقرير نهائي.pdf", PDF)]).json())
    fid = c.files[0].id
    for r in (client.get(f"/api/requests/{rid}/files/{fid}?profile_id={pid}"),
              client.get(f"/api/admin/requests/{rid}/files/{fid}", headers=auth)):
        assert r.status_code == 200
        assert r.content == PDF
        assert r.headers["content-type"] == "application/pdf"
        assert r.headers["content-disposition"] == f"attachment; filename*=UTF-8''{quote('تقرير نهائي.pdf', safe='')}"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["cache-control"] == "no-store"
    err(client.get(f"/api/requests/{rid}/files/{UNKNOWN}?profile_id={pid}"), 404, "not_found")
    err(client.get(f"/api/requests/{rid}/files/nope?profile_id={pid}"), 404, "not_found")
    err(client.get(f"/api/admin/requests/{rid}/files/{UNKNOWN}", headers=auth), 404, "not_found")


def test_intern_sees_only_their_own(env: Env) -> None:
    client, auth, _ = env
    pid_sara, pid_omar, rid_sara, rid_omar = setup(client, auth)
    c = RequestComment.model_validate(post(client, rid_omar, pid_omar, "لعمر", [f64("a.png", PNG)]).json())
    fid = c.files[0].id
    # Sara: Omar's request, its thread and its file are 404 (no hint they exist), and nothing is written
    err(client.get(f"/api/requests/{rid_omar}/comments?profile_id={pid_sara}"), 404, "not_found")
    err(post(client, rid_omar, pid_sara, "سارة"), 404, "not_found")
    err(client.get(f"/api/requests/{rid_omar}/files/{fid}?profile_id={pid_sara}"), 404, "not_found")
    # a file id of Omar's request asked through Sara's own request is 404 too
    err(client.get(f"/api/requests/{rid_sara}/files/{fid}?profile_id={pid_sara}"), 404, "not_found")
    err(client.get(f"/api/admin/requests/{rid_sara}/files/{fid}", headers=auth), 404, "not_found")
    assert len(RequestThread.model_validate(
        client.get(f"/api/requests/{rid_omar}/comments?profile_id={pid_omar}").json()).comments) == 1
    # profile checks
    err(client.get(f"/api/requests/{rid_sara}/comments"), 400, "validation_error", "profile_id")
    err(client.get(f"/api/requests/{rid_sara}/files/{fid}"), 400, "validation_error", "profile_id")
    err(client.get(f"/api/requests/{rid_sara}/comments?profile_id={UNKNOWN}"), 404, "not_found")
    err(client.get(f"/api/requests/{UNKNOWN}/comments?profile_id={pid_sara}"), 404, "not_found")
    err(post(client, rid_sara, "nope", "x"), 400, "validation_error", "profile_id")
    anon = client.post("/api/profiles", json={"role": "Sales"}).json()["profile_id"]
    err(client.get(f"/api/requests/{rid_sara}/comments?profile_id={anon}"), 404, "not_found")
    # the admin sees every thread
    assert client.get(f"/api/admin/requests/{rid_omar}/comments", headers=auth).status_code == 200
    err(client.get(f"/api/admin/requests/{UNKNOWN}/comments", headers=auth), 404, "not_found")


def test_admin_routes_need_the_token(env: Env) -> None:
    client, auth, _ = env
    pid, _, rid, _ = setup(client, auth)
    fid = RequestComment.model_validate(post(client, rid, pid, "", [f64("a.png", PNG)]).json()).files[0].id
    err(client.get(f"/api/admin/requests/{rid}/comments"), 401, "unauthorized")
    err(client.post(f"/api/admin/requests/{rid}/comments", json={"body": "x"}), 401, "unauthorized")
    err(client.get(f"/api/admin/requests/{rid}/files/{fid}"), 401, "unauthorized")
    bad = {"Authorization": "Bearer 1.nope"}
    err(client.get(f"/api/admin/requests/{rid}/files/{fid}", headers=bad), 401, "unauthorized")
    # without a token the admin route keeps the 32 KB body limit
    big = {"files": [f64("a.png", PNG + b"\x00" * 64 * 1024)]}
    err(client.post(f"/api/admin/requests/{rid}/comments", json=big), 413, "payload_too_large")


def test_validation(env: Env) -> None:
    client, auth, _ = env
    pid, _, rid, _ = setup(client, auth)
    six_mib = PNG + b"\x00" * (6 * 1024 * 1024)
    cases: list[tuple[str, list[dict[str, str]], str]] = [
        ("", [], "body"),  # neither text nor a file
        ("   \n  ", [], "body"),
        ("راسلني a@b.co", [], "body"),
        ("افتح https://example.com", [], "body"),
        ("اتصل ٠٧٩١٢٣٤٥٦٧", [], "body"),
        ("x", [f64("a.exe", b"MZ\x90\x00")], "files"),  # not on the allow-list
        ("x", [f64("notes.txt", b"hello")], "files"),
        ("x", [f64("noext", PDF)], "files"),
        ("x", [f64("a.pdf", PNG)], "files"),  # extension and magic bytes disagree
        ("x", [f64("a.png", PDF)], "files"),
        ("x", [f64("a.jpg", PNG)], "files"),
        ("x", [f64("a.docx", b"PK\x03\x04 not a zip")], "files"),
        ("x", [f64("a.docx", docx(with_document=False))], "files"),
        ("x", [f64("a.png", six_mib)], "files"),
        ("x", [f64("a.png", b"")], "files"),
        ("x", [{"filename": "a.png", "content_b64": "not base64!"}], "files"),
        ("x", [f64("a.png", PNG)] * 4, "files"),
    ]
    for body, files, field in cases:
        r = post(client, rid, pid, body, files)
        assert r.status_code == 400, (body, [f["filename"] for f in files], r.text)
        assert ErrorBody.model_validate(r.json()).error.field == field, (body, r.text)
    err(client.post(f"/api/requests/{rid}/comments", json={"profile_id": pid, "body": "ن" * 1001}), 400,
        "validation_error", "body")
    err(client.post(f"/api/requests/{rid}/comments", json={"profile_id": pid, "body": "x", "score": 1}), 400,
        "validation_error")
    assert RequestThread.model_validate(
        client.get(f"/api/requests/{rid}/comments?profile_id={pid}").json()).comments == []
    # the allowed kinds, three at once, a long name and a path in the name
    ok = post(client, rid, pid, "ن" * 1000, [f64("../../etc/تقرير.docx", docx()), f64("C:\\x\\صورة.JPG", JPG),
                                             f64("ا" * 200 + ".pdf", PDF)])
    assert ok.status_code == 201, ok.text
    names = [f.filename for f in RequestComment.model_validate(ok.json()).files]
    assert names[:2] == ["تقرير.docx", "صورة.JPG"] and len(names[2]) == 120 and names[2].endswith(".pdf")
    assert [f.content_type for f in RequestComment.model_validate(ok.json()).files] == [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "image/jpeg", "application/pdf"]


def test_safe_filename() -> None:
    assert safe_filename("../../a/b/report.pdf") == "report.pdf"
    assert safe_filename("C:\\Users\\me\\cv.docx") == "cv.docx"
    assert safe_filename("ev\u202eil\x00\x07.pdf") == "evil.pdf"  # bidi override and control characters
    assert safe_filename("  my   file .png ") == "my file.png"
    assert safe_filename(".pdf") == "pdf"
    long = safe_filename("x" * 300 + ".jpeg")
    assert len(long) == 120 and long.endswith(".jpeg")


def test_big_comment_body_is_accepted_on_the_comment_route_only(env: Env) -> None:
    client, auth, _ = env
    pid, _, rid, _ = setup(client, auth)
    big = PNG + b"\x00" * (4 * 1024 * 1024)
    assert post(client, rid, pid, "", [f64("a.png", big)] * 3).status_code == 201
    r = client.get(f"/api/requests/{rid}/comments?profile_id={pid}")
    assert [f.size_bytes for f in RequestThread.model_validate(r.json()).comments[0].files] == [len(big)] * 3
    err(client.patch(f"/api/requests/{rid}", json={"profile_id": pid, "status": "done", "x": "y" * 40000}), 413,
        "payload_too_large")


def test_deleting_a_request_deletes_its_thread_and_files(env: Env) -> None:
    client, auth, store = env
    pid, _, rid, _ = setup(client, auth)
    c = RequestComment.model_validate(post(client, rid, pid, "تم", [f64("a.pdf", PDF)]).json())
    path = store.files_dir / rid / c.files[0].id
    assert path.read_bytes() == PDF
    assert client.delete(f"/api/admin/requests/{rid}", headers=auth).status_code == 200
    assert store.table_rows("mentor_request_comments") == [] and store.table_rows("mentor_request_files") == []
    assert not path.exists()
    err(client.get(f"/api/requests/{rid}/comments?profile_id={pid}"), 404, "not_found")
    err(client.get(f"/api/admin/requests/{rid}/files/{c.files[0].id}", headers=auth), 404, "not_found")


def test_comment_text_and_files_never_reach_the_chat_or_turn_logs(env: Env) -> None:
    client, auth, store = env
    pid, _, rid, _ = setup(client, auth)
    post(client, rid, pid, "تعليقٌ فريدٌ جداً", [f64("ملفٌ فريد.pdf", PDF)])
    client.post(f"/api/admin/requests/{rid}/comments", json={"body": "ردٌّ فريدٌ"}, headers=auth)
    chat = client.post("/api/chat", json={"message": "ما قيم الشركة الخمس؟", "role": "Sales", "profile_id": pid}).text
    assert "فريد" not in chat and "%PDF" not in chat
    assert "فريد" not in str(store.table_rows("turn_logs"))
    thread = client.get(f"/api/admin/requests/{rid}/comments", headers=auth).text
    assert not re.search(r"score|grade|rating|storage|sha256|requests/", thread)
    # the assistant's code never imports the thread module
    root = Path(__file__).resolve().parents[1] / "app"
    for name in ("agent.py", "answer.py", "router.py", "tools.py", "smalltalk.py", "factcheck.py"):
        assert "request_comments" not in (root / name).read_text(encoding="utf-8"), name
    for path in (root / "llm").rglob("*.py"):
        assert "request_comments" not in path.read_text(encoding="utf-8"), path.name


def test_unavailable_store_answers_503(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    client, auth, store = env
    pid, _, rid, _ = setup(client, auth)
    monkeypatch.setattr(store, "request_comments", lambda _rid: None)
    monkeypatch.setattr(store, "request_comment_add", lambda *_a: None)
    monkeypatch.setattr(store, "request_file", lambda *_a: None)
    monkeypatch.setattr(store, "request_comment_counts", lambda _ids: None)
    err(client.get(f"/api/requests/{rid}/comments?profile_id={pid}"), 503, "requests_unavailable")
    err(post(client, rid, pid, "x"), 503, "requests_unavailable")
    err(client.get(f"/api/admin/requests/{rid}/files/{UNKNOWN}", headers=auth), 503, "requests_unavailable")
    err(client.post(f"/api/admin/requests/{rid}/comments", json={"body": "x"}, headers=auth), 503,
        "requests_unavailable")
    # the requests themselves keep working (no comment tables yet: count 0)
    listed = MentorRequestList.model_validate(client.get(f"/api/requests?profile_id={pid}").json())
    assert listed.requests[0].comment_count == 0
    assert uuid.UUID(listed.requests[0].id)
