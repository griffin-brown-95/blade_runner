#!/usr/bin/env python3
"""Export skater-day metrics from SQLite to site/data.json for the static dashboard."""

import json
import sqlite3

from ingest import DEFAULT_DB, ROOT, connect

OUT = ROOT / "site" / "data.json"


def rows(conn: sqlite3.Connection, sql: str) -> list[dict]:
    cur = conn.execute(sql)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def main():
    conn = connect(DEFAULT_DB)  # also reloads data/chips.csv
    payload = {
        "generated_at": conn.execute("SELECT MAX(scraped_at) FROM activities").fetchone()[0],
        "days": rows(conn, """
            SELECT activity_date, chip_code, chip_label, skater,
                   sessions, laps, fastest_lap_sec, avg_lap_sec, on_ice_min
            FROM skater_day WHERE laps > 0 ORDER BY activity_date, chip_code"""),
    }
    OUT.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"Wrote {OUT} ({len(payload['days'])} chip-days)")


if __name__ == "__main__":
    main()
