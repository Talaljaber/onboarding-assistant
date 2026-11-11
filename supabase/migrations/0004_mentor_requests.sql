-- Dada Academy onboarding assistant: mentor requests (P13.2).
--
-- Text-only "learn this / do this / read this" requests from the admin (the mentor) to one intern. No files,
-- no replies, no event history: one row per request and intern (a request for a whole track is stored as
-- one row per active intern of that track). A request may link one K-row id and one plan activity id; the
-- server checks both against the live KB and the intern's plan before writing. The intern moves the status
-- new -> in_progress -> done (and back). Status is a to-do marker, never a score.
-- Same security as 0001-0003: RLS on, no policies, nothing granted to the browser roles.
-- Idempotent: safe to apply more than once. Apply after 0003_kb_imports.sql.

create table if not exists public.mentor_requests (
    id                uuid primary key default gen_random_uuid(),
    intern_id         uuid not null references public.interns (id) on delete cascade,
    title             text not null
                      constraint mentor_requests_title_len check (char_length(btrim(title)) between 1 and 120),
    note              text not null default ''
                      constraint mentor_requests_note_len check (char_length(note) <= 1000),
    kind              text not null
                      constraint mentor_requests_kind_check check (kind in ('learn', 'do', 'read')),
    kb_id             text
                      constraint mentor_requests_kb_id_shape check (kb_id is null or kb_id ~ '^K[0-9]{2,3}$'),
    activity_id       text
                      constraint mentor_requests_activity_id_shape check (
                          activity_id is null or activity_id ~ '^[A-Z]{1,2}-[A-Za-z0-9-]{1,32}$'
                      ),
    due_date          date,
    status            text not null default 'new'
                      constraint mentor_requests_status_check check (status in ('new', 'in_progress', 'done')),
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    status_changed_at timestamptz not null default now()
);

create index if not exists mentor_requests_intern_idx on public.mentor_requests (intern_id, created_at desc);
create index if not exists mentor_requests_status_idx on public.mentor_requests (status);

alter table public.mentor_requests enable row level security;

do $$
declare
    r text;
begin
    foreach r in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            execute format('revoke all on table public.mentor_requests from %I', r);
        end if;
    end loop;
end
$$;
