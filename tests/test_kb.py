"""Knowledge base: load, put/add/reset round trip, snapshot, store protocol (plan Part C §9, §A12.3)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from app.config import OFFICIAL_SHA256, get_settings
from app.errors import ApiError, StartupError
from app.kb import KnowledgeBase, load_official

OFFICIAL = get_settings().data_official / "knowledge_base.csv"


def _official_sha() -> str:
    return hashlib.sha256(OFFICIAL.read_bytes()).hexdigest()


@pytest.fixture
def kb(tmp_path: Path) -> KnowledgeBase:
    return KnowledgeBase(official_path=OFFICIAL, live_dir=tmp_path)


def test_load_official_bom() -> None:
    rows = load_official(OFFICIAL)
    assert len(rows) == 18
    assert rows[0].id == "K01" and rows[0].topic == "Company"  # BOM not in the first header
    assert rows[-1].id == "K18"
    assert all(not r.edited and r.status == "official" for r in rows)


def test_bad_csv(tmp_path: Path) -> None:
    p = tmp_path / "kb.csv"
    p.write_text("id,foo\nK01,x\n", encoding="utf-8")
    with pytest.raises(StartupError):
        load_official(p)


def test_put_add_reset_round_trip(kb: KnowledgeBase, tmp_path: Path) -> None:
    v0 = kb.version()
    assert len(kb.rows()) == 18 and kb.edited_ids() == []
    row = kb.put("K16", {"answer_ar": "يُقدَّم طلب الإجازة عبر النظام قبل أسبوع."})
    assert row.status == "edited" and row.edited
    assert kb.get("K16") == row and kb.version() != v0
    assert _official_sha() == OFFICIAL_SHA256["knowledge_base.csv"]

    added = kb.add({"topic": "Values", "answer_ar": "الإبداع من القيم المشتركة للمجموعة.", "keyword_en": "Creativity",
                    "source_document": "Company Profile 2026", "source_page": 6})
    assert added.id == "K19" and added.status == "added"
    edited_added = kb.put("K19", {"source_page": 7})
    assert edited_added.status == "added" and edited_added.source_page == 7
    assert set(kb.edited_ids()) == {"K16", "K19"}
    assert _official_sha() == OFFICIAL_SHA256["knowledge_base.csv"]

    snap = json.loads((tmp_path / "kb_snapshot.json").read_text(encoding="utf-8"))
    assert len(snap["rows"]) == 19 and snap["version"] == kb.version()

    # a new KB over the same live dir starts from the snapshot
    again = KnowledgeBase(official_path=OFFICIAL, live_dir=tmp_path)
    assert again.loaded_from == "snapshot" and again.get("K19") is not None

    kb.reset()
    assert len(kb.rows()) == 18 and kb.edited_ids() == [] and kb.version() == v0
    assert _official_sha() == OFFICIAL_SHA256["knowledge_base.csv"]


def test_put_unknown_and_invalid(kb: KnowledgeBase) -> None:
    with pytest.raises(ApiError) as e:
        kb.put("K99", {"topic": "Policy"})
    assert e.value.status == 404
    with pytest.raises(ValueError):
        kb.put("K01", {})


def test_subscribers_called(kb: KnowledgeBase) -> None:
    seen: list[str | None] = []
    kb.subscribe(seen.append)
    kb.put("K01", {"keyword_en": "Founded"})
    kb.reset()
    assert seen == ["K01", None]


def test_source_shape(kb: KnowledgeBase) -> None:
    src = kb.get("K14").as_source()  # type: ignore[union-attr]
    assert set(src) == {"id", "topic", "answer_ar", "source_document", "source_page", "edited", "status"}


class FakeStore:
    def __init__(self, rows: list[dict[str, Any]] | None = None, fail: bool = False) -> None:
        self.rows = rows
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def kb_rows(self) -> list[dict[str, Any]] | None:
        if self.fail:
            raise ConnectionError("down")
        return self.rows

    def kb_upsert(self, row: dict[str, Any], source: str) -> None:
        if self.fail:
            raise ConnectionError("down")
        self.calls.append(("upsert:" + row["id"], source))

    def kb_replace_all(self, rows: list[dict[str, Any]], source: str) -> None:
        self.calls.append((f"replace:{len(rows)}", source))

    def kb_history(self, row_id: str) -> list[dict[str, Any]]:
        return [{"row_id": row_id}]


def test_store_seed_and_edits(tmp_path: Path) -> None:
    store = FakeStore(rows=[])
    kb = KnowledgeBase(store, official_path=OFFICIAL, live_dir=tmp_path)
    assert store.calls == [("replace:18", "seed")]
    kb.put("K02", {"source_page": 5})
    kb.reset()
    assert store.calls[1:] == [("upsert:K02", "editor"), ("replace:18", "reset")]
    assert kb.history("K02") == [{"row_id": "K02"}]


def test_store_rows_are_authoritative(tmp_path: Path) -> None:
    rows = [r.as_store_dict() for r in load_official(OFFICIAL)]
    rows[0] = {**rows[0], "answer_ar": "تأسست مجموعة الدادا عام 1991 في عمّان.", "status": "edited"}
    kb = KnowledgeBase(FakeStore(rows=rows), official_path=OFFICIAL, live_dir=tmp_path)
    assert kb.loaded_from == "store" and kb.get("K01").edited  # type: ignore[union-attr]


def test_store_failure_never_raises(tmp_path: Path) -> None:
    kb = KnowledgeBase(FakeStore(fail=True), official_path=OFFICIAL, live_dir=tmp_path)
    assert len(kb.rows()) == 18
    assert kb.put("K03", {"topic": "Company"}).status == "edited"


def test_unreadable_store_falls_back(tmp_path: Path) -> None:
    store = FakeStore(rows=None)
    kb = KnowledgeBase(store, official_path=OFFICIAL, live_dir=tmp_path)
    assert len(kb.rows()) == 18 and store.calls == []


def test_real_local_store_round_trip(tmp_path: Path) -> None:
    from app.store.local import LocalStore

    store = LocalStore(tmp_path)
    kb = KnowledgeBase(store, official_path=OFFICIAL, live_dir=tmp_path)
    kb.put("K16", {"source_page": 3})
    again = KnowledgeBase(LocalStore(tmp_path), official_path=OFFICIAL, live_dir=tmp_path / "other")
    assert again.loaded_from == "store" and again.get("K16").source_page == 3  # type: ignore[union-attr]
    assert again.get("K16").status == "edited"  # type: ignore[union-attr]
    assert [h["source"] for h in store.kb_history("K16")][-1] == "editor"
