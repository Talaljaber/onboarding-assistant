"""Hybrid retrieval, list detection, BM25/RRF, reindex, OOS auto-disable, bands (plan Part C §4.2–§4.4, §9)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from app.config import get_settings
from app.encoder import get_encoder
from app.kb import KnowledgeBase
from app.retrieve import BM25, Bands, OOSExample, Retriever, is_list_question, load_out_of_scope, read_bands, rrf
from app.textnorm import tokens

S = get_settings()
FAQ = [
    ("F01", "متى تأسست المجموعة؟", {"K01"}),
    ("F02", "كم عدد المعارض وأين توجد؟", {"K02"}),
    ("F03", "ما رؤية المجموعة؟", {"K03"}),
    ("F04", "ما قيم الشركة؟", {"K05", "K06", "K07", "K08", "K09"}),
    ("F05", "من المسؤول عن إجراءات تهيئة الموظف؟", {"K10"}),
    ("F06", "ماذا يحدث في اليوم الأول؟", {"K12"}),
    ("F07", "متى تصل رسالة الترحيب؟", {"K13"}),
    ("F08", "ما مدة فترة التجربة؟", {"K14"}),
    ("F09", "كيف أقدم طلب إجازة؟", {"K16"}),
    ("F10", "هل يمكنني مشاركة ملفات الشركة مع شخص خارجي؟", {"K17"}),
    ("F11", "ما العلامات التجارية للشركة؟", {"K18"}),
]


@pytest.fixture(scope="module")
def retriever(tmp_path_factory: pytest.TempPathFactory) -> Retriever:
    kb = KnowledgeBase(official_path=S.data_official / "knowledge_base.csv", live_dir=tmp_path_factory.mktemp("live"))
    return Retriever(get_encoder(), kb, load_out_of_scope(S.data_ours / "out_of_scope.csv"), bands=Bands())


def test_faq_top1(retriever: Retriever) -> None:
    ok = sum(retriever.search(q)[0].id in gold for _, q, gold in FAQ)
    assert ok >= 10, ok


def test_search_returns_all_rows_ranked(retriever: Retriever) -> None:
    hits = retriever.search("ما مدة فترة التجربة؟")
    assert len(hits) == 18 and [h.rank for h in hits] == list(range(1, 19))
    assert all(hits[i].rrf >= hits[i + 1].rrf for i in range(17))


@pytest.mark.parametrize(
    "q",
    ["ما قيم الشركة؟", "اذكر القيم المشتركة لمجموعة الدادا", "ما هي القيم الخمسة؟", "What are the company's values?",
     "شو القيم المشتركة اللي بتأمن فيها المجموعة؟", "عدد لي قيم المجموعة"],
)
def test_list_detection(q: str) -> None:
    assert is_list_question(q)


@pytest.mark.parametrize(
    "q",
    ["ما رؤية المجموعة", "هل النزاهة من قيم الشركة؟", "هل المثابرة إحدى قيم الشركة؟",
     "ما هي القيمة المتعلقة بخدمة المجتمع؟", "متى تأسست المجموعة؟"],
)
def test_not_list(q: str) -> None:
    assert not is_list_question(q)


def test_company_word_does_not_win_f04(retriever: Retriever) -> None:
    top = retriever.search("ما قيم الشركة؟")[0].id
    assert top not in {"K15", "K17"}
    assert "شرك" not in tokens("الشركة") and tokens("الشركة") == []


def test_rrf_ignores_zero_bm25() -> None:
    dense = np.array([0.9, 0.8, 0.7])
    bm = np.array([0.0, 0.0, 2.0])
    out = rrf(dense, bm)
    assert out[0] == pytest.approx(1 / 60)
    assert out[1] == pytest.approx(1 / 61)
    assert out[2] == pytest.approx(1 / 62 + 1 / 60)


def test_bm25_basic() -> None:
    bm = BM25([["اجاز", "طلب"], ["حضور"], ["اجاز"]])
    s = bm.scores(["طلب"])
    assert s[0] > 0 and s[1] == 0 and s[2] == 0


def test_margin_fields(retriever: Retriever) -> None:
    m = retriever.margin("ما مدة فترة التجربة؟")
    assert m.best_row_id == "K14" and m.best_oos_id is not None
    assert m.margin == pytest.approx(m.best_row_cos - (m.best_oos_cos or 0.0))


def test_reindex_after_add_and_oos_twin(tmp_path: Path) -> None:
    kb = KnowledgeBase(official_path=S.data_official / "knowledge_base.csv", live_dir=tmp_path)
    twin = "هل في تأمين صحي للموظفين الجدد؟"
    oos = [OOSExample("OOS90", twin), OOSExample("OOS91", "كيف الطقس اليوم؟")]
    r = Retriever(get_encoder(), kb, oos, bands=Bands())
    row = kb.add({"topic": "Policy", "answer_ar": twin, "keyword_en": "Health insurance",
                  "source_document": "General Policies", "source_page": 3})
    assert row.id == "K19"
    assert r.search("هل يوجد تأمين صحي للموظفين؟")[0].id == "K19"
    assert "OOS90" in r.last_disabled and r.enabled_oos() == ["OOS91"]
    kb.reset()
    assert r.enabled_oos() == ["OOS90", "OOS91"] and len(r.search("x")) == 18


def test_bands(tmp_path: Path) -> None:
    b = Bands()
    assert (b.band(0.0), b.band(0.01), b.band(0.03), b.band(0.051)) == ("refuse", "refuse", "not_confirmed", "answer")
    p = tmp_path / "bands.json"
    p.write_text(json.dumps({"bands": {"refuse": -0.02, "not_confirmed": 0.02}}), encoding="utf-8")
    assert read_bands(p) == Bands(-0.02, 0.02, str(p))
    p.write_text(json.dumps({"refuse_max": 0.0, "not_confirmed_max": 0.03}), encoding="utf-8")
    assert read_bands(p).not_confirmed == 0.03
    p.write_text("{oops", encoding="utf-8")
    assert read_bands(p) == Bands()
    assert read_bands(tmp_path / "missing.json") == Bands()
