#!/usr/bin/env python3
"""
Transponder -> skater assignments, stored in data/chips.csv (the source of truth).

Each row says "chip X belonged to skater Y from valid_from to valid_to (inclusive)".
Leave valid_to blank for "still assigned". A skater can hold several chips, and a
chip can move between skaters over time -- just not two skaters on the same day.

    python chips.py list
    python chips.py seed                              # start from Sporthive's own chip labels
    python chips.py assign LS-12345 "Ben" --from 2026-10-01
    python chips.py assign LS-99999 "Ben" --from 2026-10-15 --replaces LS-12345
"""

import argparse
import csv
import sqlite3
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
CHIPS_CSV = ROOT / "data" / "chips.csv"
FIELDS = ["chip_code", "skater", "valid_from", "valid_to", "note"]


def read(path: Path = CHIPS_CSV) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return [{k: (r.get(k) or "").strip() for k in FIELDS} for r in csv.DictReader(f)]


def validate(rows: list[dict]) -> list[str]:
    """Return a list of problems; empty means the file is good."""
    errors = []
    by_chip: dict[str, list[tuple[str, str]]] = {}
    for i, r in enumerate(rows, start=2):  # line 1 is the header
        if not r["chip_code"] or not r["skater"]:
            errors.append(f"line {i}: chip_code and skater are required")
            continue
        for col in ("valid_from", "valid_to"):
            if r[col]:
                try:
                    date.fromisoformat(r[col])
                except ValueError:
                    errors.append(f"line {i}: {col} '{r[col]}' is not YYYY-MM-DD")
        lo, hi = r["valid_from"] or "0000-01-01", r["valid_to"] or "9999-12-31"
        if lo > hi:
            errors.append(f"line {i}: valid_from is after valid_to")
        for other_lo, other_hi in by_chip.get(r["chip_code"], []):
            if lo <= other_hi and other_lo <= hi:
                errors.append(f"line {i}: {r['chip_code']} overlaps another assignment")
        by_chip.setdefault(r["chip_code"], []).append((lo, hi))
    return errors


def write(rows: list[dict], path: Path = CHIPS_CSV) -> None:
    errors = validate(rows)
    if errors:
        raise ValueError("\n".join(errors))
    rows = sorted(rows, key=lambda r: (r["skater"].lower(), r["valid_from"], r["chip_code"]))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def load_into(conn: sqlite3.Connection, path: Path = CHIPS_CSV) -> None:
    """Replace the chip_assignments table with the CSV contents."""
    rows = read(path)
    errors = validate(rows)
    if errors:
        raise ValueError(f"{path} is invalid:\n" + "\n".join(errors))
    conn.execute("DELETE FROM chip_assignments")
    conn.executemany(
        "INSERT INTO chip_assignments VALUES (?,?,?,?,?)",
        [(r["chip_code"], r["skater"], r["valid_from"] or None, r["valid_to"] or None, r["note"] or None)
         for r in rows],
    )
    conn.commit()


def seed(conn: sqlite3.Connection) -> int:
    """Add a row for every chip whose Sporthive label is a name rather than its code."""
    rows = read()
    known = {r["chip_code"] for r in rows}
    new = [
        {"chip_code": code, "skater": label, "valid_from": first, "valid_to": "",
         "note": "seeded from Sporthive label"}
        for code, label, first in conn.execute("""
            SELECT chip_code, chip_label, MIN(activity_date) FROM activities
            WHERE chip_label <> chip_code GROUP BY chip_code, chip_label""")
        if code not in known
    ]
    write(rows + new)
    return len(new)


def assign(chip_code: str, skater: str, start: date, replaces: str | None) -> None:
    rows = read()
    day_before = (start - timedelta(days=1)).isoformat()
    for r in rows:
        # Close any open assignment on this chip, and on the chip it replaces.
        if r["chip_code"] in (chip_code, replaces) and not r["valid_to"] and r["valid_from"] < start.isoformat():
            r["valid_to"] = day_before
    rows.append({"chip_code": chip_code, "skater": skater, "valid_from": start.isoformat(),
                 "valid_to": "", "note": f"replaces {replaces}" if replaces else ""})
    write(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("seed")
    a = sub.add_parser("assign")
    a.add_argument("chip_code")
    a.add_argument("skater")
    a.add_argument("--from", dest="start", type=date.fromisoformat, default=date.today())
    a.add_argument("--replaces", help="old chip_code; its assignment ends the day before --from")
    args = p.parse_args()

    if args.cmd == "list":
        for r in read():
            print(f"{r['chip_code']:<10} {r['skater']:<20} {r['valid_from'] or '…'} -> {r['valid_to'] or 'now'}  {r['note']}")
    elif args.cmd == "seed":
        from ingest import DEFAULT_DB, connect
        print(f"Added {seed(connect(DEFAULT_DB))} chips to {CHIPS_CSV}")
    elif args.cmd == "assign":
        assign(args.chip_code, args.skater, args.start, args.replaces)
        print(f"{args.chip_code} -> {args.skater} from {args.start}")


if __name__ == "__main__":
    main()
