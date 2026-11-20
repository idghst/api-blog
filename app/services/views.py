from datetime import datetime, timedelta, timezone

from app.schemas import PostViewOut
from app.services.db import Db, fetch
from app.services.posts import published_post_id, view_total

# KST는 서머타임이 없으므로 고정 오프셋으로 충분하다. tzdata가 없는 런타임에서도 동작한다.
KST = timezone(timedelta(hours=9))


async def record_view(conn: Db, slug: str, *, visitor: str | None) -> PostViewOut:
    """조회 1건을 기록한다. 같은 방문자가 같은 날 다시 열면 중복으로 무시된다.

    visitor가 None이면 식별할 근거가 없다는 뜻이라 기록하지 않는다. 정체를 모르는
    요청을 한 명으로 합치면 조회수가 사실과 달라진다.
    """

    post_id = await published_post_id(conn, slug)
    counted = False
    if visitor is not None:
        rows = await fetch(
            conn,
            "insert into blog.post_views (post_id, visitor, viewed_on)"
            " values (%s, %s, %s)"
            " on conflict (post_id, visitor, viewed_on) do nothing returning post_id",
            (post_id, visitor, datetime.now(KST).date()),
        )
        counted = bool(rows)
    return PostViewOut(
        slug=slug,
        view_count=await view_total(conn, post_id),
        counted=counted,
    )
