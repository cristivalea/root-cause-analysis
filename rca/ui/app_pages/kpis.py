"""KPIs: the place for the indicators of the RCA process.

The indicators are not defined yet (final_project_prompt.md, section 8): the page says so and shows no number,
so nothing here can be read as a measure the application does not make.
"""

import streamlit as st

from rca.ui import navigation, theme
from rca.ui.components.page_header import page_header
from rca.ui.strings import t

page_header(t("kpis.title"), t("kpis.subtitle"))
st.info(t("kpis.not_defined"), icon=":material/info:")
st.caption(t("kpis.meanwhile"))
with st.container(horizontal=True):
    st.page_link(navigation.PROBLEMS, label=t("nav.problems"), icon=theme.ICONS["problems"])
    st.page_link(navigation.HISTORY, label=t("nav.history"), icon=theme.ICONS["history"])
