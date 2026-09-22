"""The Root Cause Analysis interface.

Run it with:

    streamlit run rca/ui/main.py

This file is the shell: it sets the page up, decides which pages the current role can open,
draws the one control that is on every screen, and then runs the page. Everything the user
actually reads lives in the pages, the components and `strings.py`.

The older screens (`rca/app.py`, `rca/expert_app.py`) still run on their own and are left
untouched until each of them is replaced here.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from rca.ui import navigation, state, theme
from rca.ui.strings import t

st.set_page_config(
    page_title=t("app.name"),
    page_icon=theme.ICONS["start_rca"],
    layout="wide",
)

state.initialise()
theme.apply_layout()


def app_bar() -> None:
    """Who the person is working as, opposite the navigation at the top of the page."""
    with st.container(horizontal=True, horizontal_alignment="right", key="app-bar"):
        widget_key = state.role_widget_key()
        st.segmented_control(
            t("role.label"),
            options=list(state.ROLES),
            format_func=state.role_name,
            default=state.current_role(),
            key=widget_key,
            on_change=state.apply_role_selection,
            args=(widget_key,),
            help=t("role.help"),
        )


page = st.navigation(navigation.build_pages(state.current_role()), position="top")
app_bar()
page.run()
