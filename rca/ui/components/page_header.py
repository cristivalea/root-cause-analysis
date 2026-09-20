"""The top of a screen: where you are, what it is for, and the way back.

Every screen starts with this, so the answer to "where am I" is always in the same place.
"""

import streamlit as st

from rca.ui import navigation, theme
from rca.ui.strings import t


def page_header(
    title: str,
    subtitle: str | None = None,
    *,
    back_to: str | None = None,
    back_label: str | None = None,
) -> None:
    """A screen title, the sentence that explains it, and an optional link back."""
    if back_to is not None:
        st.page_link(back_to, label=back_label or t("nav.back_to_home"), icon=theme.ICONS["back"])
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def home_header(title: str, subtitle: str | None = None) -> None:
    """The header of a screen reached from the home page."""
    page_header(title, subtitle, back_to=navigation.HOME)
