create table if not exists blog.comments (
    id         bigint      generated always as identity,
    post_id    bigint      not null,
    author     text        not null,
    body       text        not null,
    created_at timestamptz not null default now(),
    constraint comments_pkey primary key (id),
    constraint comments_post_id_fkey
        foreign key (post_id) references blog.posts (id) on delete cascade,
    constraint comments_author_len check (char_length(author) between 1 and 80),
    constraint comments_body_len check (char_length(body) between 1 and 2000)
);

create index if not exists comments_post_created_idx
    on blog.comments (post_id, created_at);

create table if not exists blog.blobs (
    id          uuid        primary key default gen_random_uuid(),
    description text        not null,
    mime_type   text        not null,
    bytes       bytea       not null,
    created_at  timestamptz not null default now(),
    constraint blobs_description_len check (char_length(description) between 1 and 500),
    constraint blobs_mime_type_check
        check (mime_type in ('image/png', 'image/jpeg', 'image/webp', 'image/gif')),
    constraint blobs_bytes_len check (octet_length(bytes) between 1 and 2000000)
);

alter table blog.comments enable row level security;
alter table blog.blobs enable row level security;

revoke all privileges on table blog.comments from anon, authenticated;
revoke all privileges on table blog.blobs from anon, authenticated;
grant select, insert, update, delete on table blog.comments to service_role;
grant select, insert, update, delete on table blog.blobs to service_role;
grant usage, select on sequence blog.comments_id_seq to service_role;
