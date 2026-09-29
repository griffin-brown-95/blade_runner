-- Metric layer. Plain SQL so it ports to Snowflake/DuckDB/dbt later unchanged
-- (apart from the DROP/CREATE syntax).

DROP VIEW IF EXISTS skater_day;
CREATE VIEW skater_day AS
SELECT
    a.activity_id,
    a.activity_date,
    a.chip_label,
    COALESCE(c.skater, a.chip_label)          AS skater,
    COUNT(DISTINCT l.session_nr)              AS sessions,
    COUNT(l.lap_nr)                           AS laps,
    MIN(l.duration_sec)                       AS fastest_lap_sec,
    ROUND(AVG(l.duration_sec), 3)             AS avg_lap_sec,
    ROUND(SUM(l.duration_sec) / 60.0, 1)      AS on_ice_min
FROM activities a
LEFT JOIN chips c USING (chip_label)
LEFT JOIN laps  l USING (activity_id)
GROUP BY a.activity_id;

DROP VIEW IF EXISTS skater_totals;
CREATE VIEW skater_totals AS
SELECT
    skater,
    chip_label,
    COUNT(DISTINCT activity_date)  AS training_days,
    SUM(sessions)                  AS sessions,
    SUM(laps)                      AS laps,
    MIN(fastest_lap_sec)           AS fastest_lap_sec,
    MIN(activity_date)             AS first_day,
    MAX(activity_date)             AS last_day
FROM skater_day
GROUP BY skater, chip_label;
