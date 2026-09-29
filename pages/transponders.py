"""Manage transponder -> skater assignments (writes data/chips.csv)."""

import pandas as pd
import streamlit as st

import chips
from ingest import DEFAULT_DB, connect

st.set_page_config(page_title="Transponders", layout="wide")
st.title("Transponders")
st.caption(
    "Each row: this transponder belonged to this skater between these dates (inclusive). "
    "Leave *valid_to* blank if they still have it. When a transponder is replaced, end the old "
    "row the day before and add a new row for the new transponder. The old laps stay with the skater."
)

conn = connect(DEFAULT_DB)
seen = pd.read_sql("""
    SELECT chip_code, MAX(chip_label) AS sporthive_label, skater,
           COUNT(DISTINCT activity_date) AS days, MIN(activity_date) AS first_seen, MAX(activity_date) AS last_seen
    FROM skater_day GROUP BY chip_code""", conn)
conn.close()

rows = pd.DataFrame(chips.read(), columns=chips.FIELDS)
for col in ("valid_from", "valid_to"):
    rows[col] = pd.to_datetime(rows[col].replace("", None)).dt.date

edited = st.data_editor(
    rows, num_rows="dynamic", use_container_width=True, hide_index=True,
    column_config={
        "chip_code": st.column_config.SelectboxColumn("Transponder", options=sorted(seen["chip_code"]), required=True),
        "skater": st.column_config.TextColumn("Skater", required=True),
        "valid_from": st.column_config.DateColumn("Valid from"),
        "valid_to": st.column_config.DateColumn("Valid to"),
        "note": st.column_config.TextColumn("Note"),
    },
)

if st.button("Save to data/chips.csv", type="primary"):
    out = edited.dropna(how="all").copy()
    for col in ("valid_from", "valid_to"):
        out[col] = out[col].map(lambda d: d.isoformat() if pd.notna(d) else "")
    records = [{k: ("" if pd.isna(v) else str(v)).strip() for k, v in r.items()} for r in out.to_dict("records")]
    try:
        chips.write(records)
    except ValueError as e:
        st.error(f"Not saved:\n\n{e}")
    else:
        st.cache_data.clear()
        st.success(f"Saved {len(records)} assignments. Commit data/chips.csv to publish them.")

st.subheader("Transponders without an assignment")
st.caption("Seen on the ice but not in chips.csv. Most are one-off visitors; add the ones that are team members.")
unassigned = seen[~seen["chip_code"].isin(rows["chip_code"])].sort_values("days", ascending=False)
st.dataframe(unassigned.drop(columns="skater"), use_container_width=True, hide_index=True)
