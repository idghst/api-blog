-- API 전용 최소 권한 롤 blog_app. 슈퍼유저로 blog DB에서 한 번 실행한다(다시 실행해도 된다).
--   docker exec -i -u postgres postgres psql -v ON_ERROR_STOP=1 -d blog < db/blog_app_role.sql
--   docker exec -it -u postgres postgres psql -d blog -c '\password blog_app'
-- 테이블은 RLS가 켜져 있고 blog_app은 소유자가 아니므로 정책이 있어야 행이 보인다.

do $$
begin
    if not exists (select from pg_roles where rolname = 'blog_app') then
        create role blog_app login;
    end if;
end
$$;

alter role blog_app nosuperuser nocreatedb nocreaterole noinherit nobypassrls;

grant connect on database blog to blog_app;
grant usage on schema blog to blog_app;

-- API가 실제로 하는 일만: 글 CRUD, 댓글·그림 읽기/쓰기, 조회 기록.
grant select, insert, update, delete on blog.posts to blog_app;
grant select, insert on blog.comments to blog_app;
grant select, insert on blog.blobs to blog_app;
grant select, insert on blog.post_views to blog_app;
-- post_views insert 트리거가 호출자 권한으로 합계를 올린다.
grant select, insert, update on blog.post_view_counts to blog_app;

drop policy if exists blog_app_access on blog.posts;
create policy blog_app_access on blog.posts to blog_app using (true) with check (true);
drop policy if exists blog_app_access on blog.comments;
create policy blog_app_access on blog.comments to blog_app using (true) with check (true);
drop policy if exists blog_app_access on blog.blobs;
create policy blog_app_access on blog.blobs to blog_app using (true) with check (true);
drop policy if exists blog_app_access on blog.post_views;
create policy blog_app_access on blog.post_views to blog_app using (true) with check (true);
drop policy if exists blog_app_access on blog.post_view_counts;
create policy blog_app_access on blog.post_view_counts to blog_app using (true) with check (true);
