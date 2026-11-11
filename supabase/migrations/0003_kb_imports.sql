-- Dada Academy onboarding assistant: document import for the knowledge editor (P12.1).
--
-- The admin uploads a document; the server extracts its text in memory and stores only the passages as
-- drafts here (the original file is never stored). A draft becomes answerable only when the admin
-- approves it: it is then added to kb_rows as a normal K-row (status 'added', history source 'editor')
-- and `row_id` points at it. KB reset removes those rows and puts the drafts back to 'draft'.
-- Same security as 0001/0002: RLS on, no policies, nothing granted to the browser roles.
-- Idempotent: safe to apply more than once. Apply after 0002_interns.sql.

create table if not exists public.kb_imports (
    id            uuid primary key default gen_random_uuid(),
    filename      text not null
                  constraint kb_imports_filename_len check (char_length(btrim(filename)) between 1 and 120),
    document_name text not null
                  constraint kb_imports_document_len check (char_length(btrim(document_name)) between 1 and 80),
    file_type     text not null
                  constraint kb_imports_file_type_check check (file_type in ('txt', 'md', 'csv', 'docx', 'pdf')),
    pages         int not null default 0 constraint kb_imports_pages_check check (pages >= 0),
    passages      int not null default 0 constraint kb_imports_passages_check check (passages between 0 and 200),
    organized     boolean not null default false,
    status        text not null default 'open'
                  constraint kb_imports_status_check check (status in ('open', 'done')),
    created_at    timestamptz not null default now()
);

create index if not exists kb_imports_created_idx on public.kb_imports (created_at);

create table if not exists public.kb_drafts (
    id          uuid primary key default gen_random_uuid(),
    import_id   uuid not null references public.kb_imports (id) on delete cascade,
    ord         int not null constraint kb_drafts_ord_check check (ord between 0 and 9999),
    page        int not null default 1 constraint kb_drafts_page_check check (page between 0 and 999),
    text_ar     text not null constraint kb_drafts_text_len check (char_length(btrim(text_ar)) between 5 and 600),
    topic       text not null constraint kb_drafts_topic_len check (char_length(btrim(topic)) between 1 and 40),
    keyword_en  text not null default '' constraint kb_drafts_keyword_len check (char_length(keyword_en) <= 60),
    question_ar text constraint kb_drafts_question_len check (question_ar is null or char_length(question_ar) <= 160),
    status      text not null default 'draft'
                constraint kb_drafts_status_check check (status in ('draft', 'approved', 'discarded')),
    row_id      text constraint kb_drafts_row_id_shape check (row_id is null or row_id ~ '^K[0-9]{2,3}$'),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    constraint kb_drafts_approved_has_row check ((status = 'approved') = (row_id is not null))
);

create index if not exists kb_drafts_import_idx on public.kb_drafts (import_id, ord);
create index if not exists kb_drafts_status_idx on public.kb_drafts (status);

alter table public.kb_imports enable row level security;
alter table public.kb_drafts  enable row level security;

do $$
declare
    r text;
begin
    foreach r in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            execute format('revoke all on table public.kb_imports, public.kb_drafts from %I', r);
        end if;
    end loop;
end
$$;
