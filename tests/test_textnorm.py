"""Normalisation, tokens, stemming and number words (plan Part C §4.1, §9)."""

from __future__ import annotations

import pytest

from app.textnorm import (
    AR_CHARMAP,
    AR_DIACRITICS,
    BM25_STOP,
    ascii_digits,
    normalize,
    number_words_to_digits,
    numbers_in,
    stem,
    tokens,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("أحمد", "احمد"),
        ("إجازة", "اجازه"),
        ("آخر", "اخر"),
        ("مستشفى", "مستشفي"),
        ("مسؤول", "مسوول"),
        ("شاطئ", "شاطي"),
        ("يُقدَّم", "يقدم"),
        ("الـــدادا", "الدادا"),
        ("مَدْرَسَةٌ", "مدرسه"),
        ("  «سؤالٌ؟»  ", "سوال"),
    ],
)
def test_charmap_and_diacritics(raw: str, expected: str) -> None:
    assert normalize(raw) == expected
    # parity with the lifted CampusPulse primitives
    assert AR_DIACRITICS.sub("", expected).translate(AR_CHARMAP) == expected


def test_tanween_alif() -> None:
    assert normalize("معرضاً") == "معرضا"
    assert normalize("يوماً") == "يوما"
    assert tokens("معرضاً") == ["معرض"]


def test_arabic_indic_digits() -> None:
    assert ascii_digits("٣٠ و۹۰") == "30 و90"
    assert normalize("اليوم ٣٠") == "اليوم 30"


def test_number_words() -> None:
    assert numbers_in("الشهر الاول والثاني") == {"1", "2"}
    assert number_words_to_digits(normalize("اليوم الثلاثين")) == "اليوم 30"
    assert number_words_to_digits("سبعه عشر معرضا") == "17 معرضا"
    assert numbers_in("تسعين يوما") == {"90"}


def test_stem_never_below_three() -> None:
    for w in ["الى", "بال", "وها", "كتب", "الكتاب", "والمعارض", "موظفين"]:
        s = stem(w)
        assert len(s) >= min(3, len(w))
    assert stem("والمعارض") == "معارض"
    assert stem("الموظفين") == "موظف"


def test_company_stoplist() -> None:
    toks = tokens("شركة الدادا والمجموعة مجموعة دادا الشركة")
    assert toks == []
    assert "شركه" in BM25_STOP and "مجموع" in BM25_STOP


def test_tokens_drop_function_words() -> None:
    assert tokens("متى تأسست المجموعة؟") == ["متي", "تاسست"]  # raw-form stoplist, as measured
    assert "اجاز" in tokens("كيف أقدم طلب إجازة؟")
