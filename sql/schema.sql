-- Raw tables: one row per API object. Loaded by ingest.py, never edited by hand.

CREATE TABLE IF NOT EXISTS activities (
    activity_id    INTEGER PRIMARY KEY,   -- one chip (transponder) on one day
    location_id    INTEGER NOT NULL,
    chip_label     TEXT,
    chip_code      TEXT,
    activity_date  TEXT NOT NULL,         -- local date, YYYY-MM-DD
    start_time     TEXT,
    end_time       TEXT,
    lap_count      INTEGER,
    fastest_lap_sec REAL,
    scraped_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    activity_id    INTEGER NOT NULL REFERENCES activities(activity_id),
    session_nr     INTEGER NOT NULL,      -- continuous on-ice run within the day
    start_time     TEXT,
    duration_sec   REAL,
    PRIMARY KEY (activity_id, session_nr)
);

CREATE TABLE IF NOT EXISTS laps (
    activity_id    INTEGER NOT NULL,
    session_nr     INTEGER NOT NULL,
    lap_nr         INTEGER NOT NULL,
    start_time     TEXT,
    duration_sec   REAL,
    speed_kph      REAL,
    status         TEXT,                  -- SESSIONBEST / FASTER / SLOWER ...
    PRIMARY KEY (activity_id, session_nr, lap_nr)
);

-- Loaded from data/chips.csv on every run (see chips.py). Do not edit here.
DROP TABLE IF EXISTS chips;
CREATE TABLE IF NOT EXISTS chip_assignments (
    chip_code      TEXT NOT NULL,
    skater         TEXT NOT NULL,
    valid_from     TEXT,                  -- NULL = since forever
    valid_to       TEXT,                  -- NULL = still assigned
    note           TEXT
);
