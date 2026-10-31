# Testing — Schedulr

## Backend (pytest)

**Framework:** pytest 8.x  
**Config:** `app/backend/pyproject.toml` — `testpaths = ["app/tests"]`, `pythonpath = ["."]`  
**Run:** `cd app/backend && uv run pytest`

### Test Files

| File | What it tests |
|------|--------------|
| `app/tests/test_auth.py` | Login, token validation, 401 cases |
| `app/tests/test_meetings.py` | CRUD, team isolation, status transitions |
| `app/tests/test_contacts.py` | Contact CRUD, team scoping |
| `app/tests/test_teams.py` | Team management |
| `app/tests/test_availability.py` | Availability rules |
| `app/tests/test_export.py` | Export service unit tests (no DB needed) |
| `app/tests/test_timezone.py` | `TimezoneAwareTime` rendering |

### Fixtures (`app/tests/conftest.py`)

**Database:** a real Postgres test DB, `schedulr_test`, on the same container as the dev DB
(`postgresql+psycopg://schedulr:schedulr@localhost:5433/schedulr_test`; override with
`TEST_DATABASE_URL`). It is **not** created by `docker compose up` — create it once with
`docker exec schedulr-db createdb -U schedulr schedulr_test`, otherwise every test errors with
`database "schedulr_test" does not exist`. Tables are created/dropped per test session; each
test runs inside a nested transaction that is rolled back, so tests never see each other's data.

- `db` — Postgres session wrapped in a rolled-back transaction (overrides `get_db`).
- `client` — `TestClient` with the `db` override applied.
- `team`, `admin_user`, `member_user`, `contact`, `meeting`, `availability_slot` — seeded model rows.
- `admin_headers` / `member_headers` — JWT `Authorization: Bearer` headers (forward auth pattern; use these for new routes).
- `admin_token` / `member_token` — the raw JWTs behind those headers.
- `admin_session_headers` — legacy `X-Session-Token` header; only for routes still on `auth_legacy.py`.

### Patterns

```python
# Route test pattern (from test_meetings.py)
def test_create_meeting(client, admin_headers):
    resp = client.post("/api/meetings", json={...}, headers=admin_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "..."

# Unit test (no HTTP, no DB) — from test_export.py
def test_render_returns_bytes():
    exporter = PDFExport()
    result = exporter.render([])
    assert isinstance(result, bytes)
```

### What Tests Do NOT Cover

- End-to-end browser flows (no Playwright backend tests yet; frontend has `e2e/` with Playwright).
- No coverage minimum is enforced in CI — coverage is aspirational.

## Frontend (Vitest + Playwright)

**Unit tests:** Vitest (`npm run test` in `app/frontend/`); config in `vitest.config.ts`.  
**E2E:** Playwright (`app/frontend/e2e/`); config in `playwright.config.ts`.  
**Component tests:** in `app/frontend/__tests__/`.

## Adding Tests for a New Feature

1. Backend: add `app/backend/app/tests/test_<resource>.py` — mirror `test_export.py` for pure-unit, `test_meetings.py` for HTTP+DB.
2. For timezone-sensitive code: always test with at least one non-UTC timezone (see `test_export.py:TestFormatWhen.test_berlin_format`).
3. For exports: include a formula-injection test (see `.claude/context/export-pattern.md`).
