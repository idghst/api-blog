"""Pseudonymous visitor identity for view counting."""

import hashlib
import hmac

from fastapi import Request

from app.core.config import Settings


def visitor_hash(secret: str, raw: str) -> str:
    """HMAC 해싱한 방문자 키. 원문(IP·User-Agent·visitorId)은 저장하지 않는다.

    IPv4 주소 공간은 좁아 salt 없는 해시는 전수 대입으로 역산된다. 그래서 서버
    시크릿을 키로 쓴 HMAC을 사용한다.
    """

    return hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()


def client_address(request: Request) -> str:
    """프록시 뒤의 실제 클라이언트 IP. Vercel은 x-forwarded-for 맨 앞에 넣는다."""

    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip()
    if first:
        return first
    return request.client.host if request.client is not None else ""


def resolve_visitor(
    settings: Settings, request: Request, visitor_id: str | None
) -> str | None:
    """방문자 키를 만든다. 식별할 근거가 없으면 None을 반환해 기록을 건너뛴다.

    클라이언트가 보관하는 visitorId가 있으면 그것을 쓴다. 없으면 IP와
    User-Agent 조합으로 대체한다. 두 공간이 섞이지 않도록 접두사를 붙인다.
    """

    secret = settings.view_hash_secret()
    if secret is None:
        return None
    if visitor_id:
        return visitor_hash(secret, f"v:{visitor_id}")
    address = client_address(request)
    if not address:
        return None
    agent = request.headers.get("user-agent", "").strip()
    return visitor_hash(secret, f"f:{address}|{agent}")
