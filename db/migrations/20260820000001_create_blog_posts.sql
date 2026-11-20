create or replace function blog.set_updated_at()
returns trigger
language plpgsql
set search_path = pg_catalog
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create table if not exists blog.posts (
    id           bigint      generated always as identity,
    slug         text        not null,
    title        text        not null,
    description  text        not null default '',
    type         text        not null,
    tags         text[]      not null default '{}',
    body         text        not null,
    ticker       text,
    cover        text,
    locale       text        not null default 'ko',
    draft        boolean     not null default false,
    published_at timestamptz,
    updated_at   timestamptz not null default now(),
    created_at   timestamptz not null default now(),
    constraint posts_pkey primary key (id),
    constraint posts_slug_key unique (slug),
    constraint posts_type_check check (type in ('guide', 'news', 'stock')),
    constraint posts_locale_check check (locale in ('ko', 'en'))
);

create index if not exists posts_type_published_idx
    on blog.posts (type, published_at desc);

create index if not exists posts_published_idx
    on blog.posts (published_at desc)
    where draft = false;

create index if not exists posts_tags_gin_idx
    on blog.posts using gin (tags);

drop trigger if exists posts_set_updated_at on blog.posts;
create trigger posts_set_updated_at
    before update on blog.posts
    for each row
    execute function blog.set_updated_at();

alter table blog.posts enable row level security;

revoke usage on schema blog from anon, authenticated;
grant usage on schema blog to service_role;
revoke all privileges on table blog.posts from anon, authenticated;
grant select, insert, update, delete on table blog.posts to service_role;
grant usage, select on sequence blog.posts_id_seq to service_role;
