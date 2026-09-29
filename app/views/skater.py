import altair as alt
import pandas as pd
import streamlit as st

from app import charts, data

all_days = data.all_days()
skaters = sorted(all_days["skater"].dropna().unique())
if st.session_state.get("skater") not in skaters:
    st.session_state["skater"] = skaters[0]

st.title("Skater")
skater = st.selectbox("Skater", skaters, key="skater", label_visibility="collapsed")
mine_all = all_days[all_days["skater"] == skater]
mine = data.filtered(mine_all)
st.caption(f"{st.session_state.get('season')} · transponders: {', '.join(sorted(mine_all['chip_code'].unique()))}")

if mine.empty:
    st.info(f"No laps for {skater} in {st.session_state.get('season')}.")
else:
    data.kpis(mine)

trends, quality, day, seasons = st.tabs(["Trends", "Lap quality", "Day detail", "Seasons"])

with trends:
    if not mine.empty:
        grain = data.pick_grain(mine, "skater_trend_grain")
        b = data.bucket(mine, grain)
        st.markdown("**Fastest lap and best-5 average**")
        st.altair_chart(charts.speed_trend(b, grain), use_container_width=True)
        st.markdown("**Valid laps**")
        st.altair_chart(charts.volume(b, grain), use_container_width=True)

with quality:
    if not mine.empty:
        grain = data.pick_grain(mine, "skater_quality_grain")
        st.altair_chart(charts.volume(data.bucket(mine, grain), grain, classes=True), use_container_width=True)
        hist = data.query("""
            SELECT CAST(l.duration_sec * 4 AS INT) / 4.0 AS bin, l.lap_class, COUNT(*) AS laps
            FROM laps_classified l JOIN skater_day d USING (activity_id)
            WHERE d.skater = ? AND d.activity_date BETWEEN ? AND ?
            GROUP BY 1, 2""", (skater, mine["activity_date"].min().date().isoformat(),
                               mine["activity_date"].max().date().isoformat()))
        st.altair_chart(charts.lap_histogram(hist, data.rules()), use_container_width=True)

with day:
    if not mine.empty:
        options = mine.sort_values("activity_date", ascending=False).to_dict("records")
        row = st.selectbox("Day", options, format_func=lambda r: (
            f"{r['activity_date']:%a %b %d, %Y} · {r['laps']} valid / {r['all_laps']} laps · {r['chip_code']}"))
        laps = data.query("SELECT session_nr, lap_nr, start_time, duration_sec, lap_class FROM laps_classified "
                          "WHERE activity_id = ? ORDER BY session_nr, lap_nr", (row["activity_id"],))
        c = st.columns(4)
        c[0].metric("Sessions", row["sessions"])
        c[1].metric("Valid laps", f"{row['laps']} / {row['all_laps']}")
        c[2].metric("Fastest lap", f"{row['fastest_lap_sec']:.3f}s" if pd.notna(row["fastest_lap_sec"]) else "–")
        c[3].metric("Best-5 average", f"{row['best5_avg_sec']:.3f}s" if pd.notna(row["best5_avg_sec"]) else "–")
        st.caption("Each bar is one lap in order; gaps separate sessions.")
        st.altair_chart(charts.lap_sequence(laps, data.rules()), use_container_width=True)
        with st.expander("Lap table"):
            st.dataframe(laps, use_container_width=True, hide_index=True)

with seasons:
    st.caption("Across all seasons, regardless of the season filter.")
    per_season = (mine_all.groupby("season")
                  .agg(training_days=("activity_date", "nunique"), sessions=("sessions", "sum"),
                       valid_laps=("laps", "sum"), fastest_lap_sec=("fastest_lap_sec", "min"),
                       best5_avg_sec=("best5_avg_sec", "min"))
                  .sort_index(ascending=False))
    st.dataframe(per_season, use_container_width=True)
    # Weekly best-5 lined up by week-of-season, so seasons overlay directly.
    w = data.bucket(mine_all.assign(season=mine_all["season"]), "Week", by=["season"])
    w["week"] = ((w["period"] - w["season"].map(data.season_start)).dt.days // 7) + 1
    st.markdown("**Best-5 average by week of season**")
    st.altair_chart(alt.Chart(w.dropna(subset=["best5_avg_sec"])).mark_line(point=True).encode(
        x=alt.X("week:Q", title="Week of season (from Jul 1)"),
        y=alt.Y("best5_avg_sec:Q", title="Best-5 average (s)", scale=alt.Scale(zero=False)),
        color=alt.Color("season:N", title=None, sort="descending"),
        tooltip=["season", "week", alt.Tooltip("best5_avg_sec:Q", format=".3f")]), use_container_width=True)
