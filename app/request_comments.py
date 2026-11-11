"""Comments and files on mentor requests (P15): the intern answers a request, the admin replies.

What it does: checks a new comment before any store writes it: the body follows the same contact rule as
request titles and notes (`verify.has_contact_or_link`), a comment needs a body or at least one file, and
each file is decoded from base64 and allowed only by extension AND magic bytes (.pdf `%PDF-`, .docx a zip
with `word/document.xml` inside the document import's zip-bomb limits, .png the PNG signature, .jpg/.jpeg
`FF D8 FF`), 1 byte to 5 MiB, at most 3. File names are reduced to a safe base name. It shapes stored rows
into the contract (`RequestComment`, `RequestThread`) and builds the download headers.
What it must never do: render or preview a file, hand the browser a storage URL, hold a score, or let
comment text or file bytes reach the assistant (the agent, answer, LLM and prompt code never import this
module; comments are shown to the intern and the admin only).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import unicodedata
import uuid
import zipfile
from typing import Any
from urllib.parse import quote

from app import schemas
from app.errors import ApiError
from app.kb_import.extract import DOCX_MAX_ENTRIES, DOCX_MAX_UNCOMPRESSED
from app.mentor_requests import iso
from app.store.base import now_iso, storage_key
from app.verify import has_contact_or_link

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
#: Extension -> stored content type (the only files a comment may carry).
TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": DOCX_TYPE,
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}
_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"
_PDF = b"%PDF-"
ALLOWED_LABEL = ".pdf .docx .png .jpg .jpeg"


def _bad(message: str, field: str = "files") -> ApiError:
    return ApiError("validation_error", 400, message, field)


def safe_filename(name: str) -> str:
    """Base name only: no folders, no control or format characters (bidi overrides included), no path
    separators; the extension is kept and the whole name is at most 120 characters."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = "".join(ch for ch in unicodedata.normalize("NFC", base) if not unicodedata.category(ch).startswith("C"))
    base = " ".join(base.split()).strip(" .")
    stem, dot, ext = base.rpartition(".")
    if not dot:
        stem, ext = base, ""
    ext = ext[:10]
    stem = stem.strip(" .") or "file"
    room = schemas.COMMENT_FILENAME_MAX - (len(ext) + 1 if ext else 0)
    return f"{stem[:room].rstrip(' .') or 'file'}.{ext}" if ext else stem[: schemas.COMMENT_FILENAME_MAX]


def extension(filename: str) -> str:
    _, dot, ext = filename.rpartition(".")
    return ext.lower() if dot else ""


def _docx_ok(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            if len(infos) > DOCX_MAX_ENTRIES or sum(i.file_size for i in infos) > DOCX_MAX_UNCOMPRESSED:
                return False
            return "word/document.xml" in zf.namelist()
    except (zipfile.BadZipFile, OSError, ValueError, EOFError):
        return False


def magic_ok(ext: str, data: bytes) -> bool:
    """True when the bytes are the kind of file the extension says."""
    if ext == "pdf":
        return data.startswith(_PDF)
    if ext == "png":
        return data.startswith(_PNG)
    if ext in ("jpg", "jpeg"):
        return data.startswith(_JPEG)
    if ext == "docx":
        return data.startswith(b"PK\x03\x04") and _docx_ok(data)
    return False


def _decode(b64: str, name: str) -> bytes:
    raw = "".join(b64.split())
    if raw.startswith("data:") and "," in raw:  # tolerate a data URL prefix
        raw = raw.split(",", 1)[1]
    if len(raw) > ((schemas.COMMENT_FILE_MAX_BYTES + 2) // 3) * 4 + 4:
        raise _bad(f"{name}: each file must be at most 5 MB")
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise _bad(f"{name}: content_b64 is not valid base64") from None
    if not data:
        raise _bad(f"{name}: the file is empty")
    if len(data) > schemas.COMMENT_FILE_MAX_BYTES:
        raise _bad(f"{name}: each file must be at most 5 MB")
    return data


def prepare(
    request_id: str, author: str, body: schemas.AdminCommentCreate
) -> tuple[dict[str, Any], list[dict[str, Any]], list[bytes]]:
    """The comment record, its file records and their bytes, or a 400 ApiError (`field` body or files)."""
    text = body.body
    if has_contact_or_link(text) is not None:
        raise _bad("body must not contain an email, a link or a phone number", "body")
    if not text.strip() and not body.files:
        raise _bad("write a reply or attach a file", "body")
    if len(body.files) > schemas.COMMENT_FILES_MAX:
        raise _bad(f"at most {schemas.COMMENT_FILES_MAX} files per comment")
    cid = str(uuid.uuid4())
    at = now_iso()
    files: list[dict[str, Any]] = []
    blobs: list[bytes] = []
    for f in body.files:
        name = safe_filename(f.filename)
        ext = extension(name)
        if ext not in TYPES:
            raise _bad(f"{name}: allowed files are {ALLOWED_LABEL}")
        data = _decode(f.content_b64, name)
        if not magic_ok(ext, data):
            raise _bad(f"{name}: the content is not a .{ext} file")
        fid = str(uuid.uuid4())
        files.append({"id": fid, "comment_id": cid, "request_id": request_id, "filename": name,
                      "content_type": TYPES[ext], "size_bytes": len(data),
                      "sha256": hashlib.sha256(data).hexdigest(), "storage_key": storage_key(request_id, fid),
                      "created_at": at})
        blobs.append(data)
    comment = {"id": cid, "request_id": request_id, "author": author, "body": text, "created_at": at}
    return comment, files, blobs


def view(rec: dict[str, Any]) -> schemas.RequestComment:
    files = [schemas.RequestFile(id=f["id"], filename=f["filename"], content_type=f["content_type"],
                                 size_bytes=int(f["size_bytes"]))
             for f in rec.get("files") or []]
    return schemas.RequestComment(id=rec["id"], request_id=rec["request_id"], author=rec["author"],
                                  body=rec.get("body") or "", created_at=iso(rec["created_at"]), files=files)


def thread(request_id: str, recs: list[dict[str, Any]]) -> schemas.RequestThread:
    return schemas.RequestThread(request_id=request_id, comments=[view(r) for r in recs])


def download_headers(rec: dict[str, Any]) -> dict[str, str]:
    """Always an attachment (never shown inline), never cached, never sniffed."""
    return {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(str(rec['filename']), safe='')}",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    }


__all__ = ["TYPES", "download_headers", "extension", "magic_ok", "prepare", "safe_filename", "thread", "view"]
