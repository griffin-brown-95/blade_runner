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
| `chip_assignments` | loaded from `data/chips.csv` on every run |

Views: `skater_day` (per chip-day, attributed to whoever held the chip that day),
`skater_totals` (across all of a skater's chips) and `chip_totals`.

## Transponders → skaters

`data/chips.csv` is the source of truth. Transponders are keyed on `chip_code` (the hardware ID,
e.g. `LS-41603`), not Sporthive's editable label.

```csv
chip_code,skater,valid_from,valid_to,note
LS-41603,Ben,2026-08-03,2026-10-14,broke
LS-99999,Ben,2026-10-15,,replaces LS-41603
```

- Blank `valid_to` = still assigned. Dates are inclusive. A chip can't have two skaters on one day.
- Ben's laps on the old chip stay his; from Oct 15 the old chip is unassigned.
- Chips not in the CSV fall back to their Sporthive label if it's a name.

Three ways to edit it:
1. **GitHub web UI**: edit `data/chips.csv` in the browser. The workflow republishes the site.
2. **CLI**: `python chips.py assign LS-99999 "Ben" --from 2026-10-15 --replaces LS-41603`
3. **Streamlit**: the *Transponders* page is an editable table, with a list of chips seen but not yet assigned.

`python chips.py seed` adds every chip whose Sporthive label is a name.

## Deployment

`.github/workflows/scrape.yml` runs nightly: scrape → commit the SQLite file → publish `site/`
to GitHub Pages. Enable Pages with **Settings → Pages → Source: GitHub Actions**. No servers,
no secrets, no cloud accounts. To hand this to the team, they fork the repo and enable Pages.

## Known data caveats (to work through)

- Sessions are split by the timing system when a lap exceeds ~20 s; no lap is longer than that.
- Lap times mix warm-up, technique, and race-pace laps. Fastest-lap is robust; averages are not.
- The location includes non-team skaters (public sessions, other clubs).
