# mypy: disallow-untyped-defs, disallow-incomplete-defs, disallow-untyped-calls, disallow-any-generics, check-untyped-defs, warn-return-any, warn-unused-ignores, no-implicit-reexport, strict-equality, disallow-untyped-decorators, disallow-subclassing-any
"""Arabic normalisation, tokenising, light stemming and digit / number-word mapping (plan Part C §4.1).

What it does: the single text normaliser for retrieval, guards, the router and the verifier.
`normalize` = NFC → collapse whitespace → tanween alif → diacritics off → char map → ASCII digits →
lowercase → strip edge punctuation. `tokens` adds stopwords and a light prefix/suffix stemmer (BM25 only).
`number_words_to_digits` maps Arabic number words to digits (verifier and milestone detector, never BM25).

What it must never do: import other app modules, read files, or depend on anything but the stdlib.
Every pattern elsewhere in the app is written in the post-normalisation form produced here
(e.g. «مسوول», not «مسؤول»).
"""

from __future__ import annotations

import re
import unicodedata

# Lifted from CampusPulse adapters/preprocess/wrappers.py (AR_DIACRITICS, AR_CHARMAP).
AR_DIACRITICS = re.compile("[ً-ْٰـ]")  # harakat, dagger alif, tatweel
AR_CHARMAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})
#: Tanween fath written on or before the alif: «اً» / «ًا» → «ا» (applied before diacritics are stripped).
TANWEEN_ALIF = re.compile("(?:اً|ًا)")
PUNCT = " \t\n.,;:!?؟،؛-«»\"'"
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_WS = re.compile(r"\s+")
_TOKEN = re.compile(r"[\w’']+")

PREFIXES: tuple[str, ...] = ("وال", "بال", "كال", "فال", "لل", "ال", "و", "ب", "ل", "ف")
SUFFIXES: tuple[str, ...] = ("هما", "كم", "هم", "ها", "ات", "ون", "ين", "يه", "ه", "ي", "ك")
_MIN_STEM = 3

FUNCTION_STOP: frozenset[str] = frozenset(
    (
        "في من على عن الى الي ما ماذا متى كيف هل هو هي هذا هذه شو مين وين قديش كم اي او و ان انه مع قبل"
        " بعد لل ال عند"
        " بدي لازم ممكن بقدر اللي يعني اذا كان شي حدا عنا عندكم عندي انا احنا يتم تم ايه"
        " why what who how is are the a of to do i my can for in on be does"
    ).split()
)
#: Company-name words (post-normalisation, post-stem forms; review_exp5.py): they would pull every row.
COMPANY_STOP: frozenset[str] = frozenset({"شرك", "شركه", "مجموع", "مجموعه", "دادا", "داد"})
BM25_STOP: frozenset[str] = FUNCTION_STOP | COMPANY_STOP

#: Arabic number words → digits (applied to normalised text, whole-word, multiword keys first).
NUMBER_WORDS: dict[str, int] = {
    "سبعه عشر": 17,
    "سبعة عشر": 17,
    "واحد": 1,
    "واحده": 1,
    "اول": 1,
    "الاول": 1,
    "الاولي": 1,
    "اثنين": 2,
    "اثنان": 2,
    "ثاني": 2,
    "الثاني": 2,
    "الثانيه": 2,
    "ثلاث": 3,
    "ثلاثه": 3,
    "الثلاثه": 3,
    "ثالث": 3,
    "الثالث": 3,
    "اربع": 4,
    "اربعه": 4,
    "خمس": 5,
    "خمسه": 5,
    "الخمس": 5,
    "الخمسه": 5,
    "سبع": 7,
    "سبعه": 7,
    "عشر": 10,
    "عشره": 10,
    "سبعطعش": 17,
    "ثلاثين": 30,
    "الثلاثين": 30,
    "ستين": 60,
    "الستين": 60,
    "تسعين": 90,
    "التسعين": 90,
    "تسعون": 90,
    "شهر": 1,
    "شهرين": 2,
    "سنه": 1,
    "سنتين": 2,
    "خمسين": 50,
    "مئه": 100,
    "ميه": 100,
    "الف": 1000,
}
_NUMBER_KEYS = sorted(NUMBER_WORDS, key=lambda k: (-len(k.split()), -len(k)))
# An optional conjunction «و» is kept in front of the digit («والثاني» → «و2»).
_NUMBER_RE = re.compile(r"(?<![\w])(و?)(" + "|".join(re.escape(k) for k in _NUMBER_KEYS) + r")(?![\w])")
_NUM = re.compile(r"\d+")


def collapse_ws(text: str) -> str:
    """Replace NBSP with a space, collapse whitespace runs to one space, strip."""
    return _WS.sub(" ", text.replace("\xa0", " ")).strip()


def ascii_digits(text: str) -> str:
    """Arabic-Indic (U+0660–0669) and extended (U+06F0–06F9) digits → ASCII 0-9."""
    return text.translate(_DIGITS)


def normalize(text: str) -> str:
    """NFC → collapse_ws → tanween alif → diacritics off → char map → ASCII digits → lowercase → strip PUNCT."""
    s = collapse_ws(unicodedata.normalize("NFC", text))
    s = TANWEEN_ALIF.sub("ا", s)
    s = AR_DIACRITICS.sub("", s)
    s = s.translate(AR_CHARMAP)
    s = ascii_digits(s).lower()
    return s.strip(PUNCT)


def stem(word: str) -> str:
    """Strip one prefix then one suffix, each only when at least three characters remain."""
    for p in PREFIXES:
        if word.startswith(p) and len(word) - len(p) >= _MIN_STEM:
            word = word[len(p) :]
            break
    for s in SUFFIXES:
        if word.endswith(s) and len(word) - len(s) >= _MIN_STEM:
            word = word[: -len(s)]
            break
    return word


def words(text: str) -> list[str]:
    """Raw word tokens of the normalised text (no stopwords removed, no stemming)."""
    return _TOKEN.findall(normalize(text))


def tokens(text: str, *, stoplist: frozenset[str] = BM25_STOP) -> list[str]:
    """Normalised, stemmed tokens; the stoplist is applied before and after stemming.

    The tanween alif is dropped here (معرضاً → معرض), as in the measured BM25 configuration (review_exp5.py).
    """
    out: list[str] = []
    for w in _TOKEN.findall(normalize(TANWEEN_ALIF.sub("", text))):
        if w in stoplist:
            continue
        s = stem(w)
        if s and s not in stoplist:
            out.append(s)
    return out


def number_words_to_digits(text: str) -> str:
    """Replace whole-word Arabic number words with digits (expects normalised text)."""
    return _NUMBER_RE.sub(lambda m: m.group(1) + str(NUMBER_WORDS[m.group(2)]), text)


def numbers_in(text: str) -> set[str]:
    """Every number in the text after normalisation and number-word mapping, as digit strings."""
    return set(_NUM.findall(number_words_to_digits(normalize(text))))


__all__ = [
    "AR_CHARMAP",
    "AR_DIACRITICS",
    "BM25_STOP",
    "COMPANY_STOP",
    "FUNCTION_STOP",
    "NUMBER_WORDS",
    "PUNCT",
    "TANWEEN_ALIF",
    "ascii_digits",
    "collapse_ws",
    "normalize",
    "number_words_to_digits",
    "numbers_in",
    "stem",
    "tokens",
    "words",
]
