# Blade Runner

Practice-lap analytics for US Speedskating's short track group at the Utah Olympic Oval.
Lap timing comes from the public [Sporthive practice page](https://sporthive.com/practice/4607)
(MYLAPS transponders, 111 m lap).

```
Sporthive API ──► ingest.py ──► data/sporthive.sqlite ──► sql/views.sql (metrics)
                                                         ├─► export.py ► site/  (static dashboard, GitHub Pages)
                                                         └─► streamlit_app.py   (interactive, optional)
```

## Quick start

```bash
pip install -r requirements.txt
python ingest.py --start-date 2026-08-01 --end-date 2026-08-31   # backfill
python ingest.py                                                  # incremental after that
python export.py && python -m http.server -d site 8000           # static dashboard
streamlit run streamlit_app.py                                    # or the Streamlit version
```

## Data model

| Table        | Grain                                   |
|--------------|-----------------------------------------|
| `activities` | one transponder (chip) on one day       |
| `sessions`   | one continuous on-ice run in that day   |
| `laps`       | one 111 m lap                           |
| `chips`      | optional chip → skater name mapping     |

Views: `skater_day` (sessions, laps, fastest/avg lap per chip-day) and `skater_totals`
(training days, sessions, laps, fastest lap per skater).

## Deployment

`.github/workflows/scrape.yml` runs nightly: scrape → commit the SQLite file → publish `site/`
to GitHub Pages. Enable Pages with **Settings → Pages → Source: GitHub Actions**. No servers,
no secrets, no cloud accounts. To hand this to the team, they fork the repo and enable Pages.

## Known data caveats (to work through)

- A chip is a transponder, not a person. Chips get swapped/shared; fill `chips` to name them.
- Sessions are split by the timing system when a lap exceeds ~20 s; no lap is longer than that.
- Lap times mix warm-up, technique, and race-pace laps. Fastest-lap is robust; averages are not.
- The location includes non-team skaters (public sessions, other clubs).
