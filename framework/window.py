"""
Reporting window resolution.

The window is aligned to whole hours in the REPORT timezone (not UTC) and
floored to the last complete hour, so hourly histograms are gap-free and the
report never covers an hour still in progress. (IST is UTC+05:30 - snapping
in UTC would land bucket edges on :30 local and manufacture a phantom
"quiet hour" at the end.)
"""
import datetime
from zoneinfo import ZoneInfo


class Window:
    def __init__(self, start_utc, end_utc, tz, tz_label):
        self.start = start_utc
        self.end = end_utc
        self.tz = tz
        self.tz_label = tz_label
        self.hours = int(round((end_utc - start_utc).total_seconds() / 3600))
        self.prev_start = start_utc - (end_utc - start_utc)
        self.prev_end = start_utc

    # -- formatting -------------------------------------------------------
    @staticmethod
    def iso(dt):
        return dt.astimezone(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z")

    def local(self, dt):
        return dt.astimezone(self.tz)

    def fmt_local(self, dt, fmt="%d %b %Y, %H:%M"):
        return self.local(dt).strftime(fmt)

    @property
    def label(self):
        return (f"{self.fmt_local(self.start)} → "
                f"{self.fmt_local(self.end)} {self.tz_label}")

    @property
    def date(self):
        """
        Report date = local date of the LAST MOMENT the window covers.

        The end bound is exclusive, so using it directly mislabels any
        window that ends exactly at midnight: `--window-end 2026-07-17T23:59`
        covers all of the 17th but would be filed under the 18th. Stepping
        back one second names the report after the day whose data it
        actually contains, and leaves ordinary runs (window ending mid-day)
        unchanged.
        """
        return self.local(self.end - datetime.timedelta(seconds=1)).date()


def resolve_window(hours=24, tz_name="UTC", tz_label=None, end=None):
    """
    end=None      -> last complete local hour (normal scheduled operation)
    end=datetime  -> explicit end (re-running a historical report)
    """
    tz = ZoneInfo(tz_name)
    if end is None:
        now_local = datetime.datetime.now(tz)
    else:
        if end.tzinfo is None:
            end = end.replace(tzinfo=tz)
        now_local = end.astimezone(tz)
    end_local = now_local.replace(minute=0, second=0, microsecond=0)
    # An explicit end that is exactly on the hour is respected as-is;
    # anything else floors to the last complete hour.
    if end is not None and now_local != end_local:
        end_local = end_local + datetime.timedelta(hours=1)
    start_local = end_local - datetime.timedelta(hours=hours)
    return Window(
        start_local.astimezone(datetime.timezone.utc),
        end_local.astimezone(datetime.timezone.utc),
        tz, tz_label or tz_name,
    )


def parse_ts(value):
    """Parse an ISO timestamp (Z or offset) into an aware UTC datetime."""
    if isinstance(value, datetime.datetime):
        dt = value
    else:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)
