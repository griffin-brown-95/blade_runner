-- Metric layer. Plain SQL so it ports to Snowflake/DuckDB/dbt later unchanged
-- (apart from the DROP/CREATE syntax).

-- One row per chip per day, attributed to whoever held the chip that day.
-- Chips listed in chips.csv are governed by it entirely; for chips not listed, fall
-- back to the Sporthive label when it's a name rather than the raw code.
DROP VIEW IF EXISTS skater_day;
CREATE VIEW skater_day AS
SELECT
    a.activity_id,
    a.activity_date,
    a.chip_code,
    a.chip_label,
    CASE WHEN ca.skater IS NOT NULL THEN ca.skater
         WHEN a.chip_code NOT IN (SELECT chip_code FROM chip_assignments)
         THEN NULLIF(a.chip_label, a.chip_code)
    END                                        AS skater,
    CASE WHEN ca.skater IS NOT NULL THEN 'chips.csv'
         WHEN a.chip_code NOT IN (SELECT chip_code FROM chip_assignments)
          AND a.chip_label <> a.chip_code THEN 'sporthive label'
    END                                        AS skater_source,
    COUNT(DISTINCT l.session_nr)               AS sessions,
    COUNT(l.lap_nr)                            AS laps,
    MIN(l.duration_sec)                        AS fastest_lap_sec,
    ROUND(AVG(l.duration_sec), 3)              AS avg_lap_sec,
    ROUND(SUM(l.duration_sec) / 60.0, 1)       AS on_ice_min
FROM activities a
LEFT JOIN chip_assignments ca
       ON ca.chip_code = a.chip_code
      AND a.activity_date BETWEEN COALESCE(ca.valid_from, '0000-01-01')
                              AND COALESCE(ca.valid_to,   '9999-12-31')
LEFT JOIN laps l ON l.activity_id = a.activity_id
GROUP BY a.activity_id;

-- Per skater, across every chip they've held. Unassigned chips are excluded.
DROP VIEW IF EXISTS skater_totals;
CREATE VIEW skater_totals AS
SELECT
    skater,
    GROUP_CONCAT(DISTINCT chip_code)  AS chips,
    COUNT(DISTINCT activity_date)     AS training_days,
    SUM(sessions)                     AS sessions,
    SUM(laps)                         AS laps,
    MIN(fastest_lap_sec)              AS fastest_lap_sec,
    MIN(activity_date)                AS first_day,
    MAX(activity_date)                AS last_day
FROM skater_day
WHERE skater IS NOT NULL
GROUP BY skater;

-- Per transponder, with who has held it.
DROP VIEW IF EXISTS chip_totals;
CREATE VIEW chip_totals AS
SELECT
    chip_code,
    MAX(chip_label)                   AS chip_label,
    GROUP_CONCAT(DISTINCT skater)     AS skaters,
    COUNT(DISTINCT activity_date)     AS training_days,
    SUM(laps)                         AS laps,
    MIN(activity_date)                AS first_day,
    MAX(activity_date)                AS last_day
FROM skater_day
GROUP BY chip_code;
