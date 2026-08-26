import tomllib
from pathlib import Path

from app.schemas import PostCreate, PostOut, PostPatch

PROJECT_ROOT = Path(__file__).resolve().parents[1]

POST_COLUMNS = {
    "slug",
    "title",
    "description",
    "type",
    "tags",
    "body",
    "ticker",
    "cover",
    "locale",
    "draft",
    "published_at",
    "updated_at",
    "created_at",
}
POST_WRITABLE_COLUMNS = POST_COLUMNS - {"updated_at", "created_at"}
# 조회수는 posts 컬럼이 아니라 blog.post_view_counts에서 합쳐 넣는 파생 값이다.
POST_DERIVED_FIELDS = {"view_count"}


def test_local_supabase_project_exposes_only_blog_schema_contract() -> None:
    config = tomllib.loads(
        (PROJECT_ROOT / "supabase" / "config.toml").read_text(encoding="utf-8")
    )

    assert config["project_id"] == "fastapi-blog"
    assert config["api"]["schemas"] == ["public", "graphql_public", "blog"]


def test_blog_migration_limits_default_privileges_to_service_role() -> None:
    migrations = sorted(
        (PROJECT_ROOT / "supabase" / "migrations").glob("*_init_blog.sql")
    )

    assert len(migrations) == 1
    migration = migrations[0].read_text(encoding="utf-8")

    assert "create schema if not exists blog;" in migration
    assert (
        "grant usage on schema blog to anon, authenticated, service_role;" in migration
    )
    assert "grant all on tables to service_role;" in migration
    assert "grant all on tables to anon" not in migration
    assert "grant all on tables to authenticated" not in migration


def test_posts_migration_keeps_records_private_to_the_server() -> None:
    migrations = sorted(
        (PROJECT_ROOT / "supabase" / "migrations").glob("*_create_blog_posts.sql")
    )

    assert len(migrations) == 1
    migration = migrations[0].read_text(encoding="utf-8")

    assert "create table if not exists blog.posts" in migration
    assert "alter table blog.posts enable row level security;" in migration
    assert "revoke usage on schema blog from anon, authenticated;" in migration
    assert (
        "revoke all privileges on table blog.posts from anon, authenticated;"
        in migration
    )
    assert (
        "grant select, insert, update, delete on table blog.posts to service_role;"
        in migration
    )
    assert "constraint posts_type_check check (type in ('guide', 'news', 'stock'))" in (
        migration
    )


def test_post_schemas_match_api_contract() -> None:
    assert set(PostOut.model_fields) == POST_COLUMNS | POST_DERIVED_FIELDS
    assert set(PostCreate.model_fields) == POST_WRITABLE_COLUMNS
    assert set(PostPatch.model_fields) == POST_WRITABLE_COLUMNS


def test_post_views_migration_dedupes_and_keeps_records_private() -> None:
    migrations = sorted(
        (PROJECT_ROOT / "supabase" / "migrations").glob("*_create_post_views.sql")
    )

    assert len(migrations) == 1
    migration = migrations[0].read_text(encoding="utf-8")

    assert "create table if not exists blog.post_views" in migration
    assert "primary key (post_id, visitor, viewed_on)" in migration
    assert "create table if not exists blog.post_view_counts" in migration
    assert "alter table blog.post_views enable row level security;" in migration
    assert "alter table blog.post_view_counts enable row level security;" in migration
    assert (
        "revoke all privileges on table blog.post_views from anon, authenticated;"
        in migration
    )
    assert (
        "revoke all privileges on table blog.post_view_counts"
        " from anon, authenticated;" in migration
    )
    assert "after insert on blog.post_views" in migration
    assert "do update set total = post_view_counts.total + 1" in migration


def test_post_out_ignores_unknown_store_columns() -> None:
    record = PostOut.model_validate(
        {
            "id": 99,
            "slug": "hello-world",
            "title": "Hello",
            "description": "",
            "type": "news",
            "tags": [],
            "body": "body",
            "locale": "en",
            "draft": False,
            "published_at": "2026-08-01T00:00:00+00:00",
            "updated_at": "2026-08-02T00:00:00+00:00",
            "created_at": "2026-08-01T00:00:00+00:00",
            "unknown_column": "ignored",
        }
    )

    assert record.slug == "hello-world"
    assert "unknown_column" not in PostOut.model_fields
    assert "id" not in PostOut.model_fields
