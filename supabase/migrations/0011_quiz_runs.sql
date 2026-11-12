-- Dada Academy onboarding assistant: server-side quiz runs and time limits (P23).
--
-- `quiz_runs`: one sitting of one quiz by one profile: the set (`official` for the built-in sample quiz, else a
-- `quiz_sets` id; no foreign key, like `quiz_attempts.question_id`), the intern (null for an anonymous demo profile,
-- which may only take the official quiz), the profile, the item ids in the order served, when it started, its
-- deadline (null without a time limit), when it closed and its status. Opening a quiz resumes the profile's open
-- run (same questions, same order, answers kept, remaining time) on any device: at most ONE `in_progress` run per
-- (profile, set). The server's clock closes a run lazily once its deadline has passed (`expired`).
-- `quiz_sets.time_limit_minutes`: the admin's optional limit (1-120 minutes; null = none). The official quiz is not a
-- row here and never has one.
-- `quiz_attempts.run_id`: the run an answer belongs to (null for answers given before runs existed or through the
-- old `POST /api/quiz/check`); one answer per (run, question). For a checkpoint set the shared result is the
-- intern's FIRST run (D-P20-checkpoint); old answers keep the earliest-answer rule.
-- Same security as 0001-0010: RLS on, no policies, nothing granted to the browser roles.
-- Idempotent: safe to apply more than once. Apply after 0009_quiz_sets.sql (and 0010).

create table if not exists public.quiz_runs (
    id           uuid primary key default gen_random_uuid(),
    set_id       text not null
                 constraint quiz_runs_set_shape check (
                     set_id = 'official'
                     or set_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                 ),
    intern_id    uuid references public.interns (id) on delete cascade,
    profile_id   uuid not null references public.profiles (id) on delete cascade,
    item_ids     text[] not null default '{}',
    started_at   timestamptz not null default now(),
    deadline_at  timestamptz,
    finished_at  timestamptz,
    status       text not null default 'in_progress'
                 constraint quiz_runs_status_check check (status in ('in_progress', 'finished', 'expired')),
    constraint quiz_runs_closed_iff check ((finished_at is null) = (status = 'in_progress')),
    constraint quiz_runs_anonymous_official check (intern_id is not null or set_id = 'official')
);

create unique index if not exists quiz_runs_one_open_uidx
    on public.quiz_runs (profile_id, set_id)
    where status = 'in_progress';
create index if not exists quiz_runs_profile_idx on public.quiz_runs (profile_id, set_id, started_at);
create index if not exists quiz_runs_intern_idx on public.quiz_runs (intern_id, set_id, started_at);
create index if not exists quiz_runs_set_idx on public.quiz_runs (set_id);

alter table public.quiz_sets
    add column if not exists time_limit_minutes int;
alter table public.quiz_sets
    drop constraint if exists quiz_sets_time_limit_check;
alter table public.quiz_sets
    add constraint quiz_sets_time_limit_check check (
        time_limit_minutes is null or time_limit_minutes between 1 and 120
    );

alter table public.quiz_attempts
    add column if not exists run_id uuid references public.quiz_runs (id) on delete cascade;
create unique index if not exists quiz_attempts_run_question_uidx
    on public.quiz_attempts (run_id, question_id)
    where run_id is not null;

alter table public.quiz_runs enable row level security;

do $$
declare
    r text;
begin
    foreach r in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            execute format('revoke all on table public.quiz_runs from %I', r);
            execute format('revoke all on table public.quiz_sets, public.quiz_attempts from %I', r);
        end if;
    end loop;
end
$$;
