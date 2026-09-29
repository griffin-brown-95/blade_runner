import pandas as pd
import streamlit as st

from app import charts, data

all_days = data.all_days()
days = data.filtered(all_days)
st.title("Team")
st.caption(f"{st.session_state.get('season')} · UOO short track (111 m)")
if days.empty:
    st.info("No laps for this selection.")
    st.stop()

data.kpis(days, {"Skaters": f"{days['skater'].nunique():,}"})
speed, volume, board, seasons = st.tabs(["Speed", "Volume & lap quality", "Leaderboard", "Seasons"])

with speed:
    grain = data.pick_grain(days, "team_speed_grain")
    compare = st.multiselect("Compare skaters (best-5 average)", sorted(days["skater"].dropna().unique()),
                             placeholder="Team best")
    if compare:
        b = data.bucket(days[days["skater"].isin(compare)], grain, by=["skater"])
        st.altair_chart(charts.speed_trend(b, grain, color="skater"), use_container_width=True)
    else:
        st.altair_chart(charts.speed_trend(data.bucket(days, grain), grain), use_container_width=True)

with volume:
    grain = data.pick_grain(days, "team_volume_grain")
    st.altair_chart(charts.volume(data.bucket(days, grain), grain, classes=True), use_container_width=True)
    st.caption("All laps in this period by class")
    hist = data.query("""
        SELECT CAST(l.duration_sec * 4 AS INT) / 4.0 AS bin, l.lap_class, COUNT(*) AS laps
        FROM laps_classified l JOIN skater_day d USING (activity_id)
        WHERE d.activity_date BETWEEN ? AND ? AND (d.skater IS NOT NULL OR ? = 0)
        GROUP BY 1, 2""", (days["activity_date"].min().date().isoformat(),
                           days["activity_date"].max().date().isoformat(),
                           int(st.session_state.get("named_only", True))))
    st.altair_chart(charts.lap_histogram(hist, data.rules()), use_container_width=True)

with board:
    by = st.radio("Rows", ["skater", "chip_code"], horizontal=True, label_visibility="collapsed",
                  format_func={"skater": "By skater", "chip_code": "By transponder"}.get)
    table = data.summary(days, by)
    event = st.dataframe(table, use_container_width=True, on_select="rerun", selection_mode="single-row",
                         column_config={"last_seen": st.column_config.DateColumn("last_seen")})
    st.caption("Select a row to open that skater.")
    if by == "skater" and event.selection.rows:
        picked = table.index[event.selection.rows[0]]
        if picked != "unassigned":
            st.session_state["skater"] = picked
            st.switch_page("app/views/skater.py")

with seasons:
    st.caption("Across all seasons, regardless of the season filter.")
    named = all_days[all_days["skater"].notna()] if st.session_state.get("named_only", True) else all_days
    per_season = (named.groupby("season")
                  .agg(training_days=("activity_date", "nunique"), skaters=("skater", "nunique"),
                       sessions=("sessions", "sum"), valid_laps=("laps", "sum"),
                       team_best5_sec=("best5_avg_sec", "min"))
                  .sort_index(ascending=False))
    st.dataframe(per_season, use_container_width=True)
    st.caption("Each skater's best-5 average per season")
    st.dataframe(named.pivot_table(index="skater", columns="season", values="best5_avg_sec", aggfunc="min")
                 .sort_index(axis=1, ascending=False), use_container_width=True)
