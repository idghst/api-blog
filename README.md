# fastapi-blog

`blog` Supabase schema를 사용하는 FastAPI 서비스입니다. Vercel에는 Preview와
Production을 분리합니다. 공개 GET은 발행된(`draft=false`) `blog.posts`만 반환하고,
생성·수정·삭제는 서버 전용 `X-Blog-Key`와 secret key client로만 수행합니다. 브라우저의
Supabase 직접 접근은 허용하지 않습니다. 프론트엔드 `idghst-blog`는 MDX를 유지하며 이
저장소는 API만 담당합니다.

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
- Docs (localhost / Host에 `dev` 또는 `test`): <http://127.0.0.1:8000/docs>
- Liveness: <http://127.0.0.1:8000/health> 또는 <http://127.0.0.1:8000/health/live>
- Readiness: <http://127.0.0.1:8000/health/ready>

Vercel 런타임을 로컬에서 확인할 때는 Vercel에 연결된 프로젝트의 환경 변수를
가져온 뒤 실행합니다.

```bash
vercel dev
```

## Supabase setup

서비스별로 별도 Supabase 프로젝트를 사용합니다. 이 서비스의 PostgREST 기본
스키마는 `blog`이며, `public`에 업무 테이블을 만들지 않습니다.

1. Supabase Dashboard의 **API Settings → Exposed schemas**에 `blog`를 추가합니다.
2. 필요한 Preview/Production 프로젝트 각각에 migration을 적용합니다.
3. `blog.posts` migration을 적용합니다. 이 테이블은 RLS를 켜고 `anon`·`authenticated`
   권한과 정책을 부여하지 않습니다. API의 서버 secret client만 접근하며,
   `service_role`/secret key는 이 경로에서만 사용합니다.

호스트는 `supabase.idghst.co.kr` 패턴을 따릅니다. 프로젝트 `.mcp.json`은 만들지
않습니다.

Supabase CLI를 프로젝트 루트에서 초기화·연결한 뒤 migration을 적용합니다. 실제
project ref와 자격 증명은 CLI 프롬프트 또는 안전한 환경 변수로만 전달합니다.

```bash
npx --yes supabase@latest init
npx --yes supabase@latest link
npx --yes supabase@latest db push
```

`supabase/migrations/`은 순서대로 적용됩니다. 새 migration은 항상 CLI가 생성한
파일에 추가합니다.

```bash
npx --yes supabase@latest migration new describe_change
```

## Posts API

공개 목록/상세는 키 없이 호출합니다. `includeDrafts=true`와 쓰기 요청은 아래 헤더가
필요합니다. production host에서 `SUPABASE_SECRET_KEY`가 없으면 `/health`와
`/health/live`를 제외한 요청을 `503`으로 거부합니다. 키가 틀리거나 없으면 동일한
`401` 오류를 반환합니다.

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

쿼리: `type` (`guide`\|`news`\|`stock`), `tag`, `locale` (`ko`\|`en`), `limit`,
`offset`, `includeDrafts`.

레코드는 `slug`, `title`, `description`, `type`, `tags`, `body`, `ticker`, `cover`,
`locale`, `draft`, `publishedAt`, `updatedAt`, `createdAt`을 사용합니다.

```bash
curl -i http://127.0.0.1:8000/api/posts
curl -i -H "X-Blog-Key: $BLOG_API_KEY" http://127.0.0.1:8000/api/posts?includeDrafts=true
```

## CI

GitHub Actions는 잠금 파일, 포맷, lint, 타입, 비통합 테스트(coverage 90% 이상),
의존성 취약점을 검사합니다. 캐시 없이 의존성을 설치해 잠금 파일의 재현성을
확인합니다. 로컬에서도 같은 게이트를 실행합니다.

```bash
uv lock --check
uv run ruff format --check app tests
uv run ruff check app tests
uv run mypy app
uv run pytest -m "not integration" --cov=app --cov-report=term-missing
uv run pip-audit
```

통합 테스트는 실제 Supabase Preview 환경을 대상으로 별도로 실행합니다.

```bash
uv run pytest -m integration
```

## Vercel deployment

`vercel.json`은 FastAPI framework preset과 `app/main.py` 함수 진입점을 고정하고,
Fluid Compute와 `maxDuration: 30`을 설정합니다. `.vercelignore`는 root allowlist로
런타임에 필요한 `app/**/*.py`, `pyproject.toml`, `uv.lock`, `.python-version`,
`vercel.json`만 업로드합니다. 그러므로 `tests/`, `docs/`, `supabase/`, `.venv/`는
함수 번들에 포함되지 않습니다.

Vercel Dashboard에서 **같은 `fastapi-blog` 프로젝트의** Preview와 Production
환경을 분리해 아래 변수를 모두 설정합니다.

환경은 요청 Host/URL hostname으로만 가릅니다. `test`면 test, `dev` 또는
localhost/127.0.0.1이면 development, 그 외는 production입니다. production host에서는
`/docs` `/redoc` `/openapi.json`을 비공개하고, secret key와 HTTPS `SUPABASE_URL`이
필요합니다. 로그 레벨은 INFO로 고정입니다.

| Variable | Preview | Production | Notes |
| --- | --- | --- | --- |
| `SUPABASE_URL` | Preview Supabase URL | Production Supabase URL | 서비스별 별도 프로젝트 |
| `SUPABASE_PUBLISHABLE_KEY` | Preview publishable key | Production publishable key | readiness probe |
| `SUPABASE_SECRET_KEY` | 필수 | 필수 | posts 읽기/쓰기용 서버 secret key; `sb_publishable_` 사용 불가 |
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
promotion하지 말고 Supabase URL, publishable key, exposed schema, 네트워크 로그를
점검합니다.

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
3. `500`이면 배포 환경 변수와 import 오류를, `503`이면 Supabase 상태·네트워크·timeout을
   확인합니다.
4. 쓰기/`includeDrafts`의 `401`이면 서버의 `X-Blog-Key`만 확인합니다. 키 원문은 로그에
   남기지 않습니다.
5. `403` 또는 빈 결과면 `blog` exposed schema, `service_role` table grant, RLS 상태를
   확인합니다. `anon`/`authenticated`에 권한 또는 policy를 추가하면 안 됩니다.

키나 JWT 원문은 issue, 로그, 커밋에 넣지 않습니다.
