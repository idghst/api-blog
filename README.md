# fastapi-blog

메인 Postgres의 `blog` DB(`blog` 스키마)에 직접 연결하는 FastAPI 서비스입니다.
Supabase(PostgREST·Auth)는 쓰지 않습니다. DB에 붙는 것은 이 API뿐이고, 접속은
`DATABASE_URL`의 앱 전용 롤 `blog_app`(최소 권한)으로 합니다. 공개 GET은 발행된
(`draft=false`) `blog.posts`만 반환하고, 생성·수정·삭제는 서버 전용 `X-Blog-Key`로만
수행합니다. 프론트엔드 `idghst-blog`는 이 API만 호출하며 DB에 직접 접근하지 않습니다.

## Local development

Python 3.12와 [uv](https://docs.astral.sh/uv/)가 필요합니다.

```bash
uv sync --locked --dev
```

`.env.example`을 `.env.local`로 복사한 뒤 실제 키를 넣으세요. 실제 키는 절대
커밋하지 마세요.

```bash
uv run uvicorn app.main:app --reload
```

- API: <http://127.0.0.1:8000>
- Docs: <http://127.0.0.1:8000/docs>
- Liveness: <http://127.0.0.1:8000/health> 또는 <http://127.0.0.1:8000/health/live>
- Readiness: <http://127.0.0.1:8000/health/ready>

Vercel 런타임을 로컬에서 확인할 때는 Vercel에 연결된 프로젝트의 환경 변수를
가져온 뒤 실행합니다.

```bash
vercel dev
```

## Database setup

스키마의 원본은 `db/migrations/`입니다(Supabase 시절 migration을 그대로 옮김). 운영 DB에는
이미 적용되어 있으므로 새 migration만 순서대로 `blog_owner`로 적용합니다.

API 전용 롤은 `db/blog_app_role.sql`로 만듭니다. 슈퍼유저로 한 번 실행하며 다시 실행해도
됩니다. 권한은 API가 실제로 하는 일(글 CRUD, 댓글·그림 읽기/쓰기, 조회 기록)만 주고,
테이블 RLS가 켜져 있으므로 `blog_app` 전용 정책도 함께 만듭니다.

```bash
docker exec -i -u postgres postgres psql -v ON_ERROR_STOP=1 -d blog < db/blog_app_role.sql
docker exec -it -u postgres postgres psql -d blog -c '\password blog_app'
```

그다음 API가 붙는 네트워크에서 `blog_app`만 받도록 `pg_hba.conf`에 줄을 넣고 다시
읽게 합니다(`데이터베이스/README.md`의 "접근 정책" 참고).

```text
host blog blog_app <API 네트워크 서브넷> scram-sha-256
```

### Supabase 환경 변수에서 옮기기

기존 `.env`·`.env.local`·Vercel 환경 변수의 `SUPABASE_*` 값은 더 읽지 않습니다. 지우기
전에 아래를 먼저 옮깁니다.

1. `DATABASE_URL=postgresql://blog_app:<비밀번호>@<호스트>:5432/blog`를 넣습니다.
2. `VIEW_HASH_SALT`가 비어 있었다면 기존 `SUPABASE_SECRET_KEY` 값을 `VIEW_HASH_SALT`로
   옮깁니다. 예전에는 비어 있으면 secret key로 대체했습니다. 옮기지 않으면 조회가 기록되지
   않고(`counted: false`), 다른 값을 넣으면 그날의 중복 제거가 한 번 풀립니다.
3. 새 버전이 정상 동작하면 `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`,
   `SUPABASE_SECRET_KEY`, `SUPABASE_TEST_*`를 지우고 Supabase 키를 폐기합니다.

## Posts API

공개 목록/상세는 키 없이 호출합니다. `includeDrafts=true`와 쓰기 요청은 아래 헤더가
필요합니다. 서버에 `BLOG_API_KEY`가 없으면 그 요청은 `503`, 키가 틀리거나 없으면 동일한
`401` 오류를 반환합니다. DB에 붙지 못하면 `503 database_unavailable`입니다.

```http
X-Blog-Key: <BLOG_API_KEY>
```

| Method | Path | Auth | Result |
| --- | --- | --- | --- |
| `GET` | `/api/posts` | 공개. `includeDrafts`는 키 필요 | `{ "items": [...], "count": n }` |
| `GET` | `/api/posts/{slug}` | 공개. draft는 키 없이 404 | 단건 |
| `POST` | `/api/posts` | `X-Blog-Key` | 생성된 레코드 (`201`) |
| `PATCH` | `/api/posts/{slug}` | `X-Blog-Key` | 변경된 레코드 |
| `DELETE` | `/api/posts/{slug}` | `X-Blog-Key` | `204 No Content` |
| `POST` | `/api/posts/{slug}/view` | 공개 | `{ slug, viewCount, counted }` |
| `GET` | `/api/posts/{slug}/comments` | 공개 | `{ "items": [...], "count": n }` |
| `POST` | `/api/posts/{slug}/comments` | 공개 | 생성된 댓글 (`201`) |
| `POST` | `/api/blobs` | `X-Blog-Key` | `{ id, description, mimeType, createdAt }` |
| `GET` | `/api/blobs/{id}` | 공개 | 이미지 바이트 |
| `GET` | `/api/blobs/{id}/meta` | 공개 | `{ id, description, mimeType, createdAt }` |

댓글은 `author`, `body`. 본문 그림은 `![설명](blob:<uuid>)`.

## Post views

목록과 상세 응답에 `viewCount`가 있습니다. 값은 `blog.post_view_counts`에서 가져오며
`blog.posts` 컬럼이 아닙니다. 목록은 페이지 전체 조회수를 한 번의 질의로 합칩니다.

조회 기록은 `POST /api/posts/{slug}/view`입니다. 발행된 글만 받고 draft와 없는 slug는
`404`입니다. 응답의 `counted`는 이 요청이 실제로 1건으로 집계됐는지를 알려줍니다.

```http
POST /api/posts/hello-world/view
Content-Type: application/json

{ "visitorId": "<클라이언트가 보관하는 UUID>" }
```

중복 제거는 `blog.post_views`의 `(post_id, visitor, viewed_on)` 복합 PK로 합니다. 같은
방문자가 같은 날 몇 번 새로고침해도 1건입니다. `viewed_on`은 KST 날짜이므로 하루가
바뀌면 다시 1건 집계됩니다. 합계는 insert trigger가 같은 트랜잭션에서 올리므로 동시
요청이 서로의 증가분을 덮어쓰지 않습니다.

`blog.post_view_counts.total`은 `blog.post_views` 행 수의 파생 값입니다. 두 트리거가
양방향을 맞추므로 SQL로 `post_views`를 직접 지워도 합계가 따라 내려갑니다. 합계를
손으로 고치지 마세요. 어긋났다고 판단되면 행 수로 다시 계산합니다.

```sql
update blog.post_view_counts c
   set total = (select count(*) from blog.post_views v where v.post_id = c.post_id);
```

`visitor`는 원문을 저장하지 않습니다. `visitorId`가 오면 그 값을, 없으면 클라이언트
IP와 User-Agent 조합을 서버 시크릿 키로 HMAC-SHA256 해싱해 넣습니다. IPv4는 주소
공간이 좁아 salt 없는 해시가 전수 대입으로 역산되기 때문입니다. 키는
`VIEW_HASH_SALT`이며 없으면 조회를 기록하지 않습니다. 식별할 근거가 전혀
없으면(`visitorId`도 IP도 없음) 기록하지 않고 `counted: false`를 반환합니다 — 정체를
모르는 요청을 한 명으로 합치면 조회수가 사실과 달라집니다.

**브라우저에서 호출해야 합니다.** 서버 사이드 렌더링 중에 호출하면 IP가 프론트엔드
서버의 것으로 잡혀 전 세계 방문자가 한 명으로 합쳐집니다. 프론트엔드는 클라이언트
컴포넌트에서 `localStorage`에 보관한 `visitorId`와 함께 호출합니다.

이 방식은 부정 집계를 막지 못합니다. `visitorId`를 계속 바꿔 보내면 조회수를 올릴 수
있습니다. 개인 블로그 지표 목적이며 과금이나 정산 근거로 쓰지 않습니다.

쿼리: `type` (`guide`\|`news`\|`stock`), `tag`, `locale` (`ko`\|`en`), `limit`,
`offset`, `includeDrafts`.

레코드는 `slug`, `title`, `description`, `type`, `tags`, `body`, `ticker`, `cover`,
`locale`, `draft`, `publishedAt`, `updatedAt`, `createdAt`을 사용합니다.

`publishedAt`은 발행 시각입니다. `draft=false`로 생성하면서 값을 주지 않으면 API가
그 시점의 UTC 시각을 채웁니다. `draft=true`로 생성하면 비워 두고, 나중에
`draft=false`로 바꾸는 요청에서 비어 있을 때만 채웁니다. 이미 값이 있으면 첫 발행
시각을 보존합니다. 저장과 응답은 항상 UTC instant(`2026-08-05T02:15:00Z`)이며 한국
시간 등 지역 시각 표기는 클라이언트가 변환합니다. 목록은 `publishedAt` 내림차순에
NULL을 뒤로 보냅니다.

```bash
curl -i http://127.0.0.1:8000/api/posts
curl -i -H "X-Blog-Key: $BLOG_API_KEY" http://127.0.0.1:8000/api/posts?includeDrafts=true
```

## CI

GitHub Actions는 잠금 파일, 포맷, lint, 타입, 테스트(coverage 90% 이상),
의존성 취약점을 검사합니다. 테스트는 Postgres service 컨테이너에 `db/migrations/`와
`db/blog_app_role.sql`을 적용하고 `blog_app` 롤로 API를 호출합니다. 캐시 없이 의존성을 설치해 잠금 파일의 재현성을
확인합니다. 로컬에서도 같은 게이트를 실행합니다.

```bash
uv lock --check
uv run ruff format --check app tests
uv run ruff check app tests
uv run mypy app
uv run pytest -m "not integration" --cov=app --cov-report=term-missing
uv run pip-audit
```

로컬에서 DB 테스트를 돌리려면 빈 Postgres(예: `pgvector/pgvector:pg17` 임시 컨테이너)에
위와 같이 스키마와 롤을 만들고 두 URL을 넘깁니다. `TEST_DATABASE_URL`은 테스트마다 blog
테이블을 비우므로 **운영 DB를 가리키면 안 됩니다.** URL이 없으면 DB 테스트는 건너뜁니다.

```bash
TEST_DATABASE_URL=postgresql://postgres:<pw>@127.0.0.1:<port>/blog \
TEST_APP_DATABASE_URL=postgresql://blog_app:<pw>@127.0.0.1:<port>/blog \
uv run pytest -m "not integration" --cov=app
```

## Vercel deployment

`vercel.json`은 FastAPI framework preset과 `app/main.py` 함수 진입점을 고정하고,
Fluid Compute와 `maxDuration: 30`을 설정합니다. `.vercelignore`는 root allowlist로
런타임에 필요한 `app/**/*.py`, `pyproject.toml`, `uv.lock`, `.python-version`,
`vercel.json`만 업로드합니다. 그러므로 `tests/`, `docs/`, `db/`, `.venv/`는
함수 번들에 포함되지 않습니다.

Vercel Dashboard에서 **같은 `fastapi-blog` 프로젝트의** Preview와 Production
환경을 분리해 아래 변수를 모두 설정합니다.

환경은 요청 Host/URL hostname으로만 가릅니다. `test`면 test, `dev` 또는
localhost/127.0.0.1이면 development, 그 외는 production입니다. `/docs` `/redoc`
`/openapi.json`은 모든 환경에서 공개합니다. 로그 레벨은 INFO로 고정입니다.

**주의:** 메인 Postgres는 맥미니의 `127.0.0.1:5432`와 내부 docker 네트워크에서만 받습니다.
Vercel 함수는 그대로는 DB에 닿지 않으므로, API를 맥미니의 docker 네트워크에서 실행할지
(다른 서비스와 같은 방식) 먼저 정해야 합니다.

| Variable | Preview | Production | Notes |
| --- | --- | --- | --- |
| `DATABASE_URL` | 필수 | 필수 | `blog_app` 롤 접속 문자열. 서버 전용 |
| `VIEW_HASH_SALT` | 필수 | 필수 | 조회수 방문자 해싱 키. 없으면 조회를 기록하지 않음 |
| `BLOG_API_KEY` | 쓰기·draft 조회에 필요 | 쓰기·draft 조회에 필요 | 긴 난수; `X-Blog-Key`로만 전달 |

배포 전에 CLI 상태와 build 인자를 확인하고, Vercel 프로젝트 `fastapi-blog`을
명시적으로 연결한 뒤 Preview 설정만 가져옵니다. Vercel link는 프로젝트에 연결하는
작업이며, 이 **한 프로젝트** 안에 Preview와 Production 환경 변수 세트를 각각 둡니다.
`.vercel/`은 gitignore 대상이므로 연결 정보와 원격 환경 값은 커밋되지 않습니다. 이
runbook은 `--prod`, `vercel promote`, `--prebuilt`를 사용하지 않습니다.

```bash
vercel whoami
vercel build --help
vercel project list --scope idghst
# fastapi-blog이 없다면 한 번만 명시적으로 생성
vercel project add fastapi-blog --scope idghst
# 새 프로젝트 또는 기존 Other preset을 FastAPI로 맞춤
vercel project update fastapi-blog --framework fastapi --scope idghst
vercel link --yes --team idghst --project fastapi-blog
vercel pull --environment=preview
# 로컬 호환성 검증 전용. 이 결과물을 배포하지 않습니다.
vercel build --target=preview
# source를 직접 업로드하는 Preview 배포만 사용합니다.
vercel deploy --target=preview
```

로컬 build는 호환성 검증 전용입니다. Vercel CLI의 local build는 source upload 단계의
`.vercelignore` 필터를 적용하지 않으므로, 생성된 `.vercel/output`은 배포하지 말고
검증 후 삭제합니다. deploy는 `.vercelignore` allowlist가 적용되는 direct source
deployment를 사용합니다. 현재 작업 디렉터리에서 `--prebuilt`는 사용하지 않습니다.
배포 후 probe 전에 반환된 URL/ID를
`vercel inspect <preview-url-or-deployment-id> --format=json`으로 확인하고 Target이
Preview인지 검증합니다. Preview 배포가 `/health/ready`에서 `200`을 반환하기 전에는
`vercel promote` 또는 `--prod`를 실행하지 않습니다.

반환된 Preview URL에서 다음 상태를 확인합니다. `/health/ready`가 `503`이면
promotion하지 말고 `DATABASE_URL`, `pg_hba.conf`, 네트워크 로그를 점검합니다.

```bash
curl -i https://preview.example.vercel.app/
curl -i https://preview.example.vercel.app/health
curl -i https://preview.example.vercel.app/health/live
curl -i https://preview.example.vercel.app/health/ready
curl -i https://preview.example.vercel.app/api/posts
```

기대 상태는 각각 `200`, `200`, `200`, `200`, `200`입니다.

## Rollback and incident response

장애 배포는 Vercel Dashboard의 이전 정상 deployment로 rollback하거나, 확인한
deployment URL/ID를 사용해 실행합니다.

```bash
vercel rollback <deployment-url-or-id>
```

장애 조사 순서:

1. 응답의 `X-Request-ID`와 배포 URL을 확보합니다.
2. Vercel Functions 로그에서 같은 request ID를 검색합니다.
3. `500`이면 배포 환경 변수와 import 오류를, `503`이면 Postgres 상태·네트워크·timeout을
   확인합니다.
4. 쓰기/`includeDrafts`의 `401`이면 서버의 `X-Blog-Key`만 확인합니다. 키 원문은 로그에
   남기지 않습니다.
5. `403` 또는 빈 결과면 `blog_app`의 table grant와 `blog_app_access` RLS 정책을
   확인합니다(`db/blog_app_role.sql`을 다시 실행하면 맞춰집니다).

키나 JWT 원문은 issue, 로그, 커밋에 넣지 않습니다.
