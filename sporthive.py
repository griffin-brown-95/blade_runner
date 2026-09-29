#!/usr/bin/env python3
"""
Sporthive (MYLAPS) practice timing scraper.

Pulls per-lap speed skating timing data from sporthive.com's public JSON API
for a given practice location (track), optionally restricted to a date range,
and writes one CSV per transponder-session (i.e. one day per transponder/skater).

API endpoints used (public, no auth required):
  1. Activity list:
     GET https://practice-api.speedhive.com/api/v1/locations/{location_id}/activities?offset=N
     Returns up to 200 activities per call, sorted newest -> oldest, via `offset`
     pagination (fixed page size of 200; no server-side date filter exists, so we
     paginate and stop once results fall before the requested start date).

  2. Per-activity lap data:
     GET https://practice-api.speedhive.com/api/v1/training/activities/{activity_id}/sessions
     Returns lap-by-lap timing/speed data for one transponder's session.

Usage:
    python sporthive_scraper.py --location-id 4607 --start-date 2026-08-25 --end-date 2026-09-02

    # Just the last N days:
    python sporthive_scraper.py --location-id 4607 --days 7

    # Everything (no date filter) -- will be slow/large for high-traffic tracks:
    python sporthive_scraper.py --location-id 4607 --all
"""

import argparse
import csv
import sys
import time
from datetime import datetime, timedelta, date
from pathlib import Path

import requests

BASE = "https://practice-api.speedhive.com/api/v1"
PAGE_SIZE = 200  # server-enforced; `limit`/`take`/`pageSize` params are ignored
REQUEST_TIMEOUT = 20
RETRY_COUNT = 3
RETRY_BACKOFF_SECS = 2
POLITE_DELAY_SECS = 0.15  # small delay between requests so we're not hammering their API

SESSION = requests.Session()
SESSION.headers.update({
    # practice-api.speedhive.com checks Origin/Referer server-side and 401s
    # requests that don't look like they came from sporthive.com's own
    # frontend, so we mimic what a browser sends automatically.
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Origin": "https://sporthive.com",
    "Referer": "https://sporthive.com/",
})


def _get_json(url: str, params: dict | None = None) -> dict:
    """GET with basic retry/backoff. Raises on repeated failure."""
    last_exc = None
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            resp = SESSION.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_BACKOFF_SECS * attempt)
    raise RuntimeError(f"Failed GET {url} after {RETRY_COUNT} attempts: {last_exc}")


def fetch_location_info(location_id: int) -> dict:
    """Fetch track/location metadata (name, length, sport, etc.)."""
    data = _get_json(f"{BASE}/locations/{location_id}/activities", params={"offset": 0})
    return data.get("location", {})


def iter_activities(location_id: int, start_date: date | None, end_date: date | None):
    """
    Yield activity dicts for a location, newest first, stopping early once we've
    paginated past `start_date` (since the API returns newest -> oldest and has
    no server-side date filter).

    If start_date is None, walks the *entire* history for the location.
    end_date, if given, is used to skip activities newer than it (inclusive).
    """
    offset = 0
    seen_any_in_range = False

    while True:
        data = _get_json(f"{BASE}/locations/{location_id}/activities", params={"offset": offset})
        activities = data.get("activities", [])
        if not activities:
            break

        for act in activities:
            act_date = _parse_start_date(act)
            if end_date and act_date > end_date:
                continue  # too new, skip forward
            if start_date and act_date < start_date:
                # Since list is sorted newest -> oldest, once we're before the
                # window we can stop entirely.
                if seen_any_in_range or start_date is not None:
                    return
                continue
            seen_any_in_range = True
            yield act

        if len(activities) < PAGE_SIZE:
            break  # last page

        offset += PAGE_SIZE
        time.sleep(POLITE_DELAY_SECS)


def _parse_start_date(activity: dict) -> date:
    # startTime looks like "2026-09-02T09:23:49-06:00"
    return datetime.fromisoformat(activity["startTime"]).date()


def fetch_sessions(activity_id: int) -> dict:
    """Fetch full lap-by-lap session data for one activity (one transponder's day)."""
    return _get_json(f"{BASE}/training/activities/{activity_id}/sessions")


def flatten_laps(activity: dict, sessions_data: dict) -> list[dict]:
    """Turn one activity's session/lap data into flat rows for CSV writing."""
    rows = []
    chip_label = activity.get("chipLabel", "")
    activity_id = activity.get("id")
    activity_date = _parse_start_date(activity).isoformat()

    for session in sessions_data.get("sessions", []):
        session_id = session.get("id")
        session_start = session.get("dateTimeStart", "")
        for lap in session.get("laps", []):
            rows.append({
                "chip_label": chip_label,
                "activity_id": activity_id,
                "activity_date": activity_date,
                "session_id": session_id,
                "session_start": session_start,
                "lap_nr": lap.get("nr"),
                "lap_start": lap.get("dateTimeStart"),
                "lap_duration_sec": lap.get("duration"),
                "lap_speed_kph": (lap.get("speed") or {}).get("kph"),
                "lap_speed_mps": (lap.get("speed") or {}).get("mps"),
                "session_duration_sec": session.get("duration"),
                "status": lap.get("status"),
            })
    return rows


def write_activity_csv(rows: list[dict], out_dir: Path, activity: dict) -> Path:
    """Write one CSV per transponder-session, named <date>_<chip_label>_<activity_id>.csv."""
    chip_label = (activity.get("chipLabel") or "unknown").replace(" ", "_")
    activity_date = _parse_start_date(activity).isoformat()
    activity_id = activity.get("id")
    filename = f"{activity_date}_{chip_label}_{activity_id}.csv"
    filename = "".join(c for c in filename if c.isalnum() or c in "._-")
    out_path = out_dir / filename

    fieldnames = [
        "chip_label", "activity_id", "activity_date", "session_id", "session_start",
        "lap_nr", "lap_start", "lap_duration_sec", "lap_speed_kph", "lap_speed_mps",
        "session_duration_sec", "status",
    ]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def write_summary_csv(activities_and_stats: list[tuple[dict, dict]], out_dir: Path) -> Path:
    """Write a single roll-up CSV: one row per transponder-session with summary stats."""
    out_path = out_dir / "_summary.csv"
    fieldnames = [
        "activity_id", "chip_label", "activity_date", "chip_code",
        "lap_count", "fastest_time_sec", "average_time_sec", "median_time_sec",
        "total_training_time", "active_training_time",
        "average_speed_kph", "fastest_speed_kph",
    ]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for activity, sessions_data in activities_and_stats:
            stats = sessions_data.get("stats", {}) or {}
            avg_speed = (stats.get("averageSpeed") or {}).get("kph")
            fast_speed = (stats.get("fastestSpeed") or {}).get("kph")
            writer.writerow({
                "activity_id": activity.get("id"),
                "chip_label": activity.get("chipLabel"),
                "activity_date": _parse_start_date(activity).isoformat(),
                "chip_code": activity.get("chipCode"),
                "lap_count": stats.get("lapCount"),
                "fastest_time_sec": stats.get("fastestTime"),
                "average_time_sec": stats.get("averageTime"),
                "median_time_sec": stats.get("medianTime"),
                "total_training_time": stats.get("totalTrainingTime"),
                "active_training_time": stats.get("activeTrainingTime"),
                "average_speed_kph": avg_speed,
                "fastest_speed_kph": fast_speed,
            })
    return out_path


def run(location_id: int, start_date: date | None, end_date: date | None, out_dir: Path,
        per_activity_csv: bool = True) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    location = fetch_location_info(location_id)
    print(f"Location: {location.get('name')} (id={location_id}, "
          f"length={location.get('trackLength')}m, sport={location.get('sport')})")

    if start_date or end_date:
        print(f"Date range: {start_date or '(no lower bound)'} -> {end_date or '(no upper bound)'}")
    else:
        print("No date range given -- pulling FULL history. This may take a while.")

    activities_and_stats = []
    count = 0
    for activity in iter_activities(location_id, start_date, end_date):
        count += 1
        chip_label = activity.get("chipLabel", "?")
        act_date = _parse_start_date(activity).isoformat()
        print(f"  [{count}] {act_date}  {chip_label}  (activity {activity['id']})")

        sessions_data = fetch_sessions(activity["id"])
        time.sleep(POLITE_DELAY_SECS)

        if per_activity_csv:
            rows = flatten_laps(activity, sessions_data)
            if rows:
                write_activity_csv(rows, out_dir, activity)

        activities_and_stats.append((activity, sessions_data))

    summary_path = write_summary_csv(activities_and_stats, out_dir)
    print(f"\nDone. {count} transponder-sessions written to {out_dir}/")
    print(f"Summary: {summary_path}")


def _parse_date_arg(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date '{value}', expected YYYY-MM-DD")


def main():
    parser = argparse.ArgumentParser(description="Scrape Sporthive practice timing data.")
    parser.add_argument("--location-id", type=int, required=True,
                         help="Sporthive location/practice ID, e.g. 4607 for "
                              "https://sporthive.com/practice/4607")
    parser.add_argument("--start-date", type=_parse_date_arg, default=None,
                         help="Earliest date to include (YYYY-MM-DD).")
    parser.add_argument("--end-date", type=_parse_date_arg, default=None,
                         help="Latest date to include (YYYY-MM-DD). Defaults to today if "
                              "--start-date or --days is given and --end-date is omitted.")
    parser.add_argument("--days", type=int, default=None,
                         help="Shortcut: pull the last N days (overrides --start-date).")
    parser.add_argument("--all", action="store_true",
                         help="Pull full history with no date filter. Overrides --start-date/--days.")
    parser.add_argument("--out-dir", type=Path, default=Path("./sporthive_data"),
                         help="Output directory for CSVs (default: ./sporthive_data)")
    parser.add_argument("--summary-only", action="store_true",
                         help="Only write the roll-up summary CSV, skip per-activity lap CSVs.")

    args = parser.parse_args()

    if args.all:
        start_date, end_date = None, None
    elif args.days is not None:
        end_date = args.end_date or date.today()
        start_date = end_date - timedelta(days=args.days - 1)
    else:
        start_date = args.start_date
        end_date = args.end_date or (date.today() if start_date else None)

    try:
        run(args.location_id, start_date, end_date, args.out_dir,
            per_activity_csv=not args.summary_only)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()