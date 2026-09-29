-- Metric layer. Plain SQL so it ports to Snowflake/DuckDB/dbt later unchanged
-- (apart from the DROP/CREATE syntax).

-- Lap validity rules: the one place to tune what counts as a real 111 m lap.
-- Faster than min = shortened inside loop (resting, relay tag); slower than max = rest/cruise lap.
DROP VIEW IF EXISTS lap_rules;
CREATE VIEW lap_rules AS
SELECT 8.0 AS min_lap_sec, 11.0 AS max_lap_sec;

DROP VIEW IF EXISTS laps_classified;
CREATE VIEW laps_classified AS
SELECT
    l.*,
    CASE WHEN l.duration_sec < r.min_lap_sec THEN 'too_fast'
         WHEN l.duration_sec > r.max_lap_sec THEN 'too_slow'
         ELSE 'valid'
    END AS lap_class
FROM laps l CROSS JOIN lap_rules r;

-- One row per chip per day, attributed to whoever held the chip that day.
-- Chips listed in chips.csv are governed by it entirely; for chips not listed, fall
-- back to the Sporthive label when it's a name rather than the raw code.
-- Lap metrics use valid laps only; all_laps / short_laps / on_ice_min count everything.
DROP VIEW IF EXISTS skater_day;
CREATE VIEW skater_day AS
WITH lap_stats AS (
    SELECT
        activity_id,
        COUNT(*)                                                    AS all_laps,
        SUM(lap_class = 'too_fast')                                 AS short_laps,
        SUM(lap_class = 'valid')                                    AS laps,
        COUNT(DISTINCT CASE WHEN lap_class = 'valid' THEN session_nr END) AS sessions,
        MIN(CASE WHEN lap_class = 'valid' THEN duration_sec END)    AS fastest_lap_sec,
        ROUND(AVG(CASE WHEN lap_class = 'valid' THEN duration_sec END), 3) AS avg_lap_sec,
        ROUND(SUM(duration_sec) / 60.0, 1)                          AS on_ice_min
    FROM laps_classified
    GROUP BY activity_id
),
best5 AS (  -- mean of the day's 5 fastest valid laps; NULL if fewer than 5
    SELECT activity_id, ROUND(AVG(duration_sec), 3) AS best5_avg_sec
    FROM (
        SELECT activity_id, duration_sec,
               ROW_NUMBER() OVER (PARTITION BY activity_id ORDER BY duration_sec) AS rn
        FROM laps_classified WHERE lap_class = 'valid'
    )
    WHERE rn <= 5
    GROUP BY activity_id
    HAVING COUNT(*) = 5
)
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
    COALESCE(s.sessions, 0)                    AS sessions,
    COALESCE(s.laps, 0)                        AS laps,
    s.fastest_lap_sec,
    b.best5_avg_sec,
    s.avg_lap_sec,
    COALESCE(s.all_laps, 0)                    AS all_laps,
    COALESCE(s.short_laps, 0)                  AS short_laps,
    s.on_ice_min
FROM activities a
LEFT JOIN chip_assignments ca
       ON ca.chip_code = a.chip_code
      AND a.activity_date BETWEEN COALESCE(ca.valid_from, '0000-01-01')
                              AND COALESCE(ca.valid_to,   '9999-12-31')
LEFT JOIN lap_stats s ON s.activity_id = a.activity_id
LEFT JOIN best5     b ON b.activity_id = a.activity_id;

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
    MIN(best5_avg_sec)                AS best5_avg_sec,
    SUM(all_laps - laps)              AS filtered_laps,
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
