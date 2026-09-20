"""The pages of the application and how the user moves between them.

Navigation stays light on purpose: a few pages in a top bar, no tree, no dashboard. The
Technical Review page appears only while the person is working as a Technical Expert.

The paths are relative to `main.py`, which is what both `st.Page` and `st.page_link` expect.
"""

import streamlit as st

from rca.ui import state, theme
from rca.ui.strings import t

HOME = "app_pages/home.py"
START_RCA = "app_pages/start_rca.py"
INVESTIGATION = "app_pages/investigation.py"
REVIEW = "app_pages/review.py"
HISTORY = "app_pages/history.py"


def build_pages(role: state.Role) -> list[st.Page]:
    """The pages this role can open, in the order they appear in the top bar."""
    pages = [
        # The default page answers on "/", so it is not given a path of its own.
        st.Page(HOME, title=t("nav.home"), icon=theme.ICONS["home"], default=True),
        st.Page(START_RCA, title=t("nav.start_rca"), icon=theme.ICONS["start_rca"], url_path="start-rca"),
        st.Page(INVESTIGATION, title=t("nav.investigation"), icon=theme.ICONS["investigation"], url_path="investigation"),
    ]
    # The review page is always routable, so a link to a review still works tomorrow, in a
    # new session, whatever role the browser opens in. It is only listed in the bar for the
    # role whose work it is; the page itself says so and offers to switch.
    pages.append(
        st.Page(
            REVIEW,
            title=t("nav.review"),
            icon=theme.ICONS["review"],
            url_path="technical-review",
            visibility="visible" if role == state.TECHNICAL_EXPERT else "hidden",
        )
    )
    pages.append(
        st.Page(HISTORY, title=t("nav.history"), icon=theme.ICONS["history"], url_path="rca-history")
    )
    return pages
