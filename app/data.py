"""Shared data access, filters and time bucketing for the Streamlit app."""

from datetime import date

import pandas as pd
import streamlit as st

import chips
from ingest import DEFAULT_DB, connect_readonly as connect, download_db

SEASON_START_MONTH = 7  # a season runs Jul 1 -> Jun 30, labelled "2026-27"
LAP_CLASSES = ["valid", "too_fast", "too_slow"]
GRAINS = {"Day": "D", "Week": "W-MON", "Month": "MS"}


def season_of(d: pd.Timestamp | date) -> str:
    start = d.year if d.month >= SEASON_START_MONTH else d.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def season_start(label: str) -> pd.Timestamp:
    return pd.Timestamp(int(label[:4]), SEASON_START_MONTH, 1)


if not DEFAULT_DB.exists():  # fresh clone or Streamlit Cloud: fetch the published database
    with st.spinner("Downloading the latest lap database…"):
        download_db()


def _version() -> tuple:
    """Cache key: recompute whenever the database or chips.csv changes."""
    return (DEFAULT_DB.stat().st_mtime, chips.CHIPS_CSV.stat().st_mtime if chips.CHIPS_CSV.exists() else 0)


@st.cache_data(show_spinner="Loading laps…")
def _query(sql: str, params: tuple, _version: tuple) -> pd.DataFrame:
    conn = connect(DEFAULT_DB)
    try:
        return pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()


def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    return _query(sql, params, _version())


def rules() -> pd.Series:
    return query("SELECT * FROM lap_rules").iloc[0]


def all_days() -> pd.DataFrame:
    df = query("SELECT * FROM skater_day WHERE all_laps > 0").copy()
    df["activity_date"] = pd.to_datetime(df["activity_date"])
    df["season"] = df["activity_date"].map(season_of)
    df["too_slow_laps"] = df["all_laps"] - df["laps"] - df["short_laps"]
    return df


# ---- sidebar filters (rendered once in streamlit_app.py, read by every page) ----

RELATIVE_RANGES = {"Last 30 days": 30, "Last 90 days": 90, "Last 12 months": 365}


def sidebar(days: pd.DataFrame) -> None:
    seasons = [f"Season {s}" for s in sorted(days["season"].unique(), reverse=True)]
    options = ["All time", *RELATIVE_RANGES, *seasons, "Custom dates"]
    choice = st.sidebar.selectbox("Time range", options, key="range")
    if choice == "Custom dates":
        lo, hi = days["activity_date"].min().date(), days["activity_date"].max().date()
        st.sidebar.date_input("From – to", (lo, hi), min_value=lo, max_value=hi, key="custom_dates")
    st.sidebar.toggle("Named skaters only", value=True, key="named_only",
                      help="Hide transponders with no skater assigned (visitors, other clubs).")


def date_bounds() -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Inclusive (start, end) for the sidebar time range; None means unbounded."""
    choice = st.session_state.get("range", "All time")
    if choice in RELATIVE_RANGES:
        return pd.Timestamp(date.today()) - pd.Timedelta(days=RELATIVE_RANGES[choice] - 1), None
    if choice.startswith("Season "):
        start = season_start(choice.removeprefix("Season "))
        return start, start + pd.DateOffset(years=1) - pd.Timedelta(days=1)
    if choice == "Custom dates":
        picked = st.session_state.get("custom_dates", ())
        if len(picked) == 2:
            return pd.Timestamp(picked[0]), pd.Timestamp(picked[1])
    return None, None


def scope_label() -> str:
    choice = st.session_state.get("range", "All time")
    if choice == "Custom dates":
        lo, hi = date_bounds()
        return f"{lo:%b %d, %Y} – {hi:%b %d, %Y}" if lo is not None else "All time"
    return choice


def filtered(days: pd.DataFrame) -> pd.DataFrame:
    lo, hi = date_bounds()
    if lo is not None:
        days = days[days["activity_date"] >= lo]
    if hi is not None:
        days = days[days["activity_date"] <= hi]
    if st.session_state.get("named_only", True):
        days = days[days["skater"].notna()]
    return days


def pick_grain(days: pd.DataFrame, key: str) -> str:
    span = (days["activity_date"].max() - days["activity_date"].min()).days if len(days) else 0
    default = "Day" if span <= 45 else "Week" if span <= 400 else "Month"
    return st.radio("Group by", list(GRAINS), index=list(GRAINS).index(default),
                    horizontal=True, key=key, label_visibility="collapsed")


def bucket(days: pd.DataFrame, grain: str, by: list[str] | None = None) -> pd.DataFrame:
    """Roll skater-days up to Day / Week / Month periods."""
    freq = GRAINS[grain]
    keys = [pd.Grouper(key="activity_date", freq=freq)] + (by or [])
    out = (days.groupby(keys)
           .agg(training_days=("activity_date", "nunique"), skaters=("skater", "nunique"),
                sessions=("sessions", "sum"), valid=("laps", "sum"),
                too_fast=("short_laps", "sum"), too_slow=("too_slow_laps", "sum"),
                fastest_lap_sec=("fastest_lap_sec", "min"), best5_avg_sec=("best5_avg_sec", "min"))
           .reset_index().rename(columns={"activity_date": "period"}))
    return out[out["valid"] + out["too_fast"] + out["too_slow"] > 0]


def summary(days: pd.DataFrame, by: str) -> pd.DataFrame:
    other = "chip_code" if by == "skater" else "skater"
    return (days.fillna({"skater": "unassigned"}).groupby(by)
            .agg(**{other + "s": (other, lambda s: ", ".join(sorted(set(s))))},
                 training_days=("activity_date", "nunique"), sessions=("sessions", "sum"),
                 valid_laps=("laps", "sum"), fastest_lap_sec=("fastest_lap_sec", "min"),
                 best5_avg_sec=("best5_avg_sec", "min"), last_seen=("activity_date", "max"))
            .sort_values("valid_laps", ascending=False))


def kpis(days: pd.DataFrame, extra: dict | None = None) -> None:
    r = rules()
    filtered_laps = int((days["all_laps"] - days["laps"]).sum())
    items = {
        "Training days": f"{days['activity_date'].nunique():,}",
        "Sessions": f"{int(days['sessions'].sum()):,}",
        "Valid laps": f"{int(days['laps'].sum()):,}",
        "Fastest lap": f"{days['fastest_lap_sec'].min():.3f}s" if days["fastest_lap_sec"].notna().any() else "–",
        "Best-5 average": f"{days['best5_avg_sec'].min():.3f}s" if days["best5_avg_sec"].notna().any() else "–",
        **(extra or {}),
    }
    helps = {"Valid laps": f"Laps between {r.min_lap_sec}s and {r.max_lap_sec}s. {filtered_laps:,} others filtered.",
             "Best-5 average": "Mean of a day's 5 fastest valid laps; steadier than a single fastest lap."}
    for col, (label, value) in zip(st.columns(len(items)), items.items()):
        col.metric(label, value, help=helps.get(label))
