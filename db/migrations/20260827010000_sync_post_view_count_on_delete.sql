-- post_views 행을 지우면 합계는 그대로 남아 조회수가 영구히 과대 집계된다. service_role은
-- post_views에 delete 권한이 있으므로(오래된 기록 정리, 검증 흔적 제거) 감소도 트리거로
-- 보장한다. total >= 0 제약을 깨지 않도록 0에서 멈춘다.
create or replace function blog.drop_post_view_count()
returns trigger
language plpgsql
set search_path = pg_catalog
as $$
begin
    update blog.post_view_counts
       set total = greatest(total - 1, 0)
     where post_id = old.post_id;
    return old;
end;
$$;

drop trigger if exists post_views_drop_count on blog.post_views;
create trigger post_views_drop_count
    after delete on blog.post_views
    for each row
    execute function blog.drop_post_view_count();
