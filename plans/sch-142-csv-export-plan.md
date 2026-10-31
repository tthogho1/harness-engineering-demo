# Plan: CSV Export for Meetings Page

## Ticket
**SCH-142** — Add CSV export to the `/meetings` page via `GET /api/meetings/export?format=csv`, with formula-injection escaping on every user-supplied cell (spec: `app/docs/specs/q3-reporting-analytics.md` lines 8-43).

Type: new capability (enhancement to an existing export route). Layers: service, route, frontend API client, frontend page, tests. **No migration needed** (no new table or column).

## Affected Files

### Read before implementing
- `CLAUDE.md`: CSV escaping rule, timezone rule, forward (JWT) auth rule.
- `.claude/context/export-pattern.md`: `ExportService` protocol, `csv_safe()` reference, implementation checklist.
- `.claude/context/timezones.md`: render through `TimezoneAwareTime`, never `.strftime()`.
- `app/backend/app/services/export_service.py` (lines 1-44): `ExportService` protocol (L24-28), `_format_when` (L31-32), `PDFExport` (L35-44) to mirror.
- `app/backend/app/api/routes_meetings.py` (lines 70-88): `export_meetings` route. It already uses `Depends(get_current_user)` from `auth_jwt` (L11, L73).
- `app/backend/app/models/meeting.py` (lines 9-48): `Meeting.title` / `notes` / `host` / `invitees`, and `MeetingInvitee.contact`.
- `app/backend/app/models/contact.py` (lines 9-20): `Contact.name`, `Contact.email`.
- `app/backend/app/tests/test_export.py` (lines 1-43): unit-test pattern for exporters.
- `app/backend/app/tests/test_meetings.py` (lines 218-229): `TestExport`. **L225-229 `test_unsupported_format` asserts CSV returns 400 and must be rewritten.**
- `app/backend/app/tests/conftest.py` (lines 153-169): `meeting` fixture ("Discovery Call", 14:00 UTC, one invitee "Priya Shah" / priya@globex.test). The `admin_user` fixture is UTC and `member_user` is Europe/Berlin.
- `app/frontend/app/meetings/page.tsx` (lines 136-153): existing Export PDF button, gated on `mounted`.
- `app/frontend/lib/api.ts` (lines 17-20 `authHeaders`, lines 199-203 `exportUrl`).
- `app/frontend/__tests__/api.test.ts` (lines 35-41): `exportUrl` test.

### Modify
- `app/backend/app/services/export_service.py`: add `FORMULA_PREFIXES`, `csv_safe()` and the `CSVExport` class; update the module docstring.
- `app/backend/app/api/routes_meetings.py`: dispatch `format=csv` to `CSVExport`; keep the 400 for unknown formats.
- `app/backend/app/tests/test_export.py`: add `TestCsvSafe` and `TestCSVExport`.
- `app/backend/app/tests/test_meetings.py`: replace `test_unsupported_format` (CSV now succeeds) and add CSV route tests.
- `app/frontend/lib/api.ts`: add `downloadExport(format)`, which fetches with the Bearer header and triggers a blob download.
- `app/frontend/app/meetings/page.tsx`: add an "Export CSV" button next to Export PDF.
- `app/frontend/__tests__/api.test.ts`: add a `downloadExport` test.

### Create
- None.

## Ordered Tasks

### Task 1 — Add `csv_safe()` and `CSVExport` to the export service
- What: in `app/backend/app/services/export_service.py`:
  - Add `import csv` and `import io`.
  - Add `FORMULA_PREFIXES = ("=", "+", "-", "@")` and `csv_safe(value: str | None) -> str`. It returns `""` for `None` and prefixes `'` when `value[0] in FORMULA_PREFIXES`.
  - Add `class CSVExport` with `content_type = "text/csv"` and `file_extension = "csv"`. Its `render(self, meetings: list[Meeting], viewer_tz: str = "UTC") -> bytes`:
    - Writes with `csv.writer(io.StringIO())`.
    - Header row: `["ID", "Title", "Host", "Start", "End", "Timezone", "Status", "Invitees", "Notes"]`. This adds `Host` and `Notes` to the context-doc header because the spec names host name and notes as user-controlled fields that must be exported escaped.
    - One row per meeting:
      - `str(m.id)`
      - `csv_safe(m.title)`
      - `csv_safe(m.host.full_name if m.host else "")`
      - `_format_when(m.start_time, viewer_tz)` and `_format_when(m.end_time, viewer_tz)`
      - `m.meeting_timezone`
      - `m.status`
      - `csv_safe("; ".join(f"{inv.contact.name} <{inv.contact.email}>" for inv in m.invitees))`
      - `csv_safe(m.notes)`
    - Returns `buf.getvalue().encode("utf-8-sig")`.
  - Update the docstring (L1-13) so it no longer says PDF is the only exporter.
- Pattern: `export_service.py:L35-44` (`PDFExport`). Mirror the class attributes and the `_format_when` usage exactly.
- Gotcha:
  - Never call `.strftime()` on `start_time`/`end_time`; use `_format_when` only.
  - Apply `csv_safe` to the **whole joined invitees cell**. The cell's first character comes from the first contact name, which is user-controlled.
  - `meeting_timezone` and `status` are not free-text user input, but wrapping them in `csv_safe` is harmless if you prefer uniformity.
  - Keep `mypy`-clean: `csv_safe` must accept `str | None`.
- Validate: `cd app/backend && uv run ruff check app && uv run mypy app`

### Task 2 — Unit-test `csv_safe` and `CSVExport`
- What: in `app/backend/app/tests/test_export.py`, import `CSVExport` and `csv_safe`, and build in-memory `Meeting` objects (no DB). Set `host=User(full_name=...)` and `invitees=[MeetingInvitee(contact=Contact(name=..., email=...))]` directly on the transient objects. Add:
  - `TestCsvSafe`:
    - Each of `=`, `+`, `-`, `@` gets a `'` prefix.
    - A plain string is unchanged.
    - `""` and `None` return `""`.
    - A formula character in the middle of the string is unchanged.
  - `TestCSVExport`:
    - `render([])` returns bytes that start with the UTF-8 BOM and contain the header row.
    - `content_type == "text/csv"` and `file_extension == "csv"`.
    - Timezones: the same 14:00 UTC meeting renders `14:00` for `"UTC"` and `16:00` for `"Europe/Berlin"`, and the two outputs differ.
    - **Formula injection**: title `=HYPERLINK("http://evil.example","Click me")`, notes `+cmd`, host `@admin`, contact name `-1+1`. Parse the output back with `csv.reader(io.StringIO(result.decode("utf-8-sig")))` and assert that no cell in the data row starts with `=`, `+`, `-` or `@`, and that the title cell starts with `'=`.
    - A meeting with `notes=None` and no invitees renders empty cells without error.
- Pattern: `test_export.py:L7-43` (class-based, no DB), plus the formula-injection snippet in `.claude/context/export-pattern.md` ("Test Pattern"). Parsing with `csv.reader` is more robust than the snippet's `split("\n")`.
- Gotcha: assert on parsed cells, not on raw text. `csv.writer` quotes fields that contain `"` or `,`, so the raw line starts with `"'=...`.
- Validate: `cd app/backend && uv run pytest app/tests/test_export.py -q`

### Task 3 — Dispatch `format=csv` in the export route
- What: in `app/backend/app/api/routes_meetings.py`:
  - Change the L12 import to `from app.services.export_service import CSVExport, ExportService, PDFExport`.
  - In `export_meetings` (L70-88), replace the `format != "pdf"` guard (L76-78) with a mapping or if/elif that picks `exporter: ExportService` (`PDFExport()` for `"pdf"`, `CSVExport()` for `"csv"`).
  - Otherwise `raise HTTPException(status_code=400, detail=f"Unsupported export format: {format}")`.
  - Do the format check **before** the DB query. Keep the query, `viewer_tz=current.timezone`, and the `Content-Disposition` header (it already interpolates `exporter.file_extension`, which yields `meetings.csv`).
  - Remove the stale "Only PDF export exists today" comment.
- Pattern: existing route body `routes_meetings.py:L79-88`.
- Gotcha:
  - Keep `current: User = Depends(get_current_user)` from `auth_jwt`. Do not touch `auth_legacy`.
  - `Response(media_type="text/csv")` makes Starlette send `text/csv; charset=utf-8`, so tests should use `startswith("text/csv")`.
- Validate: `cd app/backend && uv run ruff check app && uv run mypy app`

### Task 4 — Route tests for CSV export
- What: in `app/backend/app/tests/test_meetings.py` `TestExport` (L218-229):
  - Rewrite `test_unsupported_format` to request `format=xlsx` and still expect 400.
  - Add `test_csv_export`:
    - Uses `admin_headers` and `meeting`; expects 200.
    - `content-type` starts with `text/csv`.
    - `content-disposition` contains `meetings.csv`.
    - The decoded body contains the header row and `Discovery Call` and `Priya Shah`.
  - Add `test_csv_export_requires_auth`: no headers, expect 401.
  - Add `test_csv_export_uses_viewer_timezone`: `member_headers` (Europe/Berlin user, same team) and `meeting` (14:00 UTC); the body contains `16:00`.
- Pattern: `test_meetings.py:L219-223` (`test_pdf_export`), plus the `client` / `admin_headers` / `member_headers` fixtures in `conftest.py`.
- Gotcha: the test DB `schedulr_test` must exist; it already exists on the running `schedulr-db` container.
- Validate: `cd app/backend && uv run pytest app/tests/test_meetings.py -q`

### Task 5 — Frontend: authenticated `downloadExport()` helper
- What: in `app/frontend/lib/api.ts` near `exportUrl` (L199-203), add:
  ```ts
  export async function downloadExport(format: "pdf" | "csv"): Promise<void>
  ```
  It:
  1. `fetch`es `${API_BASE}/api/meetings/export?format=${format}` with `headers: authHeaders()`.
  2. Throws on a non-OK response, like `apiFetch` does.
  3. Calls `res.blob()`, then `URL.createObjectURL(blob)`.
  4. Creates a temporary `<a download="meetings.${format}">` and clicks it.
  5. Removes the anchor and calls `URL.revokeObjectURL`.

  Update the stale comment at L199.
- Pattern: `apiFetch` (`api.ts:L27-42`) for error handling, and `authHeaders` (L17-20).
- Gotcha: **why not reuse `exportUrl`.** `exportUrl` puts the JWT in a `?token=` query parameter. The backend's `get_current_user` (`app/backend/app/services/auth_jwt.py:L18,27-35`) reads only the `Authorization: Bearer` header via `OAuth2PasswordBearer`, so a plain `<a href>` request gets a 401. The token in the URL would also leak into history and logs. Leave `exportUrl` and the PDF button as they are; fixing the PDF button is out of scope (mention it in the implementation report).
- Validate: `cd app/frontend && npx tsc --noEmit`

### Task 6 — Frontend: Export CSV button on `/meetings`
- What: in `app/frontend/app/meetings/page.tsx` L136-153:
  - Add a second `Button variant="outline" size="sm"` with `<Download className="h-4 w-4" />` and the label "Export CSV". Its `onClick` calls `downloadExport("csv")`.
  - Track an `exporting` boolean so the button is disabled while the download runs.
  - On failure, show an error (reuse `setError("Could not export meetings")`).
  - Disable the button until `mounted`, mirroring the PDF button.
  - Import `downloadExport` from `@/lib/api`.
  - Update the stale "SCH-142 adds CSV" comment.
- Pattern: the Export PDF button at `page.tsx:L140-152` (styling and mount gating).
- Gotcha: `setError` replaces the table with the error message (L161-162). That is acceptable, but do not leave `exporting` stuck: use `finally`.
- Validate: `cd app/frontend && npx tsc --noEmit`

### Task 7 — Frontend unit test for `downloadExport`
- What: in `app/frontend/__tests__/api.test.ts`, add `describe("downloadExport")`. Setup:
  - `vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(new Blob(["a,b"]), { status: 200 })))`.
  - Stub `URL.createObjectURL` and `URL.revokeObjectURL` with `vi.fn()`; jsdom does not implement them.
  - `setToken("tok")`.

  Assert:
  - `fetch` was called with a URL containing `/api/meetings/export?format=csv` and `headers.Authorization === "Bearer tok"`.
  - `createObjectURL` was called.

  Add a second case: a `401` response makes `downloadExport` reject.
- Pattern: `api.test.ts:L35-41`. The `beforeEach` at L8-11 already calls `vi.restoreAllMocks()`; also call `vi.unstubAllGlobals()`.
- Gotcha: stubbing `HTMLAnchorElement.prototype.click` avoids jsdom "navigation not implemented" noise.
- Validate: `cd app/frontend && npm run test`

## Validation Gate
Run these in order after all tasks are done:
```
cd app/backend && uv run ruff check app
cd app/backend && uv run mypy app
cd app/backend && uv run pytest
cd app/frontend && npx tsc --noEmit
cd app/frontend && npm run test
```

## Acceptance Criteria
- [ ] `GET /api/meetings/export?format=csv` with a valid Bearer JWT returns 200, `Content-Type: text/csv…`, and `Content-Disposition: attachment; filename=meetings.csv`.
- [ ] Without auth the route returns 401; an unknown format (for example `xlsx`) returns 400; `format=pdf` behaves as before.
- [ ] The CSV body is UTF-8 with a BOM, and its header row is `ID,Title,Host,Start,End,Timezone,Status,Invitees,Notes`.
- [ ] Start and end times render in the requesting user's timezone (14:00 UTC is `16:00` for a Europe/Berlin viewer) via `TimezoneAwareTime`, with no `.strftime()` on raw datetimes.
- [ ] Every user-supplied cell (title, host name, invitees, notes) that starts with `=`, `+`, `-` or `@` is prefixed with `'`. This is covered by a test that parses the CSV.
- [ ] `CSVExport` satisfies the `ExportService` protocol (mypy passes with `exporter: ExportService`).
- [ ] `/meetings` shows an "Export CSV" button next to Export PDF that downloads `meetings.csv` using the Bearer header (no token in the URL).
- [ ] The obsolete `test_unsupported_format` CSV assertion is replaced, and the stale "only PDF" comments are removed.
- [ ] All validation gate commands pass.
