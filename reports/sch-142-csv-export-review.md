## Code Review — sch-142-csv-export

**Verdict:** PASS (no blocking issues)

I checked it with the codebase-search tools. I also ran `uv run pytest app/tests/test_export.py app/tests/test_meetings.py` (44 passed), `uv run ruff check app` (clean) and `uv run mypy app` (clean, 41 files).

### Blocking findings
None.

### Rule checks
- [INFO] **Auth:** `find_references("get_current_user")` shows the export route uses it at `/Users/tthogho1/Documents/source/harness-engineering-demo/app/backend/app/api/routes_meetings.py:73`. It is imported from `app.services.auth_jwt` at `routes_meetings.py:11`. Nothing in `routes_meetings.py` references `auth_legacy`. `test_csv_export_requires_auth` checks that a request with no token gets 401.
- [INFO] **Route order:** `@router.get("/export")` (`routes_meetings.py:70`) is still registered before `@router.get("/{meeting_id}")` (`routes_meetings.py:94`), so `/{meeting_id}` cannot catch `/export` requests.
- [INFO] **CSV escaping:** `find_references("csv_safe")` finds 6 calls in production code (`/Users/tthogho1/Documents/source/harness-engineering-demo/app/backend/app/services/export_service.py:77-84`). They cover title, host full_name, meeting_timezone, status, the invitee cell (all invitees joined into one string) and notes. The only cells not escaped are `str(m.id)` and the two `_format_when` timestamps, and none of those is user-supplied. Escaping the joined invitee string once is enough, because a spreadsheet only treats a cell as a formula based on its first character. `csv_safe` (`export_service.py:41`) handles `None` and empty values and uses `FORMULA_PREFIXES = ("=", "+", "-", "@")`.
- [INFO] **Timezones:** Start and End go through `_format_when` and `TimezoneAwareTime.render(viewer_tz)`. There is no `.strftime()` in `export_service.py`. Viewer timezone is tested in both the unit tests (`test_export.py::TestCSVExport::test_viewer_timezone`) and the integration test (`test_meetings.py::test_csv_export_uses_viewer_timezone`, which expects 16:00 for a Berlin viewer).
- [INFO] **Errors:** An unsupported format raises `HTTPException(400)` (`routes_meetings.py:82`), and the test now uses `xlsx` for this case.
- [INFO] **Naming and patterns:** All names follow the rules: `CSVExport`, `csv_safe`, `CSV_HEADER`, `FORMULA_PREFIXES`, `downloadExport`, and the TS files are unchanged. No model or migration changes, no `Column()` calls, no new camelCase columns. `CSVExport` matches the `ExportService` protocol shape (checked with `outline("export_service")`). It encodes with a UTF-8 BOM (`utf-8-sig`), and Content-Disposition comes from `file_extension`.
- [INFO] **Tests:** They cover every formula prefix (parametrized), a formula character in the middle of a string, None or empty values, BOM plus header, row contents, and a full-row injection test with malicious title, notes, host and invitee. Frontend `downloadExport` is tested for the Bearer header, no `token=` in the URL, and rejection on a non-OK response.

### Non-blocking suggestions
- [SUGGESTION] `export_service.py:70-73,78` reads `m.host`, `m.invitees` and `inv.contact` for every meeting. The relationships are lazy (`/Users/tthogho1/Documents/source/harness-engineering-demo/app/backend/app/models/meeting.py:33-36,48`), so a large export runs a separate query for each of these (an N+1 pattern). Adding `.options(selectinload(Meeting.host), selectinload(Meeting.invitees).selectinload(MeetingInvitee.contact))` to the query at `routes_meetings.py:84` would load them in a few queries.
- [SUGGESTION] `csv_safe` follows the CLAUDE.md rule exactly. OWASP also lists a leading tab (`\t`) and carriage return (`\r`) as risky; adding them would go beyond the current rule and is optional.
- [SUGGESTION] The PDF button in `/Users/tthogho1/Documents/source/harness-engineering-demo/app/frontend/app/meetings/page.tsx` still uses `exportUrl()` with `?token=`. Per the comment the diff adds in `lib/api.ts`, the backend doesn't read that, so PDF export from the browser probably fails with 401. The implementation report marks this as out of scope. A follow-up could switch it to `downloadExport("pdf")` and remove the token-in-URL path.
- [INFO] The `vitest.setup.ts` localStorage fallback (Node 25) only applies when the built-in global is broken, and is a documented deviation. Fine.

### Summary
The change is clean and follows the rules. The export route uses JWT auth and stays above `/{meeting_id}`. Every user-supplied CSV cell goes through `csv_safe`, times are shown in the viewer's timezone via `TimezoneAwareTime`, and tests cover all of it. Backend lint, type check and tests pass. The suggestions above are performance and follow-up items only.
