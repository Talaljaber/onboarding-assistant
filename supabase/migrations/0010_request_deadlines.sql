-- Dada Academy onboarding assistant: task deadlines and reminder emails (P21.1).
--
-- `mentor_requests.due_at`: the deadline the admin set (a date and a time). A request that only had a `due_date`
-- (0004) gets 23:59 Asia/Amman of that day; the server keeps `due_date` as the Amman day of `due_at`.
-- `mentor_requests.done_at`: when the intern marked the request done (cleared when it is reopened); a request
-- already done gets its `status_changed_at`. The server compares it with `due_at` (done on time / done late).
-- `mentor_requests.reminder_sent_at`: when the server claimed the request's reminder email (set once, before the
-- email is queued, only while still null: two servers or a restart never send twice); a new deadline clears it.
-- `mail_log.event` may now also be `request_reminder` (the check constraint of 0007, re-created with every
-- earlier event kept). These are task facts for the admin, never a score.
-- Same security as 0001-0008: RLS on, no policies, nothing granted to the browser roles (no new table here).
-- Idempotent: safe to apply more than once. Apply after 0007_email.sql (and 0008 / 0009 if present).

alter table public.mentor_requests
    add column if not exists due_at timestamptz;
alter table public.mentor_requests
    add column if not exists done_at timestamptz;
alter table public.mentor_requests
    add column if not exists reminder_sent_at timestamptz;

update public.mentor_requests
   set due_at = (due_date::timestamp + interval '23 hours 59 minutes') at time zone 'Asia/Amman'
 where due_at is null
   and due_date is not null;

update public.mentor_requests
   set done_at = status_changed_at
 where status = 'done'
   and done_at is null;

-- The reminder check (every 30 s): open requests with a deadline and no reminder yet.
create index if not exists mentor_requests_reminder_idx
    on public.mentor_requests (due_at)
    where reminder_sent_at is null and status <> 'done';

alter table public.mail_log
    drop constraint if exists mail_log_event_check;
alter table public.mail_log
    add constraint mail_log_event_check check (event in (
        'request_created', 'admin_comment', 'intern_comment', 'request_done',
        'question_submitted', 'question_answered', 'test', 'request_reminder'
    ));

do $$
declare
    r text;
begin
    foreach r in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            execute format('revoke all on table public.mentor_requests from %I', r);
            execute format('revoke all on table public.mail_log from %I', r);
        end if;
    end loop;
end
$$;
