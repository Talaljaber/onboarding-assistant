-- Dada Academy onboarding assistant: practice quizzes written by the admin (P20).
--
-- `quiz_sets`: a named set (Arabic title, optional English title), its audience (everyone, one track, or chosen
-- interns), the suggested-plan progress at which it opens for the intern (0-100 %), draft/published, and its
-- mode: `practice` (results stay with the intern) or `checkpoint` (D-P20-checkpoint: each intern's FIRST answer
-- per question is shown to the admin; the intern is told before starting). The official sample quiz is not a
-- row here: it is the built-in set `official` (always open, always practice).
-- `quiz_set_items`: up to 20 questions per set, ids `M001`, `M002`, ... (an id held by an item or an attempt is
-- never handed out again, so an old attempt never counts for a new question), each citing one K-row; the server checks every question against the cited row
-- (numbers, contacts, lengths) before writing. Attempts stay in `quiz_attempts` (0001; `question_id` now also
-- holds `M\d{3}`): deleting a set or an item keeps them.
-- `mentor_questions.source` gains `quiz` (the intern's «اسأل مشرفي عن هذا» after a wrong practice answer).
-- Same security as 0001-0008: RLS on, no policies, nothing granted to the browser roles.
-- Idempotent: safe to apply more than once. Apply after 0008_private_answers.sql.

create table if not exists public.quiz_sets (
    id                uuid primary key default gen_random_uuid(),
    title_ar          text not null
                      constraint quiz_sets_title_ar_len check (char_length(btrim(title_ar)) between 1 and 80),
    title_en          text
                      constraint quiz_sets_title_en_len check (
                          title_en is null or char_length(btrim(title_en)) between 1 and 80
                      ),
    audience          text not null
                      constraint quiz_sets_audience_check check (audience in ('all', 'track', 'interns')),
    track             text
                      constraint quiz_sets_track_check check (track is null or track in ('Sales', 'Delivery')),
    intern_ids        uuid[] not null default '{}',
    opens_at_percent  int not null default 0
                      constraint quiz_sets_opens_check check (opens_at_percent between 0 and 100),
    status            text not null default 'draft'
                      constraint quiz_sets_status_check check (status in ('draft', 'published')),
    mode              text not null default 'practice'
                      constraint quiz_sets_mode_check check (mode in ('practice', 'checkpoint')),
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    constraint quiz_sets_track_iff check ((track is not null) = (audience = 'track')),
    constraint quiz_sets_interns_iff check ((cardinality(intern_ids) > 0) = (audience = 'interns'))
);

-- A project that ran an earlier draft of this file without `mode`.
alter table public.quiz_sets
    add column if not exists mode text not null default 'practice';
alter table public.quiz_sets
    drop constraint if exists quiz_sets_mode_check;
alter table public.quiz_sets
    add constraint quiz_sets_mode_check check (mode in ('practice', 'checkpoint'));

create index if not exists quiz_sets_created_idx on public.quiz_sets (created_at desc);

create table if not exists public.quiz_set_items (
    id                   text primary key
                         constraint quiz_set_items_id_shape check (id ~ '^M[0-9]{3}$'),
    set_id               uuid not null references public.quiz_sets (id) on delete cascade,
    position             int not null constraint quiz_set_items_position_check check (position >= 0),
    question_ar          text not null
                         constraint quiz_set_items_question_len check (char_length(btrim(question_ar)) between 1 and 300),
    option_a             text not null
                         constraint quiz_set_items_a_len check (char_length(btrim(option_a)) between 1 and 120),
    option_b             text not null
                         constraint quiz_set_items_b_len check (char_length(btrim(option_b)) between 1 and 120),
    option_c             text not null
                         constraint quiz_set_items_c_len check (char_length(btrim(option_c)) between 1 and 120),
    correct_option       text not null
                         constraint quiz_set_items_correct_check check (correct_option in ('A', 'B', 'C')),
    source_knowledge_id  text not null
                         constraint quiz_set_items_row_shape check (source_knowledge_id ~ '^K[0-9]{2,3}$'),
    origin               text not null default 'manual'
                         constraint quiz_set_items_origin_check check (origin in ('manual', 'model', 'csv')),
    created_at           timestamptz not null default now()
);

create index if not exists quiz_set_items_set_idx on public.quiz_set_items (set_id, position);
create index if not exists quiz_attempts_question_idx on public.quiz_attempts (question_id);

-- The questions inbox accepts questions sent from a practice quiz.
alter table public.mentor_questions
    drop constraint if exists mentor_questions_source_check;
alter table public.mentor_questions
    add constraint mentor_questions_source_check check (source in ('check', 'chat', 'quiz'));

alter table public.quiz_sets      enable row level security;
alter table public.quiz_set_items enable row level security;

do $$
declare
    r text;
begin
    foreach r in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            execute format('revoke all on table public.quiz_sets, public.quiz_set_items from %I', r);
        end if;
    end loop;
end
$$;
