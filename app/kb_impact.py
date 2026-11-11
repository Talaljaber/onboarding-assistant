"""KB impact (P14.1): who and what one K-row reaches, shown to the admin before an edit is saved.

What it does: lists the interns whose turn logs cite the row (through their profiles; `Store.activity` gives
ids and labels only), the plan activities of either track that reference it, and the quiz items whose
explanation is this row.
What it must never do: read chat text (the store never keeps it), count or rank per intern, or reach answer,
agent or prompt code (an intern's name stays in admin views).
"""

from __future__ import annotations

from typing import Any

from app.plan import PlanBook
from app.quiz import QuizBook
from app.schemas import ROLES, InternPublic, KbImpact


def build(row_id: str, store: Any, plan: PlanBook, quiz: QuizBook) -> KbImpact:
    profiles = store.intern_profiles()
    owner = {str(p["id"]): str(p["intern_id"]) for p in profiles if p.get("intern_id")}
    turns = store.activity(list(owner))["turns"] if owner else []
    citing = {owner[str(t.get("profile_id"))] for t in turns
              if str(t.get("profile_id")) in owner and row_id in (t.get("cited_ids") or [])}
    interns = [InternPublic(id=i["id"], name_ar=i["name_ar"], name_en=i.get("name_en"), role=i["role"])
               for i in (store.list_interns() or []) if str(i["id"]) in citing]
    activity_ids = [a.id for role in ROLES for a in plan.activities(role) if row_id in a.refs]
    quiz_ids = [q.id for q in quiz.quiz_for(None) if q.source_knowledge_id == row_id]
    return KbImpact(id=row_id, interns=interns, activity_ids=activity_ids, quiz_ids=quiz_ids)


__all__ = ["build"]
