"""Knowledge base: the 18 official K-rows plus live edits (plan Part C §1, §3.4 and §A12.3).

What it does: loads and validates `data/official/knowledge_base.csv` (UTF-8 with BOM), overlays the live
rows (from the `Store` when one is given, else from `data/live/kb_snapshot.json`), and supports
`put` / `add` / `reset`. Every load and edit rewrites the snapshot file, bumps `version()` and notifies
subscribers (the retriever re-indexes). Reads and writes go through the Store protocol when a store is
given (`kb_rows`, `kb_upsert`, `kb_replace_all`, `kb_history`); with `store=None` it is purely in memory
plus the snapshot file.

What it must never do: open the official CSV for writing, invent row text, or raise a store failure to
the caller (a failing store is logged and the in-memory rows stay authoritative for this process).
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from app.errors import ApiError, StartupError
from app.logging_setup import log_event
from app.schemas import KbNewRow, KbPatch

OFFICIAL_FILE = "knowledge_base.csv"
SNAPSHOT_FILE = "kb_snapshot.json"
_COLUMNS = ("id", "topic", "answer_ar", "keyword_en", "source_document", "source_page")
_ID_RE = re.compile(r"^K(\d{2,3})$")
#: What subscribers are told changed: one row id (edit/add), several (a batch add, P12.1) or None (reset).
ChangedIds = str | tuple[str, ...] | None


@dataclass(frozen=True)
class Row:
    """One K-row. `status` is official | edited | added; `edited` is true exactly when not official."""

    id: str
    topic: str
    answer_ar: str
    keyword_en: str
    source_document: str
    source_page: int
    status: str = "official"
    offline_edit: bool = False

    @property
    def edited(self) -> bool:
        return self.status != "official"

    def embed_text(self) -> str:
        """Text embedded for dense retrieval: `"{topic} {keyword_en}: {answer_ar}"` (plan §4.2)."""
        return f"{self.topic} {self.keyword_en}: {self.answer_ar}"

    def as_source(self) -> dict[str, Any]:
        """The contract `Source` shape (answer_ar verbatim)."""
        return {
            "id": self.id,
            "topic": self.topic,
            "answer_ar": self.answer_ar,
            "source_document": self.source_document,
            "source_page": self.source_page,
            "edited": self.edited,
            "status": self.status,
        }

    def as_kb_row(self) -> dict[str, Any]:
        """The contract `KbRow` shape."""
        return {**self.as_source(), "keyword_en": self.keyword_en, "offline_edit": self.offline_edit}

    def as_store_dict(self) -> dict[str, Any]:
        return asdict(self)


class KbStore(Protocol):
    """The part of `app.store.Store` the knowledge base uses."""

    def kb_rows(self) -> list[dict[str, Any]] | None: ...

    def kb_upsert(self, row: dict[str, Any], source: str) -> object: ...

    def kb_replace_all(self, rows: list[dict[str, Any]], source: str) -> object: ...

    def kb_history(self, row_id: str) -> list[dict[str, Any]]: ...


def _row_from_mapping(d: Mapping[str, Any], *, default_status: str = "official") -> Row:
    rid = str(d.get("id", "")).strip()
    if not _ID_RE.match(rid):
        raise ValueError(f"bad K id {rid!r}")
    answer = str(d.get("answer_ar", "")).strip()
    if not answer:
        raise ValueError(f"{rid}: empty answer_ar")
    status = str(d.get("status") or default_status)
    if status not in ("official", "edited", "added"):
        status = default_status
    return Row(
        id=rid,
        topic=str(d.get("topic", "")).strip(),
        answer_ar=answer,
        keyword_en=str(d.get("keyword_en") or "").strip(),
        source_document=str(d.get("source_document", "")).strip(),
        source_page=int(d.get("source_page") or 0),
        status=status,
        offline_edit=bool(d.get("offline_edit", False)),
    )


def load_official(path: Path) -> list[Row]:
    """Read and validate the official KB CSV (UTF-8 with BOM). Raises StartupError with the fix."""
    try:
        with Path(path).open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if tuple(reader.fieldnames or ()) != _COLUMNS:
                raise StartupError(f"{path}: unexpected columns {reader.fieldnames}; restore data/official.")
            rows = [_row_from_mapping(r) for r in reader]
    except (OSError, UnicodeDecodeError, csv.Error, ValueError) as exc:
        raise StartupError(f"{path} cannot be read ({exc}); restore data/official from the release zip.") from None
    ids = [r.id for r in rows]
    if len(set(ids)) != len(ids) or not rows:
        raise StartupError(f"{path}: duplicate or missing ids; restore data/official from the release zip.")
    return rows


def _id_num(rid: str) -> int:
    m = _ID_RE.match(rid)
    return int(m.group(1)) if m else 0


class KnowledgeBase:
    """Live K-rows over the official CSV, edited through `put` / `add` / `reset`."""

    def __init__(
        self,
        store: KbStore | None = None,
        *,
        official_path: Path | None = None,
        live_dir: Path | None = None,
    ) -> None:
        if official_path is None or live_dir is None:
            from app.config import get_settings

            s = get_settings()
            official_path = official_path or s.data_official / OFFICIAL_FILE
            live_dir = live_dir or s.data_live
        self.official_path = Path(official_path)
        self.live_dir = Path(live_dir)
        self.snapshot_path = self.live_dir / SNAPSHOT_FILE
        self.store = store
        self.lock = threading.RLock()
        self._subscribers: list[Callable[[ChangedIds], None]] = []
        self._official = load_official(self.official_path)
        self.official_sha256 = hashlib.sha256(self.official_path.read_bytes()).hexdigest()
        self._rows: dict[str, Row] = {}
        self.loaded_from = "official"
        self._load()

    # ------------------------------------------------------------------ loading
    def _load(self) -> None:
        rows: list[Row] | None = None
        if self.store is not None:
            try:
                stored = self.store.kb_rows()
                if stored is None:  # unreadable store: fall back to the snapshot / official rows
                    log_event("kb_store_failed", op="load", error="unreadable")
                elif not stored:  # empty store: seed it idempotently from the official CSV
                    self.store.kb_replace_all([r.as_store_dict() for r in self._official], "seed")
                    rows, self.loaded_from = list(self._official), "official"
                else:
                    rows, self.loaded_from = [_row_from_mapping(d) for d in stored], "store"
            except Exception as exc:  # noqa: BLE001 - a store failure must never stop the KB
                log_event("kb_store_failed", op="load", error=type(exc).__name__)
                rows = None
        if not rows:
            rows = self._read_snapshot()
            self.loaded_from = "snapshot" if rows else "official"
        if not rows:
            rows = list(self._official)
        self._rows = {r.id: r for r in sorted(rows, key=lambda r: _id_num(r.id))}
        self._write_snapshot()

    def _read_snapshot(self) -> list[Row] | None:
        try:
            data = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
            rows = [_row_from_mapping(d) for d in data["rows"]]
            return rows or None
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            log_event("kb_snapshot_unreadable", error=type(exc).__name__)
            return None

    def _write_snapshot(self) -> None:
        payload = {"version": self.version(), "rows": [r.as_store_dict() for r in self._rows.values()]}
        try:
            self.live_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.snapshot_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.snapshot_path)
        except OSError as exc:
            log_event("kb_snapshot_write_failed", error=type(exc).__name__)

    def _store_call(self, op: str, fn: Callable[[], object]) -> None:
        if self.store is None:
            return
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - never raise a store failure to the API
            log_event("kb_store_failed", op=op, error=type(exc).__name__)

    def _changed(self, row_id: ChangedIds) -> None:
        self._write_snapshot()
        for cb in list(self._subscribers):
            cb(row_id)

    # ------------------------------------------------------------------ reads
    def subscribe(self, callback: Callable[[ChangedIds], None]) -> None:
        """Call `callback(changed)` after every edit or add (the row id), batch add (a tuple of ids, one
        call for the whole batch) and reset (None)."""
        self._subscribers.append(callback)

    def rows(self) -> list[Row]:
        return list(self._rows.values())

    def get(self, row_id: str) -> Row | None:
        return self._rows.get(row_id)

    def ids(self) -> list[str]:
        return list(self._rows)

    def topics(self) -> dict[str, list[Row]]:
        out: dict[str, list[Row]] = {}
        for r in self._rows.values():
            out.setdefault(r.topic, []).append(r)
        return out

    def edited_ids(self) -> list[str]:
        return [r.id for r in self._rows.values() if r.edited]

    def version(self) -> str:
        """Short sha256 over every row's fields (changes on any edit; used in cache keys and health)."""
        h = hashlib.sha256()
        for r in self._rows.values():
            h.update(json.dumps(r.as_store_dict(), ensure_ascii=False, sort_keys=True).encode("utf-8"))
        return h.hexdigest()[:12]

    def history(self, row_id: str) -> list[dict[str, Any]]:
        if self.store is None:
            return []
        try:
            return self.store.kb_history(row_id)
        except Exception as exc:  # noqa: BLE001
            log_event("kb_store_failed", op="history", error=type(exc).__name__)
            return []

    # ------------------------------------------------------------------ edits
    def put(self, row_id: str, patch: KbPatch | Mapping[str, Any]) -> Row:
        """Apply a partial edit (null fields unchanged). Raises ApiError 404 for an unknown id."""
        p = patch if isinstance(patch, KbPatch) else KbPatch.model_validate(dict(patch))
        with self.lock:
            old = self._rows.get(row_id)
            if old is None:
                raise ApiError("not_found", 404, f"unknown KB id {row_id}")
            changes = {k: v for k, v in p.model_dump().items() if v is not None}
            status = "added" if old.status == "added" else "edited"
            new = replace(old, **changes, status=status)
            self._rows[row_id] = new
            self._store_call("upsert", lambda: self.store.kb_upsert(new.as_store_dict(), "editor"))  # type: ignore[union-attr]
            self._changed(row_id)
            return new

    def add(self, new_row: KbNewRow | Mapping[str, Any]) -> Row:
        """Add a row with the next free `K%02d` id (status `added`)."""
        n = new_row if isinstance(new_row, KbNewRow) else KbNewRow.model_validate(dict(new_row))
        with self.lock:
            next_num = max((_id_num(i) for i in self._rows), default=0) + 1
            rid = f"K{next_num:02d}"
            if rid in self._rows:  # pragma: no cover - max+1 is always free
                raise ApiError("kb_conflict", 409, f"duplicate KB id {rid}")
            row = Row(id=rid, status="added", **n.model_dump())
            self._rows[rid] = row
            self._store_call("upsert", lambda: self.store.kb_upsert(row.as_store_dict(), "editor"))  # type: ignore[union-attr]
            self._changed(rid)
            return row

    def add_many(self, new_rows: Sequence[KbNewRow | Mapping[str, Any]]) -> list[Row]:
        """Add rows with consecutive next free ids, in the given order, then notify once (one reindex).
        All rows are validated before any is added (P12.1: approving imported passages)."""
        parsed = [n if isinstance(n, KbNewRow) else KbNewRow.model_validate(dict(n)) for n in new_rows]
        if not parsed:
            return []
        with self.lock:
            next_num = max((_id_num(i) for i in self._rows), default=0) + 1
            added: list[Row] = []
            for offset, n in enumerate(parsed):
                rid = f"K{next_num + offset:02d}"
                row = Row(id=rid, status="added", **n.model_dump())
                self._rows[rid] = row
                added.append(row)
                self._store_call("upsert", lambda r=row: self.store.kb_upsert(r.as_store_dict(), "editor"))  # type: ignore[misc,union-attr]
            self._changed(tuple(r.id for r in added))
            return added

    def reset(self) -> None:
        """Restore the official rows (the official CSV is only ever read)."""
        with self.lock:
            self._rows = {r.id: r for r in self._official}
            self._store_call(
                "replace_all",
                lambda: self.store.kb_replace_all([r.as_store_dict() for r in self._official], "reset"),  # type: ignore[union-attr]
            )
            self._changed(None)


__all__ = ["ChangedIds", "KbStore", "KnowledgeBase", "Row", "load_official"]
