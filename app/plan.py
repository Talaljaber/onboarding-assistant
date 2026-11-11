"""The suggested 90-day learning plan and activity-completion progress.

What it does: joins the official milestone goals (`data/official/suggested_learning_plan.csv`) with
our role activities (`data/ours/plan_activities.csv`, 8 per role), returns the plan per role, the
activities of a milestone, the activities still pending, validates a confirmation and computes the
completion percentage `round(100 * done / total)` over the role's activities.

What it must never do: present the plan as an official evaluation schedule (it is "suggested"),
carry a score, grade or quiz correctness, persist progress (the client and the store do), or call
the network.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app import content_en, schemas

MILESTONES: tuple[str, ...] = schemas.MILESTONES
ROLES: tuple[str, ...] = schemas.ROLES
NOTES_AR: tuple[str, ...] = (
    "اختبار اليوم 30 ليس تقييم الشهر الأول المذكور في K14",
    "ملخص اليوم 90 للمراجعة البشرية فقط",
)


@dataclass(frozen=True)
class Activity:
    id: str
    role: str
    milestone: str
    kind: str
    refs: tuple[str, ...]
    title_ar: str

    def to_schema(self) -> schemas.Activity:
        return schemas.Activity(id=self.id, kind=self.kind, title_ar=self.title_ar, refs=list(self.refs),  # type: ignore[arg-type]
                                title_en=content_en.en(f"activity:{self.id}"))


@dataclass(frozen=True)
class Milestone:
    name: str
    goal_ar: str
    status_label: str
    activities: tuple[Activity, ...]

    @property
    def name_ar(self) -> str:
        return schemas.MILESTONES_AR[self.name]


@dataclass(frozen=True)
class Plan:
    role: str
    milestones: tuple[Milestone, ...]

    def to_schema(self, focus_milestone: str | None = None) -> schemas.PlanOut:
        if focus_milestone is not None and focus_milestone not in MILESTONES:
            raise ValueError(f"unknown milestone {focus_milestone!r}")
        return schemas.PlanOut(
            role=self.role,  # type: ignore[arg-type]
            status=schemas.PLAN_STATUS,
            disclaimer_ar=schemas.PLAN_DISCLAIMER_AR,
            focus_milestone=focus_milestone,  # type: ignore[arg-type]
            milestones=[
                schemas.Milestone(
                    name=m.name,  # type: ignore[arg-type]
                    name_ar=m.name_ar,
                    learning_goal_ar=m.goal_ar,
                    activities=[a.to_schema() for a in m.activities],
                    learning_goal_en=content_en.en(f"goal:{m.name}"),
                )
                for m in self.milestones
            ],
            notes_ar=list(NOTES_AR),
        )


@dataclass(frozen=True)
class ProgressSummary:
    """Completion only: activities done out of the role's activities. Never a score."""

    percent: int
    done: int
    total: int
    per_milestone: dict[str, tuple[int, int]]

    def to_schema(self, completed_ids: Sequence[str] | None = None) -> schemas.ProgressSummary:
        return schemas.ProgressSummary(
            percent=self.percent,
            done=self.done,
            total=self.total,
            completed_ids=list(completed_ids) if completed_ids is not None else None,
        )


def percent_of(done: int, total: int) -> int:
    """`round(100 * done / total)` with Python rounding (1/8 → 12, 3/8 → 38); 0 when total is 0."""
    return round(100 * done / total) if total else 0


def _read_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))


class PlanBook:
    """Plan data for both roles, validated at load time."""

    def __init__(self, goals: Sequence[dict[str, str]], activities: Sequence[dict[str, str]]) -> None:
        self._goals: dict[tuple[str, str], tuple[str, str]] = {
            (g["department"], g["milestone"]): (g["learning_goal_ar"], g["status"]) for g in goals
        }
        acts = [
            Activity(
                id=a["activity_id"],
                role=a["role"],
                milestone=a["milestone"],
                kind=a["kind"],
                refs=tuple(r for r in a["refs"].split(";") if r),
                title_ar=a["title_ar"],
            )
            for a in activities
        ]
        self._by_role: dict[str, list[Activity]] = {r: [a for a in acts if a.role == r] for r in ROLES}
        self._by_id: dict[str, Activity] = {a.id: a for a in acts}
        for role in ROLES:
            for m in MILESTONES:
                if (role, m) not in self._goals:
                    raise ValueError(f"plan goal missing for {role} {m}")
            if not self._by_role[role]:
                raise ValueError(f"no activities for {role}")
        for a in acts:
            if a.role not in ROLES or a.milestone not in MILESTONES:
                raise ValueError(f"activity {a.id}: bad role or milestone")

    @classmethod
    def from_files(cls, official_dir: Path | None = None, ours_dir: Path | None = None) -> PlanBook:
        if official_dir is None or ours_dir is None:
            from app.config import get_settings

            s = get_settings()
            official_dir = official_dir or s.data_official
            ours_dir = ours_dir or s.data_ours
        return cls(
            _read_csv(official_dir / "suggested_learning_plan.csv"),
            _read_csv(ours_dir / "plan_activities.csv"),
        )

    def _role(self, role: str) -> list[Activity]:
        if role not in ROLES:
            raise ValueError(f"unknown role {role!r}")
        return self._by_role[role]

    def milestone_names(self) -> list[str]:
        return list(MILESTONES)

    def activities(self, role: str) -> list[Activity]:
        return list(self._role(role))

    def activities_of(self, role: str, milestone: str) -> list[Activity]:
        if milestone not in MILESTONES:
            raise ValueError(f"unknown milestone {milestone!r}")
        return [a for a in self._role(role) if a.milestone == milestone]

    def activity(self, activity_id: str) -> Activity | None:
        return self._by_id.get(activity_id)

    def plan_for(self, role: str) -> Plan:
        acts = self._role(role)
        return Plan(
            role=role,
            milestones=tuple(
                Milestone(
                    name=m,
                    goal_ar=self._goals[(role, m)][0],
                    status_label=self._goals[(role, m)][1],
                    activities=tuple(a for a in acts if a.milestone == m),
                )
                for m in MILESTONES
            ),
        )

    def percent(self, role: str, completed_ids: Iterable[str]) -> ProgressSummary:
        """Completion over the role's activities; ids of other roles or unknown ids are ignored."""
        acts = self._role(role)
        done_set = set(completed_ids)
        per = {
            m: (sum(a.id in done_set for a in acts if a.milestone == m), sum(a.milestone == m for a in acts))
            for m in MILESTONES
        }
        done = sum(a.id in done_set for a in acts)
        return ProgressSummary(percent=percent_of(done, len(acts)), done=done, total=len(acts), per_milestone=per)

    def pending(self, role: str, milestone: str, completed_ids: Iterable[str]) -> list[Activity]:
        """Activities of the milestone not yet completed (what `propose_progress` offers)."""
        done_set = set(completed_ids)
        return [a for a in self.activities_of(role, milestone) if a.id not in done_set]

    def foreign_ids(self, role: str, milestone: str, activity_ids: Iterable[str]) -> list[str]:
        """Ids in a confirmation that are not activities of `role` + `milestone` (non-empty → 400)."""
        allowed = {a.id for a in self.activities_of(role, milestone)}
        return [i for i in activity_ids if i not in allowed]

    def merge_completed(self, completed_ids: Sequence[str], new_ids: Iterable[str]) -> list[str]:
        """The client's list plus the newly confirmed ids, order kept, no duplicates."""
        out = list(dict.fromkeys(completed_ids))
        for i in new_ids:
            if i not in out:
                out.append(i)
        return out


@lru_cache(maxsize=1)
def default_book() -> PlanBook:
    return PlanBook.from_files()


def plan_for(role: str) -> Plan:
    return default_book().plan_for(role)


def percent(role: str, completed_ids: Iterable[str]) -> ProgressSummary:
    return default_book().percent(role, completed_ids)


def milestone_names() -> list[str]:
    return list(MILESTONES)


def activities_of(role: str, milestone: str) -> list[Activity]:
    return default_book().activities_of(role, milestone)


def pending(role: str, milestone: str, completed_ids: Iterable[str]) -> list[Activity]:
    return default_book().pending(role, milestone, completed_ids)


def foreign_ids(role: str, milestone: str, activity_ids: Iterable[str]) -> list[str]:
    return default_book().foreign_ids(role, milestone, activity_ids)


def merge_completed(completed_ids: Sequence[str], new_ids: Iterable[str]) -> list[str]:
    return default_book().merge_completed(completed_ids, new_ids)


def plan_response(role: str, focus_milestone: str | None = None) -> schemas.PlanOut:
    """`GET /api/plan?role=…` and `reply.plan`."""
    return plan_for(role).to_schema(focus_milestone)
