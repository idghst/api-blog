create table if not exists blog.post_views (
    post_id    bigint      not null,
    visitor    text        not null,
    viewed_on  date        not null,
    created_at timestamptz not null default now(),
    constraint post_views_pkey primary key (post_id, visitor, viewed_on),
    constraint post_views_post_id_fkey
        foreign key (post_id) references blog.posts (id) on delete cascade,
    constraint post_views_visitor_len check (char_length(visitor) between 1 and 128)
);

create index if not exists post_views_post_viewed_idx
    on blog.post_views (post_id, viewed_on desc);

create table if not exists blog.post_view_counts (
    post_id bigint not null,
    total   bigint not null default 0,
    constraint post_view_counts_pkey primary key (post_id),
    constraint post_view_counts_post_id_fkey
        foreign key (post_id) references blog.posts (id) on delete cascade,
    constraint post_view_counts_total_nonneg check (total >= 0)
);

-- 조회 1건이 실제로 기록될 때만 합계를 올린다. 같은 트랜잭션에서 원자적으로 증가하므로
-- 동시 요청이 서로의 증가분을 덮어쓰지 않는다.
create or replace function blog.bump_post_view_count()
returns trigger
language plpgsql
set search_path = pg_catalog
as $$
begin
    insert into blog.post_view_counts (post_id, total)
    values (new.post_id, 1)
    on conflict (post_id)
        do update set total = post_view_counts.total + 1;
    return new;
end;
$$;

drop trigger if exists post_views_bump_count on blog.post_views;
create trigger post_views_bump_count
    after insert on blog.post_views
    for each row
    execute function blog.bump_post_view_count();

alter table blog.post_views enable row level security;
alter table blog.post_view_counts enable row level security;

revoke all privileges on table blog.post_views from anon, authenticated;
revoke all privileges on table blog.post_view_counts from anon, authenticated;
grant select, insert, delete on table blog.post_views to service_role;
grant select, insert, update, delete on table blog.post_view_counts to service_role;
