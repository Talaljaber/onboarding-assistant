-- Dada Academy onboarding assistant: private answers to interns' questions (P18.5).
--
-- Some questions are personal: the answer depends on that intern, so it must not become a K-row for everyone.
-- The admin can now answer a question either with a new K-row (`answer_row_id`, as in 0006) or with a reply to
-- that intern only (`answer_text`: stored on the question row, shown only to that intern and the admin, never
-- added to the knowledge base, the index, the assistant's prompts or the turn log). An answered question has
-- exactly one of the two; an open or dismissed question has neither.
-- Same security as 0001-0007: RLS on, no policies, nothing granted to the browser roles (unchanged here).
-- Idempotent: safe to apply more than once. Apply after 0006_questions.sql (and 0007_email.sql).

alter table public.mentor_questions
    add column if not exists answer_text text;

alter table public.mentor_questions
    drop constraint if exists mentor_questions_answer_text_len;
alter table public.mentor_questions
    add constraint mentor_questions_answer_text_len check (
        answer_text is null or char_length(btrim(answer_text)) between 1 and 600
    );

alter table public.mentor_questions
    drop constraint if exists mentor_questions_answered_has_row;
alter table public.mentor_questions
    drop constraint if exists mentor_questions_answered_has_one_answer;
alter table public.mentor_questions
    add constraint mentor_questions_answered_has_one_answer check (
        case when status = 'answered'
             then (answer_row_id is not null) <> (answer_text is not null)
             else answer_row_id is null and answer_text is null
        end
    );
