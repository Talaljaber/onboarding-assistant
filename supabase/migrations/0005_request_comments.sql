-- Dada Academy onboarding assistant: comments and files on mentor requests (P15).
--
-- Both ways: the intern answers a request ("done, here is what I learned"), the admin replies. A comment
-- has a body (0-1000 characters after trim) and/or up to 3 files (PDF, Word .docx, PNG or JPEG, 1 byte to
-- 5 MiB each; type checked by the server from extension and magic bytes). No edit, no delete, no unread
-- state: deleting the request deletes its comments and file records (cascade).
-- File bytes live in the PRIVATE Storage bucket `mentor-files` at `requests/{request_id}/{file_id}`; only the
-- server reads or writes them with the secret key, and the browser downloads them through the app's API
-- (never a public or signed URL). `request_id` is repeated on the file row for the access check.
-- Same security as 0001-0004: RLS on, no policies, nothing granted to the browser roles.
-- Idempotent: safe to apply more than once. Apply after 0004_mentor_requests.sql.

create table if not exists public.mentor_request_comments (
    id          uuid primary key default gen_random_uuid(),
    request_id  uuid not null references public.mentor_requests (id) on delete cascade,
    author      text not null
                constraint mentor_request_comments_author_check check (author in ('intern', 'admin')),
    body        text not null default ''
                constraint mentor_request_comments_body_len check (char_length(btrim(body)) <= 1000),
    created_at  timestamptz not null default now()
);

create index if not exists mentor_request_comments_request_idx
    on public.mentor_request_comments (request_id, created_at);

create table if not exists public.mentor_request_files (
    id            uuid primary key default gen_random_uuid(),
    comment_id    uuid not null references public.mentor_request_comments (id) on delete cascade,
    request_id    uuid not null references public.mentor_requests (id) on delete cascade,
    filename      text not null
                  constraint mentor_request_files_filename_len check (char_length(filename) between 1 and 120),
    content_type  text not null
                  constraint mentor_request_files_type_check check (content_type in (
                      'application/pdf',
                      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                      'image/png',
                      'image/jpeg'
                  )),
    size_bytes    integer not null
                  constraint mentor_request_files_size_check check (size_bytes between 1 and 5242880),
    sha256        text not null
                  constraint mentor_request_files_sha256_shape check (sha256 ~ '^[0-9a-f]{64}$'),
    storage_key   text not null,
    created_at    timestamptz not null default now()
);

create index if not exists mentor_request_files_comment_idx on public.mentor_request_files (comment_id);
create index if not exists mentor_request_files_request_idx on public.mentor_request_files (request_id);

alter table public.mentor_request_comments enable row level security;
alter table public.mentor_request_files enable row level security;

do $$
declare
    r text;
    t text;
begin
    foreach r in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            foreach t in array array['mentor_request_comments', 'mentor_request_files'] loop
                execute format('revoke all on table public.%I from %I', t, r);
            end loop;
        end if;
    end loop;
end
$$;

-- The private bucket for the file bytes (no storage policies: only the secret key can read or write).
insert into storage.buckets (id, name, public) values ('mentor-files', 'mentor-files', false)
on conflict (id) do nothing;
