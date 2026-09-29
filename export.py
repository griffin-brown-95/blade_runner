#!/usr/bin/env python3
"""Export the metric views from SQLite to site/data.json for the static dashboard."""

import json
import sqlite3
from pathlib import Path

from ingest import DEFAULT_DB, ROOT

OUT = ROOT / "site" / "data.json"


def rows(conn: sqlite3.Connection, sql: str) -> list[dict]:
    cur = conn.execute(sql)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def main():
    conn = sqlite3.connect(DEFAULT_DB)
    conn.executescript((ROOT / "sql" / "views.sql").read_text())
    payload = {
        "generated_at": conn.execute("SELECT MAX(scraped_at) FROM activities").fetchone()[0],
        "totals": rows(conn, "SELECT * FROM skater_totals ORDER BY laps DESC"),
        "days": rows(conn, """
            SELECT activity_date, skater, sessions, laps, fastest_lap_sec, avg_lap_sec, on_ice_min
            FROM skater_day WHERE laps > 0 ORDER BY activity_date, skater"""),
    }
    OUT.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"Wrote {OUT} ({len(payload['totals'])} skaters, {len(payload['days'])} skater-days)")


if __name__ == "__main__":
    main()
