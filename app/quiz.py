"""The practice quiz: items from the official sample quiz, checked against the K-row they cite.

What it does: loads `data/official/sample_quiz.csv`, returns the items for a role (items referenced
by the role's Day 30 activities first, then the rest, official order otherwise) **without** the
correct option, and checks one answer, returning the correct option and the cited K-row as the
explanation (the live row when a knowledge base is passed, else the official row).

What it must never do: send the correct option with the items, keep a score or count of attempts
(the store records only that an attempt was made), or call the network.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from app import content_en, schemas

OPTION_KEYS: tuple[str, ...] = ("A", "B", "C")


@dataclass(frozen=True)
class QuizItem:
    """What the client sees. There is deliberately no correct-option field."""

    id: str
    question_ar: str
    options: dict[str, str]
    source_knowledge_id: str

    def to_schema(self) -> schemas.QuizItem:
        question_en, options_en = content_en.en(f"quiz:{self.id}"), content_en.quiz_options_en(self.id)
        both = question_en is not None and options_en is not None
        return schemas.QuizItem(
            id=self.id,
            question_ar=self.question_ar,
            options=dict(self.options),  # type: ignore[arg-type]
            source_knowledge_id=self.source_knowledge_id,
            question_en=question_en if both else None,
            options_en=options_en if both else None,  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class KbRowRef:
    """An official K-row, used as the explanation when no live knowledge base is passed."""

    id: str
    topic: str
    answer_ar: str
    keyword_en: str
    source_document: str
    source_page: int
    edited: bool = False
    status: str = "official"


class KbLike(Protocol):
    """The live knowledge base (`app.kb.KnowledgeBase`): `get(id)` returns a row or None."""

    def get(self, id: str) -> Any: ...


@dataclass(frozen=True)
class QuizResult:
    correct: bool
    correct_option: str
    explanation_row: Any

    def to_schema(self) -> schemas.QuizCheckResponse:
        row = self.explanation_row
        status = getattr(row, "status", None) or ("edited" if row.edited else "official")
        return schemas.QuizCheckResponse(
            correct=self.correct,
            correct_option=self.correct_option,  # type: ignore[arg-type]
            explanation=schemas.Source(
                id=row.id,
                topic=row.topic,
                answer_ar=row.answer_ar,
                source_document=row.source_document,
                source_page=int(row.source_page),
                edited=bool(row.edited),
                status=status,  # type: ignore[arg-type]
            ),
        )


def _read_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))


class QuizBook:
    """The five official quiz items and their answers (kept apart from the items)."""

    def __init__(self, quiz_rows: list[dict[str, str]], kb_rows: list[dict[str, str]]) -> None:
        self._items: dict[str, QuizItem] = {}
        self._answers: dict[str, str] = {}
        for r in quiz_rows:
            self._items[r["id"]] = QuizItem(
                id=r["id"],
                question_ar=r["question_ar"],
                options={"A": r["option_a"], "B": r["option_b"], "C": r["option_c"]},
                source_knowledge_id=r["source_knowledge_id"],
            )
            answer = r["correct_option"].strip().upper()
            if answer not in OPTION_KEYS:
                raise ValueError(f"quiz {r['id']}: bad correct_option")
            self._answers[r["id"]] = answer
        self._kb: dict[str, KbRowRef] = {
            r["id"]: KbRowRef(
                id=r["id"],
                topic=r["topic"],
                answer_ar=r["answer_ar"],
                keyword_en=r["keyword_en"],
                source_document=r["source_document"],
                source_page=int(r["source_page"]),
            )
            for r in kb_rows
        }
        for item in self._items.values():
            if item.source_knowledge_id not in self._kb:
                raise ValueError(f"quiz {item.id}: unknown K-row {item.source_knowledge_id}")

    @classmethod
    def from_files(cls, official_dir: Path | None = None) -> QuizBook:
        if official_dir is None:
            from app.config import get_settings

            official_dir = get_settings().data_official
        return cls(_read_csv(official_dir / "sample_quiz.csv"), _read_csv(official_dir / "knowledge_base.csv"))

    def ids(self) -> list[str]:
        return list(self._items)

    def has(self, id: str) -> bool:
        return id in self._items

    def quiz_for(self, role: str | None, *, first_ids: list[str] | None = None) -> list[QuizItem]:
        """Items in official order, those listed in `first_ids` (the role's Day 30 refs) first."""
        if role is not None and role not in schemas.ROLES:
            raise ValueError(f"unknown role {role!r}")
        if first_ids is None:
            first_ids = _day30_refs(role) if role is not None else []
        first = set(first_ids)
        items = list(self._items.values())
        return [i for i in items if i.id in first] + [i for i in items if i.id not in first]

    def check(self, id: str, option: str, *, kb: KbLike | None = None) -> QuizResult:
        """Raises KeyError for an unknown id (404) and ValueError for an option outside A/B/C (400)."""
        item = self._items[id]
        if option not in OPTION_KEYS:
            raise ValueError(f"option must be one of {OPTION_KEYS}")
        correct_option = self._answers[id]
        row = kb.get(item.source_knowledge_id) if kb is not None else None
        if row is None:
            row = self._kb[item.source_knowledge_id]
        return QuizResult(correct=option == correct_option, correct_option=correct_option, explanation_row=row)


def _day30_refs(role: str) -> list[str]:
    from app import plan

    return [ref for a in plan.activities_of(role, "Day 30") for ref in a.refs if ref.startswith("Q")]


@lru_cache(maxsize=1)
def default_book() -> QuizBook:
    return QuizBook.from_files()


def quiz_for(role: str | None) -> list[QuizItem]:
    return default_book().quiz_for(role)


def check(id: str, option: str, *, kb: KbLike | None = None) -> QuizResult:
    return default_book().check(id, option, kb=kb)


def quiz_response(role: str | None) -> schemas.QuizResponse:
    """`GET /api/quiz?role=…`: items only, never the correct option."""
    return schemas.QuizResponse(items=[i.to_schema() for i in quiz_for(role)], label_ar=schemas.QUIZ_LABEL_AR)
