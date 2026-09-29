"""
Option B: Streamlit dashboard over the same SQLite database.

    streamlit run streamlit_app.py

To move to Snowflake later, swap `load()` for a snowflake-connector query
against the same views (sql/views.sql) -- the rest of the app is unchanged.
"""

import sqlite3

import pandas as pd
import streamlit as st

from ingest import DEFAULT_DB, ROOT

st.set_page_config(page_title="Blade Runner", layout="wide")


@st.cache_data(ttl=600)
def load(sql: str, params: tuple = ()) -> pd.DataFrame:
    with sqlite3.connect(DEFAULT_DB) as conn:
        conn.executescript((ROOT / "sql" / "views.sql").read_text())
        return pd.read_sql(sql, conn, params=params)


days = load("SELECT * FROM skater_day WHERE laps > 0")
days["activity_date"] = pd.to_datetime(days["activity_date"])

st.title("Blade Runner")
st.caption("US Speedskating practice laps, UOO short track (111 m)")

with st.sidebar:
    skaters = sorted(days["skater"].unique())
    picked = st.multiselect("Skaters", skaters)
    lo, hi = days["activity_date"].min().date(), days["activity_date"].max().date()
    date_range = st.date_input("Dates", (lo, hi), min_value=lo, max_value=hi)

view = days
if picked:
    view = view[view["skater"].isin(picked)]
if len(date_range) == 2:
    view = view[view["activity_date"].between(pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1]))]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Training days", view["activity_date"].nunique())
c2.metric("Sessions", int(view["sessions"].sum()))
c3.metric("Laps", int(view["laps"].sum()))
c4.metric("Fastest lap", f"{view['fastest_lap_sec'].min():.3f}s" if len(view) else "–")

st.subheader("Fastest lap by day")
trend = view.pivot_table(index="activity_date", columns="skater", values="fastest_lap_sec", aggfunc="min")
st.line_chart(trend if picked else trend.min(axis=1).rename("team best"))

st.subheader("Laps by day")
st.bar_chart(view.groupby("activity_date")["laps"].sum())

st.subheader("Skaters")
totals = (view.groupby("skater")
          .agg(training_days=("activity_date", "nunique"), sessions=("sessions", "sum"),
               laps=("laps", "sum"), fastest_lap_sec=("fastest_lap_sec", "min"),
               last_seen=("activity_date", "max"))
          .sort_values("laps", ascending=False))
st.dataframe(totals, use_container_width=True)

if len(picked) == 1:
    st.subheader(f"Laps: {picked[0]}")
    laps = load("""
        SELECT a.activity_date, l.session_nr, l.lap_nr, l.duration_sec, l.speed_kph, l.status
        FROM laps l JOIN skater_day a USING (activity_id)
        WHERE a.skater = ?
        ORDER BY a.activity_date, l.session_nr, l.lap_nr""", (picked[0],))
    st.dataframe(laps, use_container_width=True, hide_index=True)
