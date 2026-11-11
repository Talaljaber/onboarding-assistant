"""P12.1 document import: extraction per type, the chunker, the organize verifier and cache rule, the API
(admin only, body limit, approve -> K-rows -> cited verbatim, reset, drafts, 423, 503) and both stores.

Every model reply here is a scripted string from a fake client (plan §A6.11), never a real result.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import threading
import uuid
import zipfile
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from app import verify as v
from app.agent import Agent, build_agent
from app.config import get_settings
from app.errors import LLMUnavailable
from app.kb_import import extract as ex
from app.kb_import.chunk import MAX_CHARS, chunk, is_boilerplate, sentences, split_long
from app.kb_import.extract import Block, ImportRejected, extract
from app.kb_import.organize import GENERAL_TOPIC, latin_keywords, organize
from app.llm import LLM
from app.llm.budget import Budget
from app.llm.cached_chat import CachedChat
from app.llm.openrouter import ChatResult
from app.llm.paths import ORGANIZE_BATCH, llm_organize, render_organize_prompt
from app.main import create_app
from app.schemas import (
    ApproveResponse,
    ErrorBody,
    ImportCapabilities,
    ImportDetail,
    ImportListResponse,
    KbDraft,
    KbListResponse,
)
from app.store import LocalStore, SupabaseStore

MODEL = "deepseek/deepseek-v4.1-flash"
DRESS = ("يلتزم الموظف بارتداء الزي الرسمي للشركة طوال ساعات الدوام في المعارض، ويُسمح باللباس غير الرسمي يوم "
         "الخميس فقط. يجب ارتداء بطاقة التعريف دائماً.")
PARKING = "تتوفر مواقف مجانية للموظفين خلف المبنى الرئيسي، ويُمنع الوقوف أمام مدخل المعرض."
DOC_TXT = f"سياسة اللباس\n\n{DRESS}\n\nمواقف السيارات\n\n{PARKING}\n"


def b64(data: bytes | str) -> str:
    return base64.b64encode(data.encode("utf-8") if isinstance(data, str) else data).decode()


# ============================================================================ builders
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def make_docx(paragraphs: list[tuple[str | None, str, str]], styles: str | None = None) -> bytes:
    """(style or None, text, break) where break is "" | "page" (w:br page before the text) | "rendered".
    `styles` is an optional `word/styles.xml` body (the `w:style` elements)."""
    body = []
    for style, text, brk in paragraphs:
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        pre = '<w:br w:type="page"/>' if brk == "page" else "<w:lastRenderedPageBreak/>" if brk == "rendered" else ""
        body.append(f"<w:p>{ppr}<w:r>{pre}<w:t xml:space=\"preserve\">{text}</w:t></w:r></w:p>")
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{_W}"><w:body>{"".join(body)}</w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", xml)
        if styles is not None:
            zf.writestr("word/styles.xml", f'<?xml version="1.0" encoding="UTF-8"?><w:styles xmlns:w="{_W}">{styles}</w:styles>')
    return buf.getvalue()


def make_pdf(pages: list[list[str]]) -> bytes:
    """A minimal valid PDF (Helvetica text, one content stream per page)."""
    page_ids = [4 + 2 * i for i in range(len(pages))]
    kids = " ".join(f"{p} 0 R" for p in page_ids)
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i, lines in enumerate(pages):
        content = b"BT /F1 12 Tf 72 720 Td 14 TL " + b" ".join(b"(" + x.encode("latin-1") + b") '" for x in lines) + b" ET"
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
                    f"/Contents {page_ids[i] + 1} 0 R >>".encode())
        objs.append(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


# ============================================================================ extraction
def test_txt_paragraphs_headings_and_form_feed_pages() -> None:
    kind, blocks, pages = extract("a.txt", ("﻿" + DOC_TXT + "\f" + "الصفحة الثانية فيها نص كافٍ للاختبار.\n").encode())
    assert kind == "txt" and pages == 2
    assert [(b.kind, b.page) for b in blocks] == [("heading", 1), ("para", 1), ("heading", 1), ("para", 1), ("para", 2)]
    assert blocks[1].text == DRESS  # BOM gone, text verbatim


def test_md_headings_bullets_links() -> None:
    md = "# Leave policy\n\n- Annual leave is **14 days** per year.\n- See [the HR portal](https://hr.example) to apply.\n"
    _, blocks, _ = extract("p.md", md.encode())
    assert blocks[0] == Block("Leave policy", 1, "heading")
    assert blocks[1].text == "Annual leave is 14 days per year.\nSee the HR portal to apply."


def test_csv_with_known_header_and_without() -> None:
    data = "topic,answer_ar,keyword_en,source_page\nPolicy,يبدأ الدوام الساعة التاسعة صباحاً.,working hours,4\n,,,\n"
    _, blocks, pages = extract("rows.csv", ("﻿" + data).encode())
    assert blocks == [Block("يبدأ الدوام الساعة التاسعة صباحاً.", 4, "row", "Policy", "working hours")] and pages == 4
    _, plain, _ = extract("plain.csv", "القسم,المعلومة\nالمبيعات,يجتمع الفريق كل أحد\n".encode())
    assert [b.text for b in plain] == ["القسم - المعلومة", "المبيعات - يجتمع الفريق كل أحد"]


def test_docx_headings_and_page_breaks() -> None:
    doc = make_docx([("Heading1", "Leave", ""), (None, "Annual leave is 14 days.", ""),
                     (None, "Second page text here.", "page"), (None, "Third page text here.", "rendered")])
    kind, blocks, pages = extract("h.docx", doc)
    assert kind == "docx" and pages == 3
    assert [(b.kind, b.text, b.page) for b in blocks] == [
        ("heading", "Leave", 1), ("para", "Annual leave is 14 days.", 1),
        ("para", "Second page text here.", 2), ("para", "Third page text here.", 3)]


def test_docx_headings_saved_by_word_in_another_language() -> None:
    """Arabic Word stores "heading 1" under the style id "1": the style's name, not its id, makes the heading."""
    styles = ('<w:style w:type="paragraph" w:styleId="1"><w:name w:val="heading 1"/></w:style>'
              '<w:style w:type="paragraph" w:styleId="a"><w:name w:val="Normal"/></w:style>'
              '<w:style w:type="paragraph" w:styleId="x7"><w:name w:val="Custom"/><w:pPr><w:outlineLvl w:val="1"/></w:pPr></w:style>')
    doc = make_docx([("1", "الحاسوب", ""), ("a", "يستلم الموظف جهازاً في يومه الأول.", ""),
                     ("x7", "التذاكر", ""), (None, "تُرفع المشكلات عبر نظام التذاكر.", "")], styles)
    _, blocks, _ = extract("ar.docx", doc)
    assert [b.kind for b in blocks] == ["heading", "para", "heading", "para"]
    assert [p.heading for p in chunk(blocks)] == ["الحاسوب", "التذاكر"]


def test_docx_explicit_break_then_rendered_break_counts_once() -> None:
    xml = (f'<w:document xmlns:w="{_W}"><w:body><w:p><w:r><w:t>One</w:t><w:br w:type="page"/></w:r></w:p>'
           "<w:p><w:r><w:lastRenderedPageBreak/><w:t>Two</w:t></w:r></w:p></w:body></w:document>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", xml)
    _, blocks, pages = extract("b.docx", buf.getvalue())
    assert [(b.text, b.page) for b in blocks] == [("One", 1), ("Two", 2)] and pages == 2


def test_docx_bomb_and_doctype_and_garbage_are_rejected() -> None:
    big = io.BytesIO()
    with zipfile.ZipFile(big, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", "<a>" + " " * (ex.DOCX_MAX_UNCOMPRESSED + 10) + "</a>")
    with pytest.raises(ImportRejected) as e:
        extract("bomb.docx", big.getvalue())
    assert e.value.reason == "too_large_unpacked"
    evil = io.BytesIO()
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("word/document.xml", '<!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>')
    with pytest.raises(ImportRejected):
        extract("evil.docx", evil.getvalue())
    with pytest.raises(ImportRejected) as e:
        extract("junk.docx", b"not a zip")
    assert e.value.field == "content_b64"


def test_types_empty_and_encoding_rejected() -> None:
    for name, data, field, reason in (
        ("a.exe", b"MZ", "filename", "unsupported_type"),
        ("a.txt", b"", "content_b64", "empty"),
        ("a.txt", "نص".encode("cp1256"), "content_b64", "not_utf8"),
        ("a.txt", b"abc\x00def", "content_b64", "binary"),
    ):
        with pytest.raises(ImportRejected) as e:
            extract(name, data)
        assert (e.value.field, e.value.reason) == (field, reason)


def test_pdf_pages_when_pypdf_is_installed() -> None:
    pytest.importorskip("pypdf")
    pdf = make_pdf([["Welcome to the company handbook.", "Employees get 14 days of annual leave each year."],
                    ["Parking is behind the main building."]])
    kind, blocks, pages = extract("h.pdf", pdf)
    assert kind == "pdf" and pages == 2
    assert [b.page for b in blocks] == [1, 2] and "14 days" in blocks[0].text


def test_pdf_short_unpunctuated_lines_become_headings() -> None:
    """A PDF has no heading styles: a short line with no closing punctuation, followed by text, splits the page."""
    pytest.importorskip("pypdf")
    pdf = make_pdf([["Daily tools guide", "This is a sample.", "Laptop and account",
                     "You get a laptop on your first day.", "Ticket system", "Report every issue in the ticket system.",
                     "Page 1"]])
    _, blocks, _ = extract("t.pdf", pdf)
    assert [(b.kind, b.text) for b in blocks] == [
        ("heading", "Daily tools guide"), ("para", "This is a sample."), ("heading", "Laptop and account"),
        ("para", "You get a laptop on your first day."), ("heading", "Ticket system"),
        ("para", "Report every issue in the ticket system.\nPage 1")]


def test_pdf_unavailable_without_pypdf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ex, "pdf_available", lambda: False)
    assert "pdf" not in ex.supported_types()
    with pytest.raises(ImportRejected) as e:
        extract("h.pdf", b"%PDF-1.4")
    assert (e.value.field, e.value.reason) == ("filename", "pdf_unavailable")


# ============================================================================ chunker
def test_sentence_boundaries_arabic_and_english() -> None:
    text = "الجملة الأولى؟ الجملة الثانية. Third one! Fourth۔ خامسة\nسطر جديد"
    assert [s for s, _ in sentences(text)] == ["الجملة الأولى؟", "الجملة الثانية.", "Third one!", "Fourth۔", "خامسة",
                                               "سطر جديد"]
    assert [sep for _, sep in sentences(text)][-1] == "\n"
    assert [s for s, _ in sentences("النسبة 2.5 بالمئة.")] == ["النسبة 2.5 بالمئة."]  # decimals are not ends


def test_long_paragraph_split_at_sentence_ends_within_max() -> None:
    sent = "هذه جملة عربية متوسطة الطول تشرح سياسة من سياسات الشركة بوضوح. "
    pieces = split_long((sent * 25).strip())
    assert len(pieces) > 1 and all(len(p) <= MAX_CHARS for p in pieces)
    assert all(p.endswith(".") for p in pieces)  # never cut inside a sentence
    giant = "كلمة " * 300  # one sentence longer than the limit: the only allowed mid-sentence cut
    parts = split_long(giant.strip())
    assert all(len(p) <= MAX_CHARS for p in parts) and " ".join(parts) == giant.strip()


def test_boilerplate_pages_toc_and_running_headers() -> None:
    for line in ("3", "- 3 -", "Page 3 of 9", "صفحة ٣", "الصفحة 4 من 10", "Introduction ........ 3", "مقدمة …… ٥",
                 "جميع الحقوق محفوظة لمجموعة الدادا.", "© 2026 Dada Group", "Copyright 2026. All rights reserved."):
        assert is_boilerplate(line), line
    assert not is_boilerplate("يبدأ الدوام الساعة 9 صباحاً.")
    header = "دليل الموظف 2026 — سري"
    blocks = [Block(f"{header}\nنص الصفحة رقم {n} يشرح سياسة مختلفة للموظفين الجدد في الشركة.\n{n}", n) for n in (1, 2, 3)]
    passages = chunk(blocks)
    assert [p.page for p in passages] == [1, 2, 3]
    assert all(header not in p.text and not p.text.endswith(f"\n{p.page}") for p in passages)


def test_short_paragraphs_merge_within_section_and_page_only() -> None:
    blocks = [Block("Leave", 1, "heading"), Block("الإجازة السنوية 14 يوماً.", 1), Block("تُقدَّم عبر النظام.", 1),
              Block("Parking", 1, "heading"), Block("المواقف خلف المبنى الرئيسي.", 1), Block("ويمنع الوقوف أمام المدخل.", 2)]
    passages = chunk(blocks)
    assert [(p.text, p.page, p.heading) for p in passages] == [
        ("الإجازة السنوية 14 يوماً.\nتُقدَّم عبر النظام.", 1, "Leave"),
        ("المواقف خلف المبنى الرئيسي.", 1, "Parking"),
        ("ويمنع الوقوف أمام المدخل.", 2, "Parking"),
    ]


def test_order_rows_and_tiny_fragments() -> None:
    blocks = [Block("أولاً نص طويل بما يكفي ليكون مقطعاً مستقلاً.", 1), Block("ok", 1, "heading"),
              Block("ب", 1), Block("صف", 2, "row"), Block("صف من ملف CSV", 3, "row")]
    passages = chunk(blocks)
    assert [p.text for p in passages] == ["أولاً نص طويل بما يكفي ليكون مقطعاً مستقلاً.", "صف من ملف CSV"]


# ============================================================================ offline labels
def test_offline_labels() -> None:
    blocks = [Block("Policy and rules", 1, "heading"), Block("Annual leave: leave requests go through the HR system.", 1),
              Block("نص بلا عنوان يكفي ليكون مقطعاً", 2)]
    items, summary = organize(chunk(blocks), ["Company", "Policy"], requested=False, llm=None, use_llm=False)
    assert items[0].topic == "Policy" and items[0].keyword_en == "annual leave requests"
    assert not summary.used and summary.fallback == 2
    assert latin_keywords("نص عربي فقط") == ""
    plain, _ = organize(chunk([Block("نص بلا عنوان يكفي ليكون مقطعاً", 1)]), [], requested=True, llm=None, use_llm=False)
    assert plain[0].topic == GENERAL_TOPIC


# ============================================================================ organize verifier
P = [{"id": "p1", "text": "الإجازة السنوية 14 يوماً تقدم عبر النظام.", "page": 1},
     {"id": "p2", "text": "وتحتاج موافقة المدير المباشر.", "page": 1},
     {"id": "p3", "text": "جميع الحقوق محفوظة.", "page": 2}]


def good_reply(**over: Any) -> dict[str, Any]:
    items = [{"id": "p1", "topic": "Policy", "keyword_en": "annual leave", "question_ar": "كم يوماً الإجازة السنوية 14؟",
              "keep": True, "order": 1, "merge_with": "p2"},
             {"id": "p2", "topic": "Policy", "keyword_en": "manager approval", "question_ar": "من يوافق على الإجازة؟",
              "keep": True, "order": 2, "merge_with": "p1"},
             {"id": "p3", "topic": "Company", "keyword_en": "copyright", "question_ar": "ما حقوق النشر؟", "keep": False,
              "order": 3, "merge_with": None}]
    for item in items:
        item.update(over.get(item["id"], {}))
    return {"passages": items}


def test_good_organize_reply_passes() -> None:
    verdict = v.verify_organize(good_reply(), P)
    assert verdict.ok and verdict.rejected == 0
    assert verdict.merges == [("p1", "p2")] and verdict.order == ["p1", "p2", "p3"]
    assert verdict.fields["p3"]["keep"] is False


@pytest.mark.parametrize(
    ("over", "field"),
    [
        ({"p2": {"question_ar": "هل الإجازة 30 يوماً؟"}}, "question_ar"),  # number not in that passage
        ({"p1": {"topic": "Call 0791234567"}}, "topic"),
        ({"p1": {"keyword_en": "see https://x.io"}}, "keyword_en"),
        ({"p1": {"keyword_en": "إجازة"}}, "keyword_en"),  # Arabic in the English keywords
        ({"p1": {"question_ar": "What is the leave?"}}, "question_ar"),  # no Arabic
        ({"p1": {"question_ar": "س" * 161}}, "question_ar"),  # too long
        ({"p1": {"topic": "t" * 41}}, "topic"),
        ({"p1": {"topic": "K14 rules"}}, "topic"),
    ],
)
def test_bad_values_fall_back_one_by_one(over: dict[str, Any], field: str) -> None:
    verdict = v.verify_organize(good_reply(**over), P)
    pid = next(iter(over))
    assert verdict.ok and verdict.rejected == 1 and field not in verdict.fields[pid]


def test_bad_merges_and_orders_are_rejected() -> None:
    far = v.verify_organize(good_reply(p1={"merge_with": "p3"}, p2={"merge_with": None}), P)
    assert far.merges == [] and far.rejected == 1  # not a neighbour
    cross_page = v.verify_organize(good_reply(p1={"merge_with": None}, p2={"merge_with": "p3"}), P)
    assert cross_page.merges == [] and cross_page.rejected == 1
    long_p = [{**P[0], "text": "ا" * 400}, {**P[1], "text": "ب" * 300}, P[2]]
    assert v.verify_organize(good_reply(), long_p).merges == []  # joined text > 600
    dup = v.verify_organize(good_reply(p2={"order": 1}), P)
    assert dup.order is None and dup.rejected == 1


def test_whole_reply_rejected_for_unknown_or_repeated_ids_and_shape() -> None:
    assert v.verify_organize(good_reply(p3={"id": "p9"}), P).reason == v.FOREIGN_ID
    assert v.verify_organize({"passages": [{"id": "p1"}, {"id": "p1"}]}, P).reason == v.FOREIGN_ID
    assert v.verify_organize({"passages": [], "text": "x"}, P).reason == v.BAD_SHAPE
    assert v.verify_organize([], P).reason == v.INVALID_JSON


# ============================================================================ organize path (fake model)
class FakeClient:
    """Scripted replies: strings, exceptions or callables(messages) -> str; then every call times out."""

    def __init__(self, *items: Any) -> None:
        self.items = list(items)
        self.calls: list[dict[str, Any]] = []

    def chat(self, model_id: str, messages: list[dict[str, str]], *, params: Mapping[str, object],
             response_format: Mapping[str, object] | None = None, deadline_s: float | None = None) -> ChatResult:
        self.calls.append({"model": model_id, "messages": messages, "params": dict(params)})
        item = self.items.pop(0) if self.items else LLMUnavailable("OpenRouter request timed out")
        if isinstance(item, Exception):
            raise item
        if callable(item):
            item = item(messages)
        return ChatResult(item, 100, 20, 0.0001, 40)


class DictCache:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def put(self, key: str, value: str) -> None:
        self.data[key] = value


def passages_in(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    text = messages[0]["content"]
    block = text.split("PASSAGES (data):\n```json\n", 1)[1].split("\n```", 1)[0]
    return json.loads(block)  # type: ignore[no-any-return]


def labeller(question: str = "ما المطلوب من الموظف؟", keep: bool = True) -> Callable[[list[dict[str, str]]], str]:
    def reply(messages: list[dict[str, str]]) -> str:
        ps = passages_in(messages)
        return json.dumps({"passages": [{"id": p["id"], "topic": "Policy", "keyword_en": "policy", "question_ar": question,
                                         "keep": keep, "order": i + 1, "merge_with": None} for i, p in enumerate(ps)]},
                          ensure_ascii=False)
    return reply


@pytest.fixture
def chat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    monkeypatch.setenv("OFFLINE", "0")

    def make(*items: Any) -> tuple[CachedChat, FakeClient, DictCache]:
        client, cache = FakeClient(*items), DictCache()
        return CachedChat(client, MODEL, cache, Budget(tmp_path / "budget.json", 3.0)), client, cache

    yield make


def test_verified_reply_is_cached_partly_rejected_is_not(chat: Any) -> None:
    cc, client, cache = chat(json.dumps(good_reply(), ensure_ascii=False))
    verdict, why = llm_organize(P, ["Policy"], cc, 5.0)
    assert why is None and verdict is not None and len(cache.data) == 1
    assert client.calls[0]["params"]["temperature"] == 0 and client.calls[0]["model"] == MODEL
    again, _ = llm_organize(P, ["Policy"], cc, 5.0)  # served from the cache, re-verified
    assert again == verdict and len(client.calls) == 1

    cc2, _, cache2 = chat(json.dumps(good_reply(p2={"question_ar": "هل هي 30 يوماً؟"}), ensure_ascii=False))
    partial, _ = llm_organize(P, ["Policy"], cc2, 5.0)
    assert partial is not None and partial.rejected == 1 and cache2.data == {}  # used, never cached

    cc3, _, cache3 = chat(json.dumps(good_reply(p1={"id": "p7"})), "not json")
    assert llm_organize(P, ["Policy"], cc3, 5.0) == (None, v.FOREIGN_ID)
    assert llm_organize(P, ["Policy"], cc3, 5.0) == (None, v.INVALID_JSON)
    assert cache3.data == {}


def test_prompt_carries_no_ids_documents_or_names() -> None:
    rendered = render_organize_prompt([{"id": "p1", "text": "نص", "heading": "عنوان"}], ["Policy"])
    assert '"p1"' in rendered and "عنوان" in rendered and "import_id" not in rendered and "filename" not in rendered


def test_organize_batches_merges_and_falls_back(chat: Any) -> None:
    texts = [f"المقطع رقم {i} يشرح قاعدة من قواعد العمل اليومية." for i in range(1, 26)]
    passages = chunk([Block(t, 1, "row") for t in texts])
    cc, client, _ = chat(labeller(), LLMUnavailable("OpenRouter request timed out"))
    llm = LLM(chat=cc, model=MODEL, mode="llm")
    items, summary = organize(passages, ["Policy"], requested=True, llm=llm, use_llm=True)
    assert len(client.calls) == 2 and len(passages_in(client.calls[0]["messages"])) == ORGANIZE_BATCH
    assert [i.text for i in items] == texts  # order and text kept
    assert summary.used and summary.organized == 20 and summary.fallback == 5 and summary.reason == "timeout"
    assert items[0].question_ar == "ما المطلوب من الموظف؟" and items[24].question_ar is None
    rev = chat(lambda m: json.dumps({"passages": [
        {"id": "p1", "topic": "Policy", "keyword_en": "a", "question_ar": "ما الأول؟", "keep": True, "order": 2,
         "merge_with": "p2"},
        {"id": "p2", "topic": "Policy", "keyword_en": "b", "question_ar": "ما الثاني؟", "keep": True, "order": 1,
         "merge_with": None},
        {"id": "p3", "topic": "Policy", "keyword_en": "c", "question_ar": "ما الثالث؟", "keep": False, "order": 3,
         "merge_with": None}]}, ensure_ascii=False))[0]
    items2, s2 = organize(passages[:3], ["Policy"], requested=True, llm=LLM(chat=rev, model=MODEL, mode="llm"),
                          use_llm=True)
    assert [i.text for i in items2] == [f"{texts[0]}\n{texts[1]}", texts[2]]  # merged verbatim, then order
    assert s2.merged == 1 and s2.skipped == 1 and items2[1].skip


def test_organize_never_calls_without_request_or_llm(chat: Any) -> None:
    cc, client, _ = chat(labeller())
    llm = LLM(chat=cc, model=MODEL, mode="llm")
    passages = chunk([Block("نص كافٍ ليكون مقطعاً للاختبار هنا.", 1)])
    _, s1 = organize(passages, [], requested=False, llm=llm, use_llm=True)
    _, s2 = organize(passages, [], requested=True, llm=llm, use_llm=False)
    assert client.calls == [] and not s1.used and s2.reason == "llm_off"


# ============================================================================ API
@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[TestClient, Agent, LocalStore]]:
    live = tmp_path_factory.mktemp("live")
    s = get_settings().model_copy(update={"data_live": live})
    store = LocalStore(live)
    agent = build_agent(s, store=store)
    client = TestClient(create_app(s, agent=agent, store=store))
    login = client.post("/api/admin/login", json={"password": s.admin_password.get_secret_value()})
    client.headers["Authorization"] = f"Bearer {login.json()['token']}"
    yield client, agent, store
    store.close()


@pytest.fixture
def client(env: tuple[TestClient, Agent, LocalStore]) -> Iterator[TestClient]:
    yield env[0]
    env[0].post("/api/kb/reset")


@pytest.fixture
def store(env: tuple[TestClient, Agent, LocalStore]) -> LocalStore:
    return env[2]


def upload(client: TestClient, text: str = DOC_TXT, name: str = "dress_code.txt", **kw: Any) -> Any:
    return client.post("/api/admin/kb/imports", json={"filename": name, "content_b64": b64(text), **kw})


def err(r: Any, status: int, code: str, field: str | None = "<any>") -> None:
    assert r.status_code == status, r.text
    body = ErrorBody.model_validate(r.json()).error
    assert body.code == code
    if field != "<any>":
        assert body.field == field


def test_import_endpoints_are_admin_only(env: tuple[TestClient, Agent, LocalStore]) -> None:
    anon = TestClient(env[0].app)
    some = str(uuid.uuid4())
    for method, path, body in (
        ("GET", "/api/admin/kb/import/capabilities", None),
        ("POST", "/api/admin/kb/imports", {"filename": "a.txt", "content_b64": b64("x")}),
        ("GET", "/api/admin/kb/imports", None),
        ("GET", f"/api/admin/kb/imports/{some}", None),
        ("PATCH", f"/api/admin/kb/drafts/{some}", {"topic": "x"}),
        ("POST", f"/api/admin/kb/imports/{some}/approve", {"draft_ids": [some]}),
    ):
        err(anon.request(method, path, json=body), 401, "unauthorized")


def test_capabilities(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    caps = ImportCapabilities.model_validate(client.get("/api/admin/kb/import/capabilities").json())
    assert caps.ai_available is False and caps.max_bytes == 2 * 1024 * 1024 and caps.max_passages == 200
    monkeypatch.setattr(ex, "pdf_available", lambda: False)
    caps = ImportCapabilities.model_validate(client.get("/api/admin/kb/import/capabilities").json())
    assert caps.pdf is False and "pdf" not in caps.types
    err(client.post("/api/admin/kb/imports", json={"filename": "x.pdf", "content_b64": b64(b"%PDF-1.4")}), 400,
        "validation_error", "filename")


def test_body_limit_is_raised_only_for_the_admin_upload(env: tuple[TestClient, Agent, LocalStore]) -> None:
    client = env[0]
    anon = TestClient(client.app)
    big = "سطر عربي قصير للاختبار فقط.\n\n" * 2500  # ~100 KB of text, far more than 200 passages
    err(anon.post("/api/admin/kb/imports", json={"filename": "a.txt", "content_b64": b64(big)}), 413, "payload_too_large")
    err(client.post("/api/kb", json={"topic": "x" * 40000}), 413, "payload_too_large")  # other routes keep 32 KB
    err(upload(client, big), 400, "validation_error", "passages")  # accepted body, refused by the 200 cap
    err(client.post("/api/admin/kb/imports", json={"filename": "a.txt", "content_b64": "A" * (3 * 1024 * 1024)}), 413,
        "payload_too_large")
    raw = b"a" * (2 * 1024 * 1024 + 10)  # decoded > 2 MB inside a body < 3 MB
    err(client.post("/api/admin/kb/imports", json={"filename": "a.txt", "content_b64": b64(raw)}), 413,
        "payload_too_large")


def test_upload_errors(client: TestClient) -> None:
    err(upload(client, name="a.exe"), 400, "validation_error", "filename")
    err(client.post("/api/admin/kb/imports", json={"filename": "a.txt", "content_b64": "%%%"}), 400,
        "validation_error", "content_b64")
    err(upload(client, "\n\n3\n\n"), 400, "validation_error", "content_b64")
    err(upload(client, organize=True, extra=1), 400, "validation_error", "extra")


def test_import_review_approve_answer_reset(client: TestClient, store: LocalStore) -> None:
    kb_before = KbListResponse.model_validate(client.get("/api/kb").json())
    r = upload(client, organize=True)  # offline server: organize falls back, nothing sent
    assert r.status_code == 201, r.text
    detail = ImportDetail.model_validate(r.json())
    assert detail.document.document_name == "dress code" and detail.document.file_type == "txt"
    assert detail.organize is not None and detail.organize.used is False and detail.organize.reason == "llm_off"
    assert [(d.text_ar, d.topic, d.status, d.ord) for d in detail.drafts] == [
        (DRESS, "سياسة اللباس", "draft", 0), (PARKING, "مواقف السيارات", "draft", 1)]
    # Not answerable before approval: the KB and its version are unchanged, the chat cites no draft text.
    assert KbListResponse.model_validate(client.get("/api/kb").json()).version == kb_before.version
    pre = client.post("/api/chat", json={"message": "هل يسمح باللباس غير الرسمي؟"}).json()["reply"]
    assert all(DRESS != s["answer_ar"] for s in pre.get("sources", []))

    dress, parking = detail.drafts
    edited = client.patch(f"/api/admin/kb/drafts/{dress.id}", json={"topic": "Policy", "keyword_en": "dress code"})
    assert edited.status_code == 200 and KbDraft.model_validate(edited.json()).topic == "Policy"
    err(client.patch(f"/api/admin/kb/drafts/{dress.id}", json={"text_ar": "قصير"}), 400, "validation_error", "text_ar")
    err(client.patch(f"/api/admin/kb/drafts/{dress.id}", json={}), 400, "validation_error")
    gone = client.patch(f"/api/admin/kb/drafts/{parking.id}", json={"status": "discarded"})
    assert gone.json()["status"] == "discarded"
    err(client.post(f"/api/admin/kb/imports/{detail.document.id}/approve", json={"draft_ids": [parking.id]}), 409,
        "kb_conflict")

    r = client.post(f"/api/admin/kb/imports/{detail.document.id}/approve", json={"draft_ids": [dress.id]})
    assert r.status_code == 200, r.text
    ap = ApproveResponse.model_validate(r.json())
    assert [(x.id, x.status, x.answer_ar, x.source_document, x.source_page, x.topic) for x in ap.rows] == [
        ("K19", "added", DRESS, "dress code", 1, "Policy")]
    assert ap.drafts[0].row_id == "K19" and ap.drafts[0].status == "approved" and ap.version != kb_before.version
    hist = [h["source"] for h in store.kb_history("K19")]
    assert hist == ["editor"]
    err(client.patch(f"/api/admin/kb/drafts/{dress.id}", json={"topic": "x"}), 409, "kb_conflict")
    listing = ImportListResponse.model_validate(client.get("/api/admin/kb/imports").json())
    mine = next(i for i in listing.imports if i.id == detail.document.id)
    assert (mine.approved, mine.pending, mine.discarded, mine.status) == (1, 0, 1, "done")

    # Answerable now, cited verbatim from the new row.
    a = client.post("/api/chat", json={"message": "هل يسمح باللباس غير الرسمي؟"}).json()["reply"]
    src = next(s for s in a["sources"] if s["id"] == "K19")
    assert src["answer_ar"] == DRESS and src["source_document"] == "dress code" and src["status"] == "added"

    # Reset removes the row and puts the draft back to pending.
    assert client.post("/api/kb/reset").json()["rows"] == 18
    back = ImportDetail.model_validate(client.get(f"/api/admin/kb/imports/{detail.document.id}").json())
    assert back.organize is None
    assert [(d.status, d.row_id) for d in back.drafts] == [("draft", None), ("discarded", None)]
    assert back.document.status == "open"
    restored = client.patch(f"/api/admin/kb/drafts/{parking.id}", json={"status": "draft"})
    assert restored.json()["status"] == "draft"
    both = client.post(f"/api/admin/kb/imports/{detail.document.id}/approve", json={"draft_ids": [parking.id, dress.id]})
    assert [r["id"] for r in both.json()["rows"]] == ["K19", "K20"]  # document order, consecutive ids
    assert [r["answer_ar"] for r in both.json()["rows"]] == [DRESS, PARKING]


def test_not_found_and_foreign_drafts(client: TestClient) -> None:
    a = ImportDetail.model_validate(upload(client).json())
    b = ImportDetail.model_validate(upload(client, name="other.md").json())
    err(client.get(f"/api/admin/kb/imports/{uuid.uuid4()}"), 404, "not_found")
    err(client.get("/api/admin/kb/imports/not-a-uuid"), 404, "not_found")
    err(client.patch(f"/api/admin/kb/drafts/{uuid.uuid4()}", json={"topic": "x"}), 404, "not_found")
    err(client.post(f"/api/admin/kb/imports/{a.document.id}/approve", json={"draft_ids": [b.drafts[0].id]}), 404,
        "not_found")


def test_approve_waits_for_the_kb_lock(env: tuple[TestClient, Agent, LocalStore]) -> None:
    client, agent, _ = env
    detail = ImportDetail.model_validate(upload(client).json())
    held, release = threading.Event(), threading.Event()

    def hold() -> None:
        with agent.kb.lock:
            held.set()
            release.wait(10)

    t = threading.Thread(target=hold)
    t.start()
    held.wait(5)
    try:
        err(client.post(f"/api/admin/kb/imports/{detail.document.id}/approve",
                        json={"draft_ids": [detail.drafts[0].id]}), 423, "kb_locked")
    finally:
        release.set()
        t.join()
    assert len(agent.kb.rows()) == 18


class NoImportTables(LocalStore):
    """A store without the import tables (Supabase before migration 0003)."""

    def kb_import_create(self, record: dict[str, Any], drafts: list[dict[str, Any]]) -> bool:
        return False

    def kb_imports(self) -> list[dict[str, Any]] | None:
        return None

    def kb_import_get(self, import_id: str) -> dict[str, Any] | None:
        return None

    def kb_drafts(self, **kw: Any) -> list[dict[str, Any]] | None:
        return None


def test_missing_import_tables_answer_503_and_the_app_keeps_working(
        env: tuple[TestClient, Agent, LocalStore], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = env[0]
    broken = NoImportTables(tmp_path)
    monkeypatch.setattr(client.app.state, "store", broken)  # type: ignore[attr-defined]
    err(upload(client), 503, "imports_unavailable")
    err(client.get("/api/admin/kb/imports"), 503, "imports_unavailable")
    err(client.get(f"/api/admin/kb/imports/{uuid.uuid4()}"), 503, "imports_unavailable")
    assert client.post("/api/kb/reset").status_code == 200
    assert client.post("/api/chat", json={"message": "متى تأسست مجموعة الدادا؟"}).status_code == 200
    broken.close()


def test_organize_in_llm_mode_through_the_api(env: tuple[TestClient, Agent, LocalStore], tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    client, agent, _ = env
    monkeypatch.setenv("OFFLINE", "0")
    fake = FakeClient(json.dumps({"title_lines": [1, 3]}), labeller("ما الزي المطلوب في المعرض؟"))
    budget = Budget(tmp_path / "budget.json", 3.0)
    monkeypatch.setattr(agent, "llm", LLM(chat=CachedChat(fake, MODEL, DictCache(), budget), model=MODEL, mode="llm",
                                          budget=budget))
    assert client.get("/api/admin/kb/import/capabilities").json()["ai_available"] is True
    off = upload(client)  # the checkbox off: no call
    assert off.status_code == 201 and fake.calls == []
    assert off.json()["organize"]["titles"] == {"used": False, "count": 0, "reason": "not_requested"}
    on = ImportDetail.model_validate(upload(client, organize=True).json())
    assert len(fake.calls) == 2 and on.organize is not None and on.organize.used and on.organize.organized == 2
    assert on.organize.titles is not None and (on.organize.titles.used, on.organize.titles.count) == (True, 2)
    assert on.document.organized and [d.topic for d in on.drafts] == ["Policy", "Policy"]
    assert on.drafts[0].question_ar == "ما الزي المطلوب في المعرض؟" and on.drafts[0].text_ar == DRESS
    for call in fake.calls:  # the title lines, then the passages: never the file name or an id
        sent = call["messages"][0]["content"]
        assert "dress_code" not in sent and on.document.id not in sent


# ============================================================================ stores
def draft(import_id: str, ord_: int, **over: Any) -> dict[str, Any]:
    return {"id": str(uuid.uuid4()), "import_id": import_id, "ord": ord_, "page": 1, "text_ar": f"نص المقطع رقم {ord_}",
            "topic": "Policy", "keyword_en": "", "question_ar": None, "status": "draft", "row_id": None,
            "created_at": "2026-11-11T10:00:00+00:00", "updated_at": "2026-11-11T10:00:00+00:00", **over}


def record(**over: Any) -> dict[str, Any]:
    return {"id": str(uuid.uuid4()), "filename": "a.txt", "document_name": "A", "file_type": "txt", "pages": 1,
            "passages": 2, "organized": False, "status": "open", "created_at": "2026-11-11T10:00:00+00:00", **over}


def exercise_store(st: Any) -> None:
    rec = record()
    d0, d1 = draft(rec["id"], 0), draft(rec["id"], 1)
    assert st.kb_import_create(rec, [d1, d0])
    assert not st.kb_import_create(record(file_type="exe"), [])
    assert not st.kb_import_create(record(), [draft(rec["id"], 0, text_ar="x")])
    assert not st.kb_import_create(record(), [draft(rec["id"], 0, status="approved")])  # approved needs a row id
    got = st.kb_import_get(rec["id"])
    assert got["document_name"] == "A" and got["organized"] is False
    assert st.kb_import_get(str(uuid.uuid4())) == {}
    assert [d["ord"] for d in st.kb_drafts(import_id=rec["id"])] == [0, 1]
    assert st.kb_drafts_save([{**d0, "status": "approved", "row_id": "K19"}])
    assert [d["id"] for d in st.kb_drafts(status="approved")] == [d0["id"]]
    assert st.kb_drafts(ids=[d1["id"]])[0]["status"] == "draft"
    assert st.kb_drafts(ids=["nope"]) == []
    assert st.kb_import_update(rec["id"], {"status": "done"})
    assert [i["status"] for i in st.kb_imports() if i["id"] == rec["id"]] == ["done"]


def test_local_store_imports(tmp_path: Path) -> None:
    st = LocalStore(tmp_path)
    exercise_store(st)
    assert {r["status"] for r in st.table_rows("kb_drafts")} == {"draft", "approved"}
    st.close()


class FakeImportsPostgrest:
    """PostgREST for kb_imports / kb_drafts: select with eq./in. filters, insert, upsert, patch, delete."""

    def __init__(self, missing: bool = False) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {"kb_imports": [], "kb_drafts": []}
        self.missing = missing
        self.requests: list[httpx.Request] = []

    @staticmethod
    def _match(row: dict[str, Any], params: dict[str, list[str]]) -> bool:
        for col, (cond, *_) in params.items():
            if col in ("select", "order", "limit", "on_conflict"):
                continue
            if cond.startswith("eq.") and str(row.get(col)) != cond[3:]:
                return False
            if cond.startswith("in.(") and str(row.get(col)) not in [x.strip('"') for x in cond[4:-1].split(",")]:
                return False
        return True

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        table = request.url.path.rsplit("/", 1)[-1]
        if self.missing or table not in self.tables:
            return httpx.Response(404, json={"code": "PGRST205", "message": "Could not find the table"})
        params = parse_qs(request.url.query.decode())
        rows = self.tables[table]
        if request.method == "GET":
            out = sorted((r for r in rows if self._match(r, params)), key=lambda r: (r.get("ord", 0)))
            if table == "kb_imports":
                out = list(reversed(out))
            return httpx.Response(200, json=out)
        if request.method == "PATCH":
            for r in rows:
                if self._match(r, params):
                    r.update(json.loads(request.content))
            return httpx.Response(204)
        if request.method == "DELETE":
            self.tables[table] = [r for r in rows if not self._match(r, params)]
            return httpx.Response(204)
        body = json.loads(request.content)
        for item in body if isinstance(body, list) else [body]:
            found = [r for r in rows if r["id"] == item["id"]]
            if found and "merge-duplicates" in request.headers.get("Prefer", ""):
                found[0].update(item)
            elif found:
                return httpx.Response(409)
            else:
                rows.append(dict(item))
        return httpx.Response(201)


def test_supabase_store_imports(tmp_path: Path) -> None:
    fake = FakeImportsPostgrest()
    sb = SupabaseStore("https://example.supabase.test", "sb_" + "secret_TEST", data_live=tmp_path,
                       transport=httpx.MockTransport(fake))
    exercise_store(sb)
    assert sb.name == "supabase" and not (tmp_path / "local.sqlite").exists()
    upsert = [r for r in fake.requests if r.method == "POST" and r.url.path.endswith("kb_drafts")][-1]
    assert parse_qs(upsert.url.query.decode())["on_conflict"] == ["id"]
    sb.close()


def test_supabase_without_migration_fails_softly_and_does_not_flip(tmp_path: Path) -> None:
    sb = SupabaseStore("https://example.supabase.test", "sb_" + "secret_TEST", data_live=tmp_path,
                       transport=httpx.MockTransport(FakeImportsPostgrest(missing=True)))
    assert sb.kb_import_create(record(), []) is False
    assert sb.kb_imports() is None and sb.kb_import_get(str(uuid.uuid4())) is None
    assert sb.kb_drafts(status="approved") is None and sb.kb_drafts_save([]) is True
    assert sb.name == "supabase" and sb.fallback_reason is None  # the rest of the app keeps Supabase
    sb.close()


def test_add_many_validates_all_first_and_notifies_once(tmp_path: Path) -> None:
    from app.kb import KnowledgeBase

    kb = KnowledgeBase(official_path=get_settings().data_official / "knowledge_base.csv", live_dir=tmp_path)
    seen: list[Any] = []
    kb.subscribe(seen.append)
    row = {"topic": "Policy", "answer_ar": DRESS, "keyword_en": "", "source_document": "Doc", "source_page": 1}
    with pytest.raises(ValueError):
        kb.add_many([row, {**row, "answer_ar": "x"}])
    assert len(kb.rows()) == 18 and seen == []
    added = kb.add_many([row, {**row, "answer_ar": PARKING, "source_page": 2}])
    assert [r.id for r in added] == ["K19", "K20"] and seen == [("K19", "K20")]
    assert kb.add_many([]) == [] and len(seen) == 1


# ============================================================================ title detection (P13.4)
LINES = [{"n": 1, "page": 1, "text": "دليل الأدوات اليومية"},
         {"n": 2, "page": 1, "text": "يستلم الموظف جهازاً محمولاً في يومه الأول من قسم تقنية المعلومات."},
         {"n": 3, "page": 1, "text": "نظام التذاكر:"},
         {"n": 4, "page": 1, "text": "تُرفع كل مشكلة تقنية عبر نظام التذاكر ويُرد عليها خلال يوم عمل."},
         {"n": 5, "page": 2, "text": "Page 2"}]


def test_good_titles_reply_passes() -> None:
    verdict = v.verify_titles({"title_lines": [3, 1]}, LINES, 5)
    assert verdict.ok and verdict.lines == [1, 3] and verdict.rejected == 0  # a short line ending in ":" is fine
    assert v.verify_titles({"title_lines": []}, LINES, 5).lines == []


def test_titles_reply_with_a_bad_shape_is_rejected_whole() -> None:
    assert v.verify_titles([1, 3], LINES, 5).reason == v.INVALID_JSON
    for bad in ({"titles": [1]}, {"title_lines": 1}, {"title_lines": [1], "text": "x"}, {"title_lines": ["1"]},
                {"title_lines": [1.0]}, {"title_lines": [True]}, {"title_lines": [None]}):
        verdict = v.verify_titles(bad, LINES, 5)
        assert not verdict.ok and verdict.reason == v.BAD_SHAPE, bad


def test_bad_title_numbers_are_dropped_one_by_one() -> None:
    long_title = {"n": 6, "page": 2, "text": "ع" * 81}
    sentence = {"n": 7, "page": 2, "text": "يُرجى مراجعة قسم الموارد البشرية قبل نهاية الأسبوع الأول."}  # > 40 + "."
    digits = {"n": 8, "page": 2, "text": "2026 - 3"}
    last = {"n": 9, "page": 2, "text": "الخاتمة"}
    lines = [*LINES, long_title, sentence, digits, last]
    for n in (0, 10, -1, 6, 7, 8, 9):  # out of range, too long, a sentence, no letter, the last line
        verdict = v.verify_titles({"title_lines": [1, n]}, lines, 9)
        assert verdict.ok and verdict.lines == [1] and verdict.rejected == 1, n
    dup = v.verify_titles({"title_lines": [1, 3, 1]}, lines, 9)
    assert dup.lines == [1, 3] and dup.rejected == 1
    assert v.title_line_ok("قواعد اللباس في المعرض.", 1, 9)  # short and punctuated: still allowed


def test_titles_prompt_carries_numbers_pages_and_cut_lines_only() -> None:
    from app.llm.paths import TITLES_LINE_CHARS, render_titles_prompt

    rendered = render_titles_prompt([{"n": 4, "page": 2, "text": "عنوان"}, {"n": 5, "page": 2, "text": "ب" * 500}])
    block = json.loads(rendered.split("LINES (data):\n```json\n", 1)[1].split("\n```", 1)[0])
    assert block[0] == {"n": 4, "page": 2, "text": "عنوان"}
    assert len(block[1]["text"]) == TITLES_LINE_CHARS and block[1]["text"].endswith("…")
    assert "filename" not in rendered and "import_id" not in rendered


def lines_in(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    text = messages[0]["content"]
    return json.loads(text.split("LINES (data):\n```json\n", 1)[1].split("\n```", 1)[0])  # type: ignore[no-any-return]


def titler(*titles: str) -> Callable[[list[dict[str, str]]], str]:
    """A fake model that picks the lines whose text is one of `titles`."""
    def reply(messages: list[dict[str, str]]) -> str:
        return json.dumps({"title_lines": [ln["n"] for ln in lines_in(messages) if ln["text"] in titles]})
    return reply


def test_titles_cached_only_when_nothing_was_rejected(chat: Any) -> None:
    from app.llm.paths import llm_titles

    cc, client, cache = chat(json.dumps({"title_lines": [1, 3]}))
    verdict, why = llm_titles(LINES, 5, cc, 5.0)
    assert why is None and verdict is not None and verdict.lines == [1, 3] and len(cache.data) == 1
    assert client.calls[0]["params"]["temperature"] == 0 and client.calls[0]["model"] == MODEL
    again, _ = llm_titles(LINES, 5, cc, 5.0)  # from the cache, re-verified
    assert again == verdict and len(client.calls) == 1

    cc2, _, cache2 = chat(json.dumps({"title_lines": [1, 5]}))  # 5 is the last line: dropped
    partial, _ = llm_titles(LINES, 5, cc2, 5.0)
    assert partial is not None and partial.lines == [1] and partial.rejected == 1 and cache2.data == {}

    cc3, _, cache3 = chat(json.dumps({"title_lines": "1,3"}), "not json")
    assert llm_titles(LINES, 5, cc3, 5.0) == (None, v.BAD_SHAPE)
    assert llm_titles(LINES, 5, cc3, 5.0) == (None, v.INVALID_JSON)
    assert cache3.data == {}


def test_rebuild_keeps_text_pages_and_paragraphs() -> None:
    from app.kb_import.titles import document_lines, rebuild

    blocks = [Block("مقدمة", 1, "heading"),  # a rule-based heading the model does not choose
              Block("دليل الأدوات اليومية\nيستلم الموظف جهازاً.\nنظام التذاكر\nتُرفع المشكلات عبر النظام.", 1),
              Block("فقرة ثانية في الصفحة نفسها.", 1),
              Block("الإجازات\nتُقدّم الطلبات عبر البوابة.", 2)]
    lines = document_lines(blocks)
    assert [(ln.n, ln.page) for ln in lines] == [(1, 1), (2, 1), (3, 1), (4, 1), (5, 1), (6, 1), (7, 2), (8, 2)]
    rebuilt = rebuild(lines, {2, 4, 7})
    assert [(b.kind, b.text, b.page) for b in rebuilt] == [
        ("para", "مقدمة", 1), ("heading", "دليل الأدوات اليومية", 1), ("para", "يستلم الموظف جهازاً.", 1),
        ("heading", "نظام التذاكر", 1), ("para", "تُرفع المشكلات عبر النظام.", 1),
        ("para", "فقرة ثانية في الصفحة نفسها.", 1),
        ("heading", "الإجازات", 2), ("para", "تُقدّم الطلبات عبر البوابة.", 2)]
    # Verbatim: the same lines in the same order, nothing added or lost.
    assert [x for b in rebuilt for x in b.text.split("\n")] == [ln.text for ln in lines]
    joined = rebuild(lines, set())
    assert joined[0] == Block("مقدمة\n" + blocks[1].text, 1)  # a heading that is not a title joins its text
    assert [b.page for b in rebuild(document_lines([Block("أ\nب", 1), Block("ج", 2)]), set())] == [1, 2]


ONE_PAGE = ("دليل الأدوات اليومية\n"
            "يستلم الموظف جهازاً محمولاً في يومه الأول من قسم تقنية المعلومات، ويوقّع على نموذج الاستلام.\n"
            "نظام التذاكر\n"
            "تُرفع كل مشكلة تقنية عبر نظام التذاكر، ويُرد عليها خلال يوم عمل واحد من فريق الدعم.\n"
            "الإجازات السنوية\n"
            "تُقدَّم طلبات الإجازة عبر بوابة الموظف قبل أسبوع على الأقل، وتحتاج موافقة المدير المباشر.\n")
TITLES = ("دليل الأدوات اليومية", "نظام التذاكر", "الإجازات السنوية")


def test_detect_titles_used_fallback_and_skipped(chat: Any) -> None:
    from app.kb_import.titles import detect_titles

    _, blocks, _ = extract("guide.txt", ONE_PAGE.encode())
    assert [b.kind for b in blocks] == ["para"]  # one paragraph: no rule-based heading
    cc, client, _ = chat(titler(*TITLES))
    out, s = detect_titles("txt", blocks, requested=True, llm=LLM(chat=cc, model=MODEL, mode="llm"), use_llm=True)
    assert (s.used, s.count, s.reason) == (True, 3, None) and len(client.calls) == 1
    assert [b.text for b in out if b.kind == "heading"] == list(TITLES)

    failing, _, _ = chat(LLMUnavailable("OpenRouter request timed out"))
    same, s2 = detect_titles("txt", blocks, requested=True, llm=LLM(chat=failing, model=MODEL, mode="llm"),
                             use_llm=True)
    assert same is blocks and (s2.used, s2.count, s2.reason) == (False, 0, "timeout")

    cc3, client3, _ = chat(titler(*TITLES))
    llm3 = LLM(chat=cc3, model=MODEL, mode="llm")
    docx_blocks = [Block("Leave", 1, "heading"), Block("Annual leave is 14 days.", 1)]
    for kind, bl in (("md", blocks), ("csv", blocks), ("docx", docx_blocks)):
        kept, s3 = detect_titles(kind, bl, requested=True, llm=llm3, use_llm=True)
        assert kept is bl and s3.reason == "structured" and not s3.used
    _, s4 = detect_titles("txt", blocks, requested=False, llm=llm3, use_llm=True)
    _, s5 = detect_titles("txt", blocks, requested=True, llm=llm3, use_llm=False)
    assert (s4.reason, s5.reason) == ("not_requested", "llm_off") and client3.calls == []
    # A Word file with no heading style at all is treated like plain text.
    _, s6 = detect_titles("docx", blocks, requested=True, llm=llm3, use_llm=True)
    assert s6.used and len(client3.calls) == 1


def test_detect_titles_batches_with_global_numbers(chat: Any) -> None:
    from app.kb_import.titles import detect_titles
    from app.llm.paths import TITLES_BATCH

    texts = [f"القسم {i}" if i % 50 == 0 else f"سطر النص رقم {i} يشرح قاعدة من قواعد العمل." for i in range(1, 251)]
    blocks = [Block("\n".join(texts[:-1]), 1), Block("الخاتمة", 1, "heading"), Block(texts[-1], 1)]
    cc, client, _ = chat(lambda m: json.dumps({"title_lines": [ln["n"] for ln in lines_in(m)
                                                               if ln["text"].startswith("القسم ")]}),
                         LLMUnavailable("OpenRouter request timed out"))
    out, s = detect_titles("txt", blocks, requested=True, llm=LLM(chat=cc, model=MODEL, mode="llm"), use_llm=True)
    sent = [lines_in(c["messages"]) for c in client.calls]
    assert [len(x) for x in sent] == [TITLES_BATCH, 51] and sent[1][0]["n"] == TITLES_BATCH + 1
    # Batch 1 passed (4 titles); batch 2 timed out and keeps its rule-based heading «الخاتمة».
    assert s.used and s.count == 4 and s.reason == "timeout"
    assert [b.text for b in out if b.kind == "heading"] == ["القسم 50", "القسم 100", "القسم 150", "القسم 200",
                                                            "الخاتمة"]
    assert [x for b in out for x in b.text.split("\n")] == [*texts[:-1], "الخاتمة", texts[-1]]


def test_model_titles_split_a_pdf_page(chat: Any) -> None:
    """Titles that end with a colon are not rule-based headings; the model's line numbers split the page."""
    pytest.importorskip("pypdf")
    from app.kb_import.titles import detect_titles

    pdf = make_pdf([["Laptop:", "You get a laptop on your first day from the IT team.", "Tickets:",
                     "Report every issue in the ticket system within one day.", "Page 1"]])
    _, blocks, _ = extract("t.pdf", pdf)
    assert not any(b.kind == "heading" for b in blocks)
    cc, _, _ = chat(titler("Laptop:", "Tickets:"))
    out, s = detect_titles("pdf", blocks, requested=True, llm=LLM(chat=cc, model=MODEL, mode="llm"), use_llm=True)
    passages = chunk(out)
    assert s.used and [p.heading for p in passages] == ["Laptop:", "Tickets:"] and [p.page for p in passages] == [1, 1]


def test_titles_through_the_api_split_one_page_into_sections(env: tuple[TestClient, Agent, LocalStore],
                                                             tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, agent, _ = env
    before = ImportDetail.model_validate(upload(client, ONE_PAGE, name="guide.txt", organize=True).json())
    assert len(before.drafts) == 1 and before.organize is not None and before.organize.titles is not None
    assert before.organize.titles.reason == "llm_off"  # offline server: nothing sent, one run-on passage
    monkeypatch.setenv("OFFLINE", "0")
    fake = FakeClient(titler(*TITLES), labeller())
    budget = Budget(tmp_path / "budget.json", 3.0)
    monkeypatch.setattr(agent, "llm", LLM(chat=CachedChat(fake, MODEL, DictCache(), budget), model=MODEL, mode="llm",
                                          budget=budget))
    r = upload(client, ONE_PAGE, name="guide.txt", organize=True)
    assert r.status_code == 201, r.text
    detail = ImportDetail.model_validate(r.json())
    assert detail.organize is not None and detail.organize.titles is not None
    assert (detail.organize.titles.used, detail.organize.titles.count) == (True, 3)
    body = [ln for ln in ONE_PAGE.splitlines() if ln not in TITLES]
    assert [d.text_ar for d in detail.drafts] == body and all(d.page == 1 for d in detail.drafts)
    assert "guide" not in fake.calls[0]["messages"][0]["content"]
    assert lines_in(fake.calls[0]["messages"])[0] == {"n": 1, "page": 1, "text": TITLES[0]}


def _eval_titles() -> Any:
    import importlib.util

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("eval_titles", root / "scripts" / "eval_titles.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_eval_titles_dry_run_without_a_model(tmp_path: Path) -> None:
    mod = _eval_titles()
    out = tmp_path / "titles.csv"
    assert mod.main(["--out", str(out)]) == 0  # OFFLINE=1 in tests: rule-based columns only
    rows = list(csv.DictReader(io.StringIO(out.read_text(encoding="utf-8"))))
    assert len(rows) == len(mod.DOCS) and all(r["used"] == "not_run" and r["model_tp"] == "not_run" for r in rows)
    assert mod.main(["--out", str(tmp_path / "x.csv"), "--require-llm"]) == 2 and not (tmp_path / "x.csv").exists()


def test_eval_titles_scores_a_fake_model(chat: Any, tmp_path: Path) -> None:
    mod = _eval_titles()
    expected = {t for _, _, titles in mod.DOCS for t in titles}
    cc, client, _ = chat(*[titler(*expected) for _ in mod.DOCS])
    budget = Budget(tmp_path / "b.json", 3.0)
    out = tmp_path / "titles.csv"
    assert mod.main(["--out", str(out)], llm=LLM(chat=cc, model=MODEL, mode="llm", budget=budget)) == 0
    rows = list(csv.DictReader(io.StringIO(out.read_text(encoding="utf-8"))))
    assert len(client.calls) == len(mod.DOCS)
    # The rule joins nothing the model needs here, so a perfect fake finds every title and nothing else.
    assert all((r["used"], r["model_fp"]) == ("1", "0") for r in rows)
    total = sum(len(t) for _, _, t in mod.DOCS)
    assert sum(int(r["model_tp"]) for r in rows) == total and sum(int(r["model_fn"]) for r in rows) == 0
    assert mod.summarise(rows, 0.0).startswith(f"docs={len(mod.DOCS)} used={len(mod.DOCS)}/{len(mod.DOCS)} "
                                               f"model_tp={total} model_fp=0 model_fn=0")
