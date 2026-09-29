"""
Blade Runner: Streamlit explorer over data/sporthive.sqlite.

    streamlit run streamlit_app.py

Team  -> Skater -> Day -> Lap. The sidebar season filter applies to every page.
To move to Snowflake later, swap app/data.py's query() for a snowflake-connector
query against the same views (sql/views.sql); the pages don't change.
"""

import streamlit as st

from app import data

st.set_page_config(page_title="Blade Runner", layout="wide")

data.sidebar(data.all_days())
st.navigation({
    "Dashboards": [
        st.Page("app/views/team.py", title="Team", default=True),
        st.Page("app/views/skater.py", title="Skater"),
    ],
    "Admin": [st.Page("app/views/transponders.py", title="Transponders")],
}).run()
