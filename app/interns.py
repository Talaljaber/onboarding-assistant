"""Interns: the startup seed and the admin's per-intern views (list rows and the detail page).

What it does: `SEED` holds the four fictional demo interns inserted when the interns table is empty;
`summary_row` and `detail` turn an intern, their profiles (one per track) and the timestamped records of
those profiles (`Store.activity`) into the admin's list row and detail page.
What it must never do: hold a real person's name or contact (the organizer forbids real data: the seed
is invented personas), show quiz correctness or any score, or read chat text (turn logs hold ids and
labels only). Answer, agent, LLM and prompt code never import this module: a name never reaches them.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from app import schemas
from app.plan import PlanBook, percent_of

# Invented demo personas (two women, two men), not employees. Seeded once, then managed by the admin.
SEED: tuple[dict[str, str], ...] = (
    {"name_ar": "سارة الخطيب", "name_en": "Sara Al-Khatib", "role": "Sales"},
    {"name_ar": "عمر حداد", "name_en": "Omar Haddad", "role": "Delivery"},
    {"name_ar": "ليان العلي", "name_en": "Layan Al-Ali", "role": "Sales"},
    {"name_ar": "يوسف النجار", "name_en": "Yousef Al-Najjar", "role": "Delivery"},
)

# Turns that answer (or refuse) a question, as opposed to greetings, scenarios, plan or quiz requests.
QUESTION_TOOLS = frozenset({"search_knowledge", "answer_from_rows", "refuse"})
TIMELINE_MAX = 200


def _ts(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def iso(value: object) -> str:
    """One timestamp format for the contract (UTC, milliseconds)."""
    dt = _ts(value)
    return dt.astimezone(UTC).isoformat(timespec="milliseconds") if dt else str(value or "")


def _last(values: Iterable[object]) -> str | None:
    stamps = [d for d in (_ts(v) for v in values) if d is not None]
    return max(stamps).astimezone(UTC).isoformat(timespec="milliseconds") if stamps else None


def _stamps(act: dict[str, list[dict[str, Any]]]) -> list[object]:
    return ([r.get("completed_at") for r in act["progress"]] + [r.get("at") for r in act["quiz"]]
            + [r.get("at") for r in act["scenarios"]] + [r.get("at") for r in act["turns"]])


def public(intern: dict[str, Any]) -> schemas.InternPublic:
    return schemas.InternPublic(id=intern["id"], name_ar=intern["name_ar"], name_en=intern.get("name_en"),
                                role=intern["role"])


def out(intern: dict[str, Any]) -> schemas.InternOut:
    return schemas.InternOut(
        id=intern["id"], name_ar=intern["name_ar"], name_en=intern.get("name_en"), role=intern["role"],
        active=bool(intern["active"]), created_at=iso(intern["created_at"]), updated_at=iso(intern["updated_at"]),
    )


def _current_ids(profiles: list[dict[str, Any]], role: str) -> set[str]:
    return {str(p["id"]) for p in profiles if p.get("role") == role}


def summary_row(intern: dict[str, Any], profiles: list[dict[str, Any]], act: dict[str, list[dict[str, Any]]],
                plan: PlanBook) -> schemas.InternSummary:
    role = intern["role"]
    current = _current_ids(profiles, role)
    known = {a.id for a in plan.activities(role)}
    done = len({r["activity_id"] for r in act["progress"] if str(r["profile_id"]) in current and r["activity_id"] in known})
    total = len(known)
    return schemas.InternSummary(
        id=intern["id"], name_ar=intern["name_ar"], name_en=intern.get("name_en"), role=role,
        active=bool(intern["active"]), created_at=iso(intern["created_at"]),
        percent=percent_of(done, total), activities_done=done, activities_total=total,
        scenarios_practised=len({r["scenario_id"] for r in act["scenarios"]}),
        quiz_attempts=len(act["quiz"]),
        questions_asked=sum(1 for t in act["turns"] if t.get("tool") in QUESTION_TOOLS),
        last_active=_last(_stamps(act)),
    )


def detail(intern: dict[str, Any], profiles: list[dict[str, Any]], act: dict[str, list[dict[str, Any]]],
           plan: PlanBook, scenario_value: Callable[[str], str | None],
           kb_topic: Callable[[str], str | None]) -> schemas.InternDetail:
    role = intern["role"]
    roles = {str(p["id"]): str(p["role"]) for p in profiles}
    current = _current_ids(profiles, role)

    # Plan of the current track, with the date each activity was completed.
    when = {r["activity_id"]: iso(r["completed_at"]) for r in act["progress"] if str(r["profile_id"]) in current}
    milestones: list[schemas.DetailMilestone] = []
    for m in plan.plan_for(role).milestones:
        acts = [schemas.DetailActivity(id=a.id, kind=a.kind, title_ar=a.title_ar,  # type: ignore[arg-type]
                                       completed_at=when.get(a.id)) for a in m.activities]
        milestones.append(schemas.DetailMilestone(
            name=m.name, name_ar=m.name_ar, done=sum(1 for a in acts if a.completed_at),  # type: ignore[arg-type]
            total=len(acts), activities=acts,
        ))
    done = sum(m.done for m in milestones)
    total = sum(m.total for m in milestones)

    # Scenarios practised: how often and when (practice only).
    by_scenario: dict[str, list[dict[str, Any]]] = {}
    for r in act["scenarios"]:
        by_scenario.setdefault(r["scenario_id"], []).append(r)
    scenarios = []
    for sid in sorted(by_scenario):
        rows = by_scenario[sid]
        value = next((r.get("value") for r in reversed(rows) if r.get("value")), None) or scenario_value(sid)
        stamps = sorted(iso(r["at"]) for r in rows)
        scenarios.append(schemas.DetailScenario(
            scenario_id=sid, value=value if value in schemas.VALUES else None,  # type: ignore[arg-type]
            times=len(rows), first_at=stamps[0], last_at=stamps[-1],
        ))

    # Quiz practice: questions answered per day (never correctness).
    per_day = Counter(iso(r["at"])[:10] for r in act["quiz"])
    quiz = schemas.DetailQuiz(answered=len(act["quiz"]),
                              days=[schemas.DetailQuizDay(date=d, answered=n) for d, n in sorted(per_day.items())])

    # Chat: question turns and the K-rows they cited (from turn logs: ids only).
    questions = [t for t in act["turns"] if t.get("tool") in QUESTION_TOOLS]
    cited = Counter(k for t in questions for k in (t.get("cited_ids") or []) if isinstance(k, str))
    chat = schemas.DetailChat(
        questions=len(questions), turns=len(act["turns"]),
        cited=[schemas.DetailCited(id=k, topic=kb_topic(k) or "", count=n)
               for k, n in sorted(cited.items(), key=lambda kv: (-kv[1], kv[0])) if kb_topic(k) is not None],
    )

    events: list[schemas.TimelineEvent] = []
    for r in act["progress"]:
        events.append(schemas.TimelineEvent(at=iso(r["completed_at"]), kind="activity",
                                            role=roles.get(str(r["profile_id"]), role), ids=[r["activity_id"]]))  # type: ignore[arg-type]
    for r in act["scenarios"]:
        events.append(schemas.TimelineEvent(at=iso(r["at"]), kind="scenario",
                                            role=roles.get(str(r["profile_id"]), role), ids=[r["scenario_id"]]))  # type: ignore[arg-type]
    for r in act["quiz"]:
        events.append(schemas.TimelineEvent(at=iso(r["at"]), kind="quiz",
                                            role=roles.get(str(r["profile_id"]), role), ids=[r["question_id"]]))  # type: ignore[arg-type]
    # "Asked the assistant" uses the same definition as `chat.questions`: question turns only. Practice
    # replies already appear as scenario events; greetings, plan and quiz turns are not questions.
    for t in questions:
        ids = [k for k in (t.get("cited_ids") or []) if isinstance(k, str)]
        events.append(schemas.TimelineEvent(at=iso(t["at"]), kind="chat",
                                            role=roles.get(str(t["profile_id"]), role), ids=ids))  # type: ignore[arg-type]
    events.sort(key=lambda e: e.at, reverse=True)

    return schemas.InternDetail(
        intern=out(intern), last_active=_last(_stamps(act)),
        progress=schemas.DetailProgress(role=role, percent=percent_of(done, total), done=done, total=total,
                                        milestones=milestones),
        scenarios=scenarios, quiz=quiz, chat=chat, timeline=events[:TIMELINE_MAX],
        label_ar=schemas.INTERNS_LABEL_AR,
    )


__all__ = ["QUESTION_TOOLS", "SEED", "detail", "iso", "out", "public", "summary_row"]
