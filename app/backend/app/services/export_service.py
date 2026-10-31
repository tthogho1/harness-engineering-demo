"""Export pipeline.

``ExportService`` is the structural protocol every exporter satisfies.
Concrete exporters:

- ``PDFExport`` — minimal stand-in PDF renderer.
- ``CSVExport`` — SCH-142. Every user-supplied cell is passed through
  ``csv_safe()`` to prevent spreadsheet formula injection (a cell starting
  with ``=``, ``+``, ``-`` or ``@`` would otherwise be evaluated by
  Excel/Google Sheets, e.g. ``=HYPERLINK(...)``).

All datetimes are rendered in the viewer's timezone via ``TimezoneAwareTime``.
"""
import csv
import io
from datetime import datetime
from typing import Protocol

from app.models import Meeting
from app.utils.timezones import TimezoneAwareTime


DISPLAY_FORMAT = "%Y-%m-%d %H:%M %Z"

FORMULA_PREFIXES = ("=", "+", "-", "@")

CSV_HEADER = ["ID", "Title", "Host", "Start", "End", "Timezone", "Status", "Invitees", "Notes"]


class ExportService(Protocol):
    content_type: str
    file_extension: str

    def render(self, meetings: list[Meeting], viewer_tz: str = "UTC") -> bytes: ...


def _format_when(dt: datetime, tz_name: str = "UTC") -> str:
    return TimezoneAwareTime(dt).render(tz_name)


def csv_safe(value: str | None) -> str:
    """Escape formula injection in a CSV cell (prefix ``'`` if it starts with = + - @)."""
    if not value:
        return ""
    if value[0] in FORMULA_PREFIXES:
        return "'" + value
    return value


class PDFExport:
    content_type = "application/pdf"
    file_extension = "pdf"

    def render(self, meetings: list[Meeting], viewer_tz: str = "UTC") -> bytes:
        # Minimal stand-in for a real PDF renderer (the demo doesn't open PDFs).
        lines = ["Meetings Export (PDF)", "=" * 24]
        for m in meetings:
            lines.append(f"{m.title} | {_format_when(m.start_time, viewer_tz)} | {m.status}")
        return ("\n".join(lines)).encode("utf-8")


class CSVExport:
    content_type = "text/csv"
    file_extension = "csv"

    def render(self, meetings: list[Meeting], viewer_tz: str = "UTC") -> bytes:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(CSV_HEADER)
        for m in meetings:
            invitees = "; ".join(
                f"{inv.contact.name} <{inv.contact.email}>" for inv in m.invitees
            )
            writer.writerow(
                [
                    str(m.id),
                    csv_safe(m.title),
                    csv_safe(m.host.full_name if m.host else ""),
                    _format_when(m.start_time, viewer_tz),
                    _format_when(m.end_time, viewer_tz),
                    csv_safe(m.meeting_timezone),
                    csv_safe(m.status),
                    csv_safe(invitees),
                    csv_safe(m.notes),
                ]
            )
        # BOM so Excel detects UTF-8.
        return buf.getvalue().encode("utf-8-sig")
