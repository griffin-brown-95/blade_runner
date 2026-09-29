#!/usr/bin/env python3
"""
Load Sporthive practice laps into a local SQLite database.

Re-runnable: activities already in the database are skipped (except the most
recent day, which may still have been in progress on the last run).

Usage:
    python ingest.py --start-date 2026-08-01 --end-date 2026-08-31
    python ingest.py                      # incremental: resume from last loaded day
"""

import argparse
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

import chips
import sporthive

ROOT = Path(__file__).parent
DEFAULT_DB = ROOT / "data" / "sporthive.sqlite"
DEFAULT_LOCATION = 4607  # UOO Short Track, 111 m
# Published nightly by .github/workflows/scrape.yml; the database is not kept in git.
RELEASE_DB_URL = "https://github.com/griffin-brown-95/blade_runner/releases/download/data/sporthive.sqlite"


def parse_duration(value: str | None) -> float | None:
    """'12.954' | '1:46.762' | '1:29:32.290' -> seconds."""
    if not value:
        return None
    total = 0.0
    for part in value.split(":"):
        total = total * 60 + float(part)
    return total


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript((ROOT / "sql" / "schema.sql").read_text())
    conn.executescript((ROOT / "sql" / "views.sql").read_text())
    chips.load_into(conn)
    return conn


def download_db(db_path: Path = DEFAULT_DB, url: str = RELEASE_DB_URL) -> None:
    """Fetch the latest published database (replaces the local copy)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(".download")
    with requests.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in resp.iter_content(1 << 20):
                f.write(chunk)
    tmp.replace(db_path)


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    """
    Open the database without ever writing to it, so dashboards can run while
    ingest.py is loading. The current views.sql and chips.csv are applied as TEMP
    objects, which shadow the stored ones for this connection only.
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    conn.execute("""CREATE TEMP TABLE chip_assignments (
        chip_code TEXT NOT NULL, skater TEXT NOT NULL, valid_from TEXT, valid_to TEXT, note TEXT)""")
    views = (ROOT / "sql" / "views.sql").read_text()
    conn.executescript(views.replace("DROP VIEW IF EXISTS ", "DROP VIEW IF EXISTS temp.")
                            .replace("CREATE VIEW ", "CREATE TEMP VIEW "))
    chips.load_into(conn)
    return conn


def load_activity(conn: sqlite3.Connection, location_id: int, activity: dict, data: dict) -> int:
    activity_id = activity["id"]
    stats = data.get("stats") or {}
    conn.execute("DELETE FROM laps WHERE activity_id = ?", (activity_id,))
    conn.execute("DELETE FROM sessions WHERE activity_id = ?", (activity_id,))
    conn.execute(
        "INSERT OR REPLACE INTO activities VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            activity_id, location_id, activity.get("chipLabel"), activity.get("chipCode"),
            sporthive._parse_start_date(activity).isoformat(),
            activity.get("startTime"), activity.get("endTime"),
            stats.get("lapCount"), parse_duration(stats.get("fastestTime")),
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )
    lap_rows = []
    for s in data.get("sessions", []):
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?)",
            (activity_id, s["id"], s.get("dateTimeStart"), parse_duration(s.get("duration"))),
        )
        for lap in s.get("laps", []):
            lap_rows.append((
                activity_id, s["id"], lap["nr"], lap.get("dateTimeStart"),
                parse_duration(lap.get("duration")),
                (lap.get("speed") or {}).get("kph"), lap.get("status"),
            ))
    conn.executemany("INSERT INTO laps VALUES (?,?,?,?,?,?,?)", lap_rows)
    return len(lap_rows)


def run(db_path: Path, location_id: int, start: date | None, end: date | None) -> None:
    conn = connect(db_path)

    if start is None:  # incremental: re-pull the last loaded day onward
        last = conn.execute("SELECT MAX(activity_date) FROM activities").fetchone()[0]
        start = date.fromisoformat(last) if last else date.today() - timedelta(days=6)
    end = end or date.today()
    print(f"Loading location {location_id}, {start} -> {end} into {db_path}")

    # Skip everything already loaded, except the newest day (it may have been partial).
    known = {r[0] for r in conn.execute(
        "SELECT activity_id FROM activities "
        "WHERE activity_date < (SELECT MAX(activity_date) FROM activities)")}
    loaded = skipped = failed = laps = 0
    for activity in sporthive.iter_activities(location_id, start, end):
        if activity["id"] in known:
            skipped += 1
            continue
        try:
            data = sporthive.fetch_sessions(activity["id"])
        except RuntimeError as exc:  # not saved, so the next run retries it
            failed += 1
            print(f"  ! skipping activity {activity['id']}: {exc}")
            continue
        laps += load_activity(conn, location_id, activity, data)
        loaded += 1
        if loaded % 50 == 0:
            conn.commit()
            print(f"  {loaded} activities, {laps} laps ... ({activity['startTime'][:10]})")
        time.sleep(sporthive.POLITE_DELAY_SECS)

    conn.commit()
    conn.close()
    print(f"Done: {loaded} activities / {laps} laps loaded, {skipped} already loaded, {failed} failed.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--location-id", type=int, default=DEFAULT_LOCATION)
    p.add_argument("--start-date", type=date.fromisoformat, default=None)
    p.add_argument("--end-date", type=date.fromisoformat, default=None)
    p.add_argument("--download", action="store_true",
                   help="Replace the local database with the latest published one, then exit.")
    args = p.parse_args()
    if args.download:
        download_db(args.db)
        print(f"Downloaded {RELEASE_DB_URL} -> {args.db}")
        return
    run(args.db, args.location_id, args.start_date, args.end_date)


if __name__ == "__main__":
    main()
