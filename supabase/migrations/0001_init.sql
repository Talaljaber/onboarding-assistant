-- Dada Academy onboarding assistant: initial schema (plan §A12.2).
--
-- Stores the live knowledge base and its history, demo profiles (aliases only), progress,
-- practice attempts and turn logs. No chat text, no answer text and no free-text replies are
-- stored anywhere. Row level security is enabled on every table with NO policies: the browser
-- keys (anon / authenticated) can neither read nor write; only the server's secret key can.
-- Idempotent: safe to apply more than once. No pgvector (embeddings are computed in-process).

-- Knowledge base ------------------------------------------------------------------------------

create table if not exists public.kb_rows (
    id              text primary key
                    constraint kb_rows_id_format check (id ~ '^K\d{2,3}$'),
    topic           text not null check (char_length(topic) between 1 and 200),
    answer_ar       text not null check (char_length(answer_ar) between 1 and 4000),
    keyword_en      text not null default '' check (char_length(keyword_en) <= 400),
    source_document text not null default '' check (char_length(source_document) <= 200),
    source_page     int check (source_page is null or source_page >= 0),
    status          text not null default 'official'
                    constraint kb_rows_status_check check (status in ('official', 'edited', 'added')),
    version         int not null default 1 check (version >= 1),
    updated_at      timestamptz not null default now()
);

create table if not exists public.kb_row_history (
    id         bigserial primary key,
    row_id     text not null check (row_id ~ '^K\d{2,3}$'),
    before     jsonb,
    after      jsonb,
    source     text not null
               constraint kb_row_history_source_check check (source in ('seed', 'editor', 'reset')),
    changed_at timestamptz not null default now()
);

create index if not exists kb_row_history_row_idx on public.kb_row_history (row_id, changed_at);

-- Demo profiles (aliases only, never real names or contacts) -----------------------------------

create table if not exists public.profiles (
    id         uuid primary key default gen_random_uuid(),
    alias      text not null
               constraint profiles_alias_shape check (
                   char_length(btrim(alias)) between 1 and 40
                   -- no email shape
                   and alias !~ '[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+'
                   -- no phone shape: at most 6 digits (ASCII, Arabic-Indic or Persian)
                   and char_length(regexp_replace(alias, '[^0-9٠-٩۰-۹]', '', 'g')) < 7
               ),
    role       text not null
               constraint profiles_role_check check (role in ('Sales', 'Delivery')),
    created_at timestamptz not null default now()
);

create index if not exists profiles_created_idx on public.profiles (created_at);

-- Progress and practice ------------------------------------------------------------------------

create table if not exists public.progress (
    profile_id   uuid not null references public.profiles (id) on delete cascade,
    activity_id  text not null check (char_length(activity_id) between 1 and 64),
    completed_at timestamptz not null default now(),
    primary key (profile_id, activity_id)
);

create table if not exists public.quiz_attempts (
    id          bigserial primary key,
    profile_id  uuid not null references public.profiles (id) on delete cascade,
    question_id text not null check (char_length(question_id) between 1 and 64),
    option      text not null check (char_length(option) between 1 and 64),
    correct     boolean not null,
    at          timestamptz not null default now()
);

create index if not exists quiz_attempts_profile_idx on public.quiz_attempts (profile_id);

create table if not exists public.scenario_attempts (
    id          bigserial primary key,
    profile_id  uuid not null references public.profiles (id) on delete cascade,
    scenario_id text not null check (char_length(scenario_id) between 1 and 64),
    mode        text not null check (char_length(mode) between 1 and 32),
    option_id   text check (option_id is null or char_length(option_id) between 1 and 64),
    met         text[] not null default '{}',
    missing     text[] not null default '{}',
    value       text check (value is null or char_length(value) <= 64),
    at          timestamptz not null default now()
);

create index if not exists scenario_attempts_profile_idx on public.scenario_attempts (profile_id);

-- Turn logs: metadata only, never the message or the answer text ------------------------------

create table if not exists public.turn_logs (
    id              bigserial primary key,
    request_id      text check (request_id is null or char_length(request_id) <= 64),
    profile_id      uuid references public.profiles (id) on delete cascade,
    at              timestamptz not null default now(),
    tool            text check (tool is null or char_length(tool) <= 64),
    mode            text check (mode is null or char_length(mode) <= 32),
    status          text check (status is null or char_length(status) <= 32),
    band            text check (band is null or char_length(band) <= 32),
    cited_ids       text[] not null default '{}',
    verifier_ok     boolean,
    verifier_reason text check (verifier_reason is null or char_length(verifier_reason) <= 120),
    latency_ms      int check (latency_ms is null or latency_ms >= 0),
    cached          boolean,
    model           text check (model is null or char_length(model) <= 120)
);

create index if not exists turn_logs_at_idx on public.turn_logs (at);
create index if not exists turn_logs_profile_idx on public.turn_logs (profile_id);

-- Security: RLS on, no policies, no grants to the browser roles --------------------------------

alter table public.kb_rows           enable row level security;
alter table public.kb_row_history    enable row level security;
alter table public.profiles          enable row level security;
alter table public.progress          enable row level security;
alter table public.quiz_attempts     enable row level security;
alter table public.scenario_attempts enable row level security;
alter table public.turn_logs         enable row level security;

do $$
declare
    r text;
begin
    foreach r in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            execute format(
                'revoke all on table public.kb_rows, public.kb_row_history, public.profiles, '
                'public.progress, public.quiz_attempts, public.scenario_attempts, public.turn_logs '
                'from %I', r);
            execute format(
                'revoke all on sequence public.kb_row_history_id_seq, public.quiz_attempts_id_seq, '
                'public.scenario_attempts_id_seq, public.turn_logs_id_seq from %I', r);
        end if;
    end loop;
end
$$;
