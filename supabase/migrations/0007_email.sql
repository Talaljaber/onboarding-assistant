-- Dada Academy onboarding assistant: email notifications (P18.2).
--
-- `interns.email`: where an intern's notifications go (optional, entered by the admin in the add/edit intern
-- form; one address, checked by the server before it is written).
-- `mail_log`: one row per email the server sent, failed to send or skipped (SMTP not configured, OFFLINE=1, no
-- address). `error` is a short code such as `auth_failed`: never an SMTP reply, a password or a key.
-- Bodies and attachments are not stored here (they are the request, comment or question rows already stored).
-- Same security as 0001-0005: RLS on, no policies, nothing granted to the browser roles.
-- Idempotent: safe to apply more than once. Apply after 0005_request_comments.sql (and 0006 if present).

alter table public.interns
    add column if not exists email text
        constraint interns_email_shape check (
            email is null or (
                char_length(email) <= 254
                and email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'
            )
        );

create table if not exists public.mail_log (
    id          uuid primary key default gen_random_uuid(),
    event       text not null
                constraint mail_log_event_check check (event in (
                    'request_created', 'admin_comment', 'intern_comment', 'request_done',
                    'question_submitted', 'question_answered', 'test'
                )),
    to_addr     text not null default ''
                constraint mail_log_to_len check (char_length(to_addr) <= 254),
    subject     text not null
                constraint mail_log_subject_len check (char_length(subject) between 1 and 200),
    status      text not null
                constraint mail_log_status_check check (status in ('sent', 'failed', 'skipped')),
    error       text
                constraint mail_log_error_shape check (error is null or error ~ '^[a-z_]{1,40}$'),
    created_at  timestamptz not null default now()
);

create index if not exists mail_log_created_idx on public.mail_log (created_at desc);

alter table public.mail_log enable row level security;

do $$
declare
    r text;
begin
    foreach r in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            execute format('revoke all on table public.mail_log from %I', r);
        end if;
    end loop;
end
$$;
