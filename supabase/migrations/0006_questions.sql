-- Dada Academy onboarding assistant: questions inbox (P18.1).
--
-- A question the intern CHOSE to send to the mentor (the Rumour Check found no confirming row, or the
-- assistant could not answer in chat). Stored only on the intern's explicit Send, with exactly the text they
-- saw and could edit (1-600 characters). The admin answers it once with a new K-row (status `added`, through
-- the KB editor's add path; `answer_row_id` is that row's id) or dismisses it. No score, no history.
-- Same security as 0001-0005: RLS on, no policies, nothing granted to the browser roles.
-- Idempotent: safe to apply more than once. Apply after 0005_request_comments.sql.

create table if not exists public.mentor_questions (
    id             uuid primary key default gen_random_uuid(),
    intern_id      uuid not null references public.interns (id) on delete cascade,
    source         text not null
                   constraint mentor_questions_source_check check (source in ('check', 'chat')),
    text           text not null
                   constraint mentor_questions_text_len check (char_length(btrim(text)) between 1 and 600),
    status         text not null default 'open'
                   constraint mentor_questions_status_check check (status in ('open', 'answered', 'dismissed')),
    answer_row_id  text
                   constraint mentor_questions_answer_row_shape check (
                       answer_row_id is null or answer_row_id ~ '^K[0-9]{2,3}$'
                   ),
    created_at     timestamptz not null default now(),
    answered_at    timestamptz,
    constraint mentor_questions_answered_has_row check ((status = 'answered') = (answer_row_id is not null))
);

create index if not exists mentor_questions_intern_idx on public.mentor_questions (intern_id, created_at desc);
create index if not exists mentor_questions_status_idx on public.mentor_questions (status);

alter table public.mentor_questions enable row level security;

do $$
declare
    r text;
begin
    foreach r in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            execute format('revoke all on table public.mentor_questions from %I', r);
        end if;
    end loop;
end
$$;
