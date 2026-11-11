-- Dada Academy onboarding assistant: interns managed by the admin (P11.2).
--
-- Adds an `interns` table (the admin adds, renames, re-tracks and deactivates interns at runtime) and
-- links each profile to its intern. One profile per (intern, track): a track change by the admin starts
-- a new profile and keeps the old one as history. Profiles without an intern are the old anonymous
-- demo profiles (scripts/purge_demo_profiles.py removes them). Names are fictional demo personas.
-- Same security as 0001: RLS on, no policies, nothing granted to the browser roles.
-- Idempotent: safe to apply more than once. Apply after 0001_init.sql.

create table if not exists public.interns (
    id         uuid primary key default gen_random_uuid(),
    name_ar    text not null
               constraint interns_name_ar_shape check (
                   char_length(btrim(name_ar)) between 2 and 40
                   and name_ar !~ '[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+'
                   and char_length(regexp_replace(name_ar, '[^0-9٠-٩۰-۹]', '', 'g')) < 7
               ),
    name_en    text
               constraint interns_name_en_shape check (
                   name_en is null or (
                       char_length(btrim(name_en)) between 2 and 40
                       and name_en !~ '[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+'
                       and char_length(regexp_replace(name_en, '[^0-9٠-٩۰-۹]', '', 'g')) < 7
                   )
               ),
    role       text not null
               constraint interns_role_check check (role in ('Sales', 'Delivery')),
    active     boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists interns_created_idx on public.interns (created_at);

alter table public.profiles
    add column if not exists intern_id uuid references public.interns (id) on delete restrict;

-- One profile per intern and track (the server's get-or-create relies on it).
create unique index if not exists profiles_intern_role_uidx
    on public.profiles (intern_id, role) where intern_id is not null;

alter table public.interns enable row level security;

do $$
declare
    r text;
begin
    foreach r in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            execute format('revoke all on table public.interns from %I', r);
        end if;
    end loop;
end
$$;
