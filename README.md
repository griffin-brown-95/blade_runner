# Blade Runner

Practice-lap analytics for US Speedskating's short track group at the Utah Olympic Oval.
Lap timing comes from the public [Sporthive practice page](https://sporthive.com/practice/4607)
(MYLAPS transponders, 111 m lap).

## Why

The goal is to track each skater's **progress** and **training load**. The lap data already
existed, but getting it into a usable shape was slow: download CSV exports from the timing site
by hand, then clean, merge and chart everything in Excel, every week. That time went to data prep
instead of athletes.

Blade Runner automates that loop. Laps are pulled nightly into one consistent model of skaters,
sessions and laps, and the dashboard is current whenever the coaches open it.

On-ice laps are only one part of an athlete's load. This is the foundation for bringing in gym,
heart-rate and wellness data so the staff can balance total load against progress on the ice.

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

## Streamlit app

Organised as zoom levels so it stays usable over many seasons: **Team → Skater → Day → Lap**.
The sidebar season filter (seasons run Jul 1 – Jun 30) applies everywhere, and charts
default to daily, weekly or monthly buckets depending on the span shown.

| Page | Tabs |
|------|------|
| Team | Speed (team best or compare skaters) · Volume & lap quality · Leaderboard (click → skater) · Seasons |
| Skater | Trends (fastest, best-5, valid laps) · Lap quality · Day detail (every lap in order) · Seasons (week-of-season overlay) |
| Transponders | Edit `data/chips.csv`, see unassigned chips |

Code: `streamlit_app.py` (navigation + sidebar), `app/data.py` (queries, caching, time buckets),
`app/charts.py` (shared Altair charts), `app/views/*.py` (pages).

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

`.github/workflows/scrape.yml` runs nightly, on demand, and when `data/chips.csv`, `site/`,
`sql/` or `export.py` change on `main`:

```
download sporthive.sqlite from the "data" release → ingest.py → export.py
  → upload sporthive.sqlite back to the release → deploy site/ to GitHub Pages
```

The database is **not** kept in git (a nightly commit of a ~70 MB binary would bloat the repo).
It lives as an asset on the [`data` release](https://github.com/griffin-brown-95/blade_runner/releases/tag/data).
Get the latest copy locally with:

```bash
python ingest.py --download
```

The Streamlit app downloads it automatically when it's missing (fresh clones, Streamlit Cloud).

Setup, once: **Settings → Pages → Source: GitHub Actions**, then **Actions → scrape-and-publish →
Run workflow**. The dashboard is served at https://griffin-brown-95.github.io/blade_runner/.
To hand this to the team, they fork the repo, enable Pages, and run the workflow once.

## Known data caveats (to work through)

- Sessions are split by the timing system when a lap exceeds ~20 s; no lap is longer than that.
- Practice block layout may make the practice lap shorter than the 111.12 m race line.
- The location includes non-team skaters (public sessions, other clubs).
