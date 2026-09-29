"""Altair chart builders shared across pages, so every view uses the same encodings."""

import altair as alt
import pandas as pd

CLASS_COLORS = alt.Scale(domain=["valid", "too_fast", "too_slow"], range=["#4c8df6", "#e15759", "#9a9a9a"])
SPEED_COLORS = alt.Scale(domain=["Fastest lap", "Best-5 average"], range=["#4c8df6", "#f28e2b"])
GRAIN_FORMAT = {"Day": "%b %d", "Week": "%b %d", "Month": "%b %Y"}


def speed_trend(b: pd.DataFrame, grain: str, color: str | None = None) -> alt.Chart:
    """Fastest lap and best-5 average per period. With `color`, one best-5 line per group."""
    x = alt.X("period:T", title=None, axis=alt.Axis(format=GRAIN_FORMAT[grain]))
    y = alt.Y("sec:Q", title="Lap time (s)", scale=alt.Scale(zero=False))
    if color:
        return alt.Chart(b.dropna(subset=["best5_avg_sec"])).mark_line(point=True).encode(
            x=x, y=alt.Y("best5_avg_sec:Q", title="Best-5 average (s)", scale=alt.Scale(zero=False)),
            color=alt.Color(f"{color}:N", title=None),
            tooltip=[color, alt.Tooltip("period:T"), alt.Tooltip("best5_avg_sec:Q", format=".3f")])
    long = b.melt(id_vars="period", value_vars=["fastest_lap_sec", "best5_avg_sec"], var_name="metric", value_name="sec")
    long["metric"] = long["metric"].map({"fastest_lap_sec": "Fastest lap", "best5_avg_sec": "Best-5 average"})
    return alt.Chart(long.dropna()).mark_line(point=True).encode(
        x=x, y=y, color=alt.Color("metric:N", scale=SPEED_COLORS, title=None, legend=alt.Legend(orient="top")),
        strokeDash=alt.StrokeDash("metric:N", legend=None),
        tooltip=["metric", alt.Tooltip("period:T"), alt.Tooltip("sec:Q", format=".3f")])


def volume(b: pd.DataFrame, grain: str, classes: bool = False) -> alt.Chart:
    """Laps per period; with classes=True, stacked valid / too_fast / too_slow."""
    x = alt.X("period:T", title=None, axis=alt.Axis(format=GRAIN_FORMAT[grain]))
    cols = ["valid", "too_fast", "too_slow"] if classes else ["valid"]
    long = b.melt(id_vars="period", value_vars=cols, var_name="lap_class", value_name="laps")
    return alt.Chart(long).mark_bar().encode(
        x=x, y=alt.Y("sum(laps):Q", title="Laps"),
        color=alt.Color("lap_class:N", scale=CLASS_COLORS, title=None,
                        legend=alt.Legend(orient="top") if classes else None),
        order=alt.Order("lap_class:N", sort="descending"),
        tooltip=[alt.Tooltip("period:T"), "lap_class", alt.Tooltip("sum(laps):Q", title="laps")])


def lap_histogram(h: pd.DataFrame, rules) -> alt.Chart:
    bars = alt.Chart(h).mark_bar().encode(
        x=alt.X("bin:Q", title="Lap time (s)", bin=alt.Bin(step=0.25), scale=alt.Scale(domain=[6, 20])),
        y=alt.Y("sum(laps):Q", title="Laps"),
        color=alt.Color("lap_class:N", scale=CLASS_COLORS, title=None, legend=alt.Legend(orient="top")))
    lines = alt.Chart(pd.DataFrame({"x": [rules.min_lap_sec, rules.max_lap_sec]})).mark_rule(strokeDash=[4, 3]).encode(x="x")
    return bars + lines


def lap_sequence(laps: pd.DataFrame, rules) -> alt.Chart:
    """Every lap of one day in order, a gap between sessions."""
    laps = laps.copy()
    laps["i"] = range(len(laps))
    laps["i"] += laps["session_nr"].rank(method="dense").astype(int) * 2
    bars = alt.Chart(laps).mark_bar(clip=True).encode(
        x=alt.X("i:O", axis=None),
        y=alt.Y("duration_sec:Q", title="Lap (s)", scale=alt.Scale(domain=[6, 20])),
        color=alt.Color("lap_class:N", scale=CLASS_COLORS, title=None, legend=alt.Legend(orient="top")),
        tooltip=["session_nr", "lap_nr", alt.Tooltip("duration_sec", format=".3f"), "lap_class"])
    lines = alt.Chart(pd.DataFrame({"y": [rules.min_lap_sec, rules.max_lap_sec]})).mark_rule(strokeDash=[4, 3]).encode(y="y")
    return bars + lines
