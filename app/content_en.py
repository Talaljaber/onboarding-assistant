"""Authored English for the fixed learning content (P16.3): a helper for the English UI, never the reference.

What it does: loads `data/ours/content_en.csv` (`key,text_en,source`) once and returns the English text of a
fixed item by a stable key: `goal:<milestone>`, `activity:<id>`, `scenario:<S>`, `suggested:<S>`,
`customer:<S>`, `option:<O>`, `option_feedback:<O>`, `check_done:<C>`, `check_add:<C>`, `quiz:<Q>`,
`quiz:<Q>:<A|B|C>` and `reply:<name>`. It also fills the optional `*_en` fields of practice feedback by
matching each shown Arabic sentence to the checklist or option row it came from.

What it must never do: change or replace an Arabic field (Arabic stays the reference the server checks and
cites), translate model-written text (`tip_ar` stays Arabic), call the network, or invent a translation: a
missing key gives None and the client shows the Arabic.
"""

from __future__ import annotations

import csv
import io
from functools import lru_cache
from pathlib import Path
from typing import Any

from app import schemas

FILE_NAME = "content_en.csv"


@lru_cache(maxsize=4)
def _table(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    rows = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig")))
    return {r["key"].strip(): r["text_en"].strip() for r in rows if r.get("text_en", "").strip()}


def _path() -> Path:
    from app.config import get_settings

    return get_settings().data_ours / FILE_NAME


def table() -> dict[str, str]:
    """Every authored English text by key (empty when the file is absent)."""
    return dict(_table(_path()))


def en(key: str) -> str | None:
    """The English text for `key`, or None."""
    return _table(_path()).get(key)


def en_all(keys: list[str]) -> list[str] | None:
    """English for every key in order, or None when any one is missing (the client then shows the Arabic list)."""
    out = [en(k) for k in keys]
    return None if any(t is None for t in out) else [t for t in out if t is not None]


def quiz_options_en(quiz_id: str) -> dict[str, str] | None:
    """The three English options of a quiz item, or None unless all three exist."""
    opts = {k: en(f"quiz:{quiz_id}:{k}") for k in ("A", "B", "C")}
    return None if any(v is None for v in opts.values()) else {k: v for k, v in opts.items() if v is not None}


def plan_reply_en(milestone: str | None, milestone_en: str | None = None) -> str | None:
    """English for the fixed `show_plan` reply (whole plan, or one milestone with its goal)."""
    if milestone is None:
        return en("reply:plan")
    template, goal = en("reply:plan_milestone"), en(f"goal:{milestone}")
    if template is None or goal is None:
        return None
    return template.format(milestone=milestone_en or milestone, goal=goal)


def _feedback_sentences(scenario: Any) -> dict[str, str]:
    """Arabic sentence → English for every fixed sentence a feedback of `scenario` can show."""
    out: dict[str, str] = {}
    for c in getattr(scenario, "checklist", ()):
        for ar, key in ((c.done_ar, f"check_done:{c.item_id}"), (c.add_ar, f"check_add:{c.item_id}")):
            text = en(key)
            if text is not None:
                out.setdefault(ar.strip(), text)
    for o in getattr(scenario, "options", ()):
        text = en(f"option_feedback:{o.option_id}")
        if text is not None:
            out.setdefault(o.feedback_ar.strip(), text)
    return out


def feedback(fb: schemas.Feedback, scenario: Any) -> schemas.Feedback:
    """`fb` with its optional English fields set from the fixed sentences it shows (Arabic fields unchanged)."""
    sentences = _feedback_sentences(scenario)
    strengths = [sentences.get(s.strip()) for s in fb.strengths_ar]
    return fb.model_copy(
        update={
            "strengths_en": None if any(s is None for s in strengths) else [s for s in strengths if s is not None],
            "improve_en": sentences.get(fb.improve_ar.strip()) if fb.improve_ar else None,
            "suggested_good_response_en": en(f"suggested:{fb.scenario_id}"),
            "customer_en": en(f"customer:{fb.scenario_id}") if fb.customer_ar else None,
        }
    )


__all__ = ["FILE_NAME", "en", "en_all", "feedback", "plan_reply_en", "quiz_options_en", "table"]
