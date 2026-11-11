"""Document import service (P12.1): upload -> passage drafts -> admin review -> added K-rows.

What it does: `create_import` decodes the base64 upload in memory, extracts the text, optionally lets the
pinned model pick the title lines of a PDF or text file (P13.4, same opt-in as organizing), chunks it, labels the
passages (offline, or with the pinned model when the admin asked for it in LLM mode) and stores the import
record and its drafts. `approve` turns pending drafts into normal added K-rows through
`KnowledgeBase.add_many` (next free ids, history `editor`, one reindex), in draft order, and marks the
drafts approved with their row id. `after_kb_reset` puts approved drafts back to `draft` (the reset removed
their rows). `patch_draft` edits or discards a pending draft.

What it must never do: store the uploaded bytes, make any draft answerable before the admin approves it,
change draft text with a model, or raise anything but `ApiError` to the API (store problems are 503).
"""

from __future__ import annotations

import base64
import binascii
import time
import uuid
from collections import Counter
from pathlib import PurePath
from typing import Any

from pydantic import ValidationError

from app.errors import ApiError
from app.kb import KnowledgeBase, Row
from app.kb_import.chunk import chunk
from app.kb_import import extract as extraction
from app.kb_import.extract import ImportRejected, extract
from app.kb_import.organize import ORGANIZE_MAX_S, Summary, organize
from app.kb_import.titles import TITLES_MAX_S, TitlesSummary, detect_titles
from app.logging_setup import log_event
from app.schemas import (
    IMPORT_FILE_MAX_BYTES,
    IMPORT_MAX_PASSAGES,
    DraftPatch,
    ImportCapabilities,
    ImportCreate,
    ImportDetail,
    ImportListResponse,
    KbDraft,
    KbImport,
    KbNewRow,
    OrganizeSummary,
    clean_line,
)
from app.store.base import now_iso

UNAVAILABLE = "document import is unavailable: the store has no import tables (apply migration 0003) or failed"


def unavailable() -> ApiError:
    return ApiError("imports_unavailable", 503, UNAVAILABLE)


def capabilities(ai_available: bool) -> ImportCapabilities:
    return ImportCapabilities(types=extraction.supported_types(), pdf=extraction.pdf_available(), max_bytes=IMPORT_FILE_MAX_BYTES,  # type: ignore[arg-type]
                              max_passages=IMPORT_MAX_PASSAGES, ai_available=ai_available)


def _decode(b64: str) -> bytes:
    raw = "".join(b64.split())
    if raw.startswith("data:") and "," in raw:  # tolerate a data URL prefix
        raw = raw.split(",", 1)[1]
    if len(raw) > (IMPORT_FILE_MAX_BYTES * 4) // 3 + 8:
        raise ApiError("payload_too_large", 413, f"file larger than {IMPORT_FILE_MAX_BYTES // (1024 * 1024)} MB")
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise ApiError("validation_error", 400, "content_b64 is not valid base64", "content_b64") from None
    if len(data) > IMPORT_FILE_MAX_BYTES:
        raise ApiError("payload_too_large", 413, f"file larger than {IMPORT_FILE_MAX_BYTES // (1024 * 1024)} MB")
    return data


def _document_name(filename: str, given: str | None) -> str:
    if given:
        return given
    stem = clean_line(PurePath(filename.replace("\\", "/")).stem.replace("_", " "))
    return (stem[:80].strip() or "Imported document")


def _with_counts(record: dict[str, Any], drafts: list[dict[str, Any]]) -> KbImport:
    c = Counter(str(d["status"]) for d in drafts)
    return KbImport.model_validate({**record, "created_at": str(record["created_at"]), "approved": c["approved"],
                                    "pending": c["draft"], "discarded": c["discarded"]})


def _draft(d: dict[str, Any]) -> KbDraft:
    return KbDraft.model_validate({**d, "created_at": str(d["created_at"]), "updated_at": str(d["updated_at"]),
                                   "keyword_en": d.get("keyword_en") or ""})


def create_import(store: Any, kb: KnowledgeBase, body: ImportCreate, *, llm: Any | None, use_llm: bool) -> ImportDetail:
    filename = PurePath(body.filename.replace("\\", "/")).name or "document"
    data = _decode(body.content_b64)
    try:
        kind, blocks, pages = extract(filename, data)
    except ImportRejected as exc:
        raise ApiError("validation_error", 400, exc.message, exc.field) from None
    started = time.monotonic()
    blocks, titles = detect_titles(kind, blocks, requested=body.organize, llm=llm, use_llm=use_llm,
                                   max_s=min(TITLES_MAX_S, ORGANIZE_MAX_S))
    passages = chunk(blocks)
    if not passages:
        raise ApiError("validation_error", 400, "no readable text found in the file", "content_b64")
    if len(passages) > IMPORT_MAX_PASSAGES:
        raise ApiError("validation_error", 400, f"more than {IMPORT_MAX_PASSAGES} passages: split the document",
                       "passages")
    topics = sorted({r.topic for r in kb.rows()})
    items, summary = organize(passages, topics, requested=body.organize, llm=llm, use_llm=use_llm,
                              max_s=max(0.0, ORGANIZE_MAX_S - (time.monotonic() - started)))
    at = now_iso()
    record = {"id": str(uuid.uuid4()), "filename": filename[:120], "document_name": _document_name(filename, body.document_name),
              "file_type": kind, "pages": pages, "passages": len(items), "organized": summary.used and summary.organized > 0,
              "status": "open", "created_at": at}
    drafts = [{"id": str(uuid.uuid4()), "import_id": record["id"], "ord": i, "page": min(max(it.page, 0), 999),
               "text_ar": it.text, "topic": it.topic, "keyword_en": it.keyword_en, "question_ar": it.question_ar,
               "status": "discarded" if it.skip else "draft", "row_id": None, "created_at": at, "updated_at": at}
              for i, it in enumerate(items)]
    if not store.kb_import_create(record, drafts):
        raise unavailable()
    log_event("kb_import", file_type=kind, bytes=len(data), pages=pages, passages=len(items),
              organize=body.organize, organized=summary.organized, fallback=summary.fallback, titles=titles.count)
    return ImportDetail(document=_with_counts(record, drafts), drafts=[_draft(d) for d in drafts],
                        organize=OrganizeSummary(**_summary(summary, titles)))


def _summary(s: Summary, titles: TitlesSummary) -> dict[str, Any]:
    return {**s.as_dict(), "titles": titles.as_dict()}


def list_imports(store: Any) -> ImportListResponse:
    records = store.kb_imports()
    drafts = store.kb_drafts() if records is not None else None
    if records is None or drafts is None:
        raise unavailable()
    by_import: dict[str, list[dict[str, Any]]] = {}
    for d in drafts:
        by_import.setdefault(str(d["import_id"]), []).append(d)
    return ImportListResponse(imports=[_with_counts(r, by_import.get(str(r["id"]), [])) for r in records])


def _load(store: Any, import_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    record = store.kb_import_get(import_id)
    if record is None:
        raise unavailable()
    if not record:
        raise ApiError("not_found", 404, "unknown import")
    drafts = store.kb_drafts(import_id=str(record["id"]))
    if drafts is None:
        raise unavailable()
    return record, drafts


def get_import(store: Any, import_id: str) -> ImportDetail:
    record, drafts = _load(store, import_id)
    return ImportDetail(document=_with_counts(record, drafts), drafts=[_draft(d) for d in drafts], organize=None)


def _sync_status(store: Any, record: dict[str, Any], drafts: list[dict[str, Any]]) -> None:
    status = "open" if any(d["status"] == "draft" for d in drafts) else "done"
    if record.get("status") != status:
        store.kb_import_update(str(record["id"]), {"status": status})
        record["status"] = status


def patch_draft(store: Any, draft_id: str, patch: DraftPatch) -> KbDraft:
    found = store.kb_drafts(ids=[draft_id])
    if found is None:
        raise unavailable()
    if not found:
        raise ApiError("not_found", 404, "unknown draft")
    draft = dict(found[0])
    if draft["status"] == "approved":
        raise ApiError("kb_conflict", 409, f"draft already approved as {draft['row_id']}; edit the row instead")
    changes = {k: v for k, v in patch.model_dump().items() if v is not None}
    draft.update(changes, updated_at=now_iso())
    if not store.kb_drafts_save([draft]):
        raise unavailable()
    record, drafts = _load(store, str(draft["import_id"]))
    _sync_status(store, record, drafts)
    log_event("kb_draft_updated", fields=sorted(changes))
    return _draft(draft)


def approve(store: Any, kb: KnowledgeBase, import_id: str, draft_ids: list[str]) -> tuple[list[Row], list[KbDraft]]:
    """Add the chosen pending drafts as K-rows (in draft order). Call under the KB lock."""
    record, drafts = _load(store, import_id)
    by_id = {str(d["id"]): d for d in drafts}
    wanted = list(dict.fromkeys(draft_ids))
    unknown = [i for i in wanted if i not in by_id]
    if unknown:
        raise ApiError("not_found", 404, "a draft does not belong to this import")
    chosen = sorted((by_id[i] for i in wanted), key=lambda d: (int(d["ord"]), str(d["created_at"]), str(d["id"])))
    not_pending = [d for d in chosen if d["status"] != "draft"]
    if not_pending:
        raise ApiError("kb_conflict", 409, f"{len(not_pending)} draft(s) are not pending (approved or discarded)")
    try:
        new_rows = [KbNewRow(topic=d["topic"], answer_ar=d["text_ar"], keyword_en=d.get("keyword_en") or "",
                             source_document=record["document_name"], source_page=int(d["page"])) for d in chosen]
    except ValidationError as exc:
        first = exc.errors()[0]
        raise ApiError("validation_error", 400, f"a draft is not a valid knowledge row: {first.get('msg')}",
                       ".".join(str(x) for x in first.get("loc", ())) or None) from None
    rows = kb.add_many(new_rows)
    at = now_iso()
    for d, row in zip(chosen, rows, strict=True):
        d.update(status="approved", row_id=row.id, updated_at=at)
    if not store.kb_drafts_save(chosen):
        log_event("kb_import_store_failed", op="approve", drafts=len(chosen))
    _sync_status(store, record, drafts)
    log_event("kb_import_approved", drafts=len(chosen), first=rows[0].id if rows else None)
    return rows, [_draft(d) for d in chosen]


def after_kb_reset(store: Any) -> int:
    """KB reset removed every added row: approved drafts go back to pending with no row. Never raises."""
    try:
        approved = store.kb_drafts(status="approved")
        if not approved:
            return 0
        at = now_iso()
        for d in approved:
            d.update(status="draft", row_id=None, updated_at=at)
        store.kb_drafts_save(approved)
        for iid in {str(d["import_id"]) for d in approved}:
            store.kb_import_update(iid, {"status": "open"})
        log_event("kb_import_reset", drafts=len(approved))
        return len(approved)
    except Exception as exc:  # noqa: BLE001 - a reset must succeed even when the import tables are missing
        log_event("kb_import_store_failed", op="reset", error=type(exc).__name__)
        return 0


__all__ = ["after_kb_reset", "approve", "capabilities", "create_import", "get_import", "list_imports", "patch_draft"]
