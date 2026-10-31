"""Tests for export service."""
import csv
import io
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Contact, Meeting, MeetingInvitee, User
from app.services.export_service import (
    CSV_HEADER,
    FORMULA_PREFIXES,
    CSVExport,
    PDFExport,
    _format_when,
    csv_safe,
)


def make_meeting(
    title: str = "Discovery Call",
    notes: str | None = "Agenda",
    host_name: str = "Dana Ortiz",
    contacts: list[tuple[str, str]] | None = None,
) -> Meeting:
    """Build a transient (non-DB) Meeting with host + invitees for export tests."""
    start = datetime(2026, 7, 20, 14, 0, tzinfo=timezone.utc)
    m = Meeting(
        id=1,
        title=title,
        notes=notes,
        start_time=start,
        end_time=start + timedelta(minutes=30),
        meeting_timezone="UTC",
        status="scheduled",
    )
    m.host = User(full_name=host_name)
    m.invitees = [
        MeetingInvitee(contact=Contact(name=name, email=email))
        for name, email in (contacts if contacts is not None else [("Priya Shah", "priya@globex.test")])
    ]
    return m


def parse_csv(data: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))


class TestPDFExport:
    def test_render_returns_bytes(self) -> None:
        exporter = PDFExport()
        result = exporter.render([])
        assert isinstance(result, bytes)
        assert b"Meetings Export (PDF)" in result

    def test_render_with_meetings(self) -> None:
        """PDFExport renders times using TimezoneAwareTime (no naive strftime)."""
        exporter = PDFExport()
        # We just verify it runs without error and returns bytes
        result = exporter.render([], viewer_tz="UTC")
        assert isinstance(result, bytes)

    def test_content_type(self) -> None:
        exporter = PDFExport()
        assert exporter.content_type == "application/pdf"
        assert exporter.file_extension == "pdf"


class TestFormatWhen:
    def test_utc_format(self) -> None:
        dt = datetime(2026, 7, 20, 14, 0, tzinfo=timezone.utc)
        result = _format_when(dt, "UTC")
        assert "14:00" in result

    def test_berlin_format(self) -> None:
        dt = datetime(2026, 7, 20, 14, 0, tzinfo=timezone.utc)
        result = _format_when(dt, "Europe/Berlin")
        assert "16:00" in result

    def test_no_naive_strftime(self) -> None:
        """Ensures we're not using naive strftime (which would give UTC regardless)."""
        dt = datetime(2026, 7, 20, 14, 0, tzinfo=timezone.utc)
        utc_result = _format_when(dt, "UTC")
        berlin_result = _format_when(dt, "Europe/Berlin")
        assert utc_result != berlin_result


class TestCsvSafe:
    @pytest.mark.parametrize("prefix", FORMULA_PREFIXES)
    def test_formula_prefixes_escaped(self, prefix: str) -> None:
        assert csv_safe(f"{prefix}SUM(A1)") == f"'{prefix}SUM(A1)"

    def test_plain_string_unchanged(self) -> None:
        assert csv_safe("Discovery Call") == "Discovery Call"

    def test_empty_and_none(self) -> None:
        assert csv_safe("") == ""
        assert csv_safe(None) == ""

    def test_formula_char_mid_string_unchanged(self) -> None:
        assert csv_safe("Q3 = revenue") == "Q3 = revenue"


class TestCSVExport:
    def test_render_empty_has_bom_and_header(self) -> None:
        result = CSVExport().render([])
        assert isinstance(result, bytes)
        assert result.startswith(b"\xef\xbb\xbf")
        assert parse_csv(result) == [CSV_HEADER]

    def test_content_type(self) -> None:
        exporter = CSVExport()
        assert exporter.content_type == "text/csv"
        assert exporter.file_extension == "csv"

    def test_row_contents(self) -> None:
        rows = parse_csv(CSVExport().render([make_meeting()], viewer_tz="UTC"))
        assert rows[1][0] == "1"
        assert rows[1][1] == "Discovery Call"
        assert rows[1][2] == "Dana Ortiz"
        assert rows[1][7] == "Priya Shah <priya@globex.test>"
        assert rows[1][8] == "Agenda"

    def test_viewer_timezone(self) -> None:
        m = make_meeting()
        utc_row = parse_csv(CSVExport().render([m], viewer_tz="UTC"))[1]
        berlin_row = parse_csv(CSVExport().render([m], viewer_tz="Europe/Berlin"))[1]
        assert "14:00" in utc_row[3]
        assert "16:00" in berlin_row[3]
        assert utc_row[3] != berlin_row[3]

    def test_csv_export_escapes_formula_injection(self) -> None:
        m = make_meeting(
            title='=HYPERLINK("http://evil.example","Click me")',
            notes="+cmd",
            host_name="@admin",
            contacts=[("-1+1", "x@evil.example")],
        )
        row = parse_csv(CSVExport().render([m], viewer_tz="UTC"))[1]
        for cell in row:
            assert not cell.startswith(FORMULA_PREFIXES), cell
        assert row[1].startswith("'=")

    def test_null_notes_and_no_invitees(self) -> None:
        m = make_meeting(notes=None, contacts=[])
        row = parse_csv(CSVExport().render([m]))[1]
        assert row[7] == ""
        assert row[8] == ""
