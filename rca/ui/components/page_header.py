"""The top of a screen: where you are and what it is for.

Every screen starts with this, so the answer to "where am I" is always in the same place.
The way back is the navigation at the top of the page, which is on every screen already.
"""

import streamlit as st


def page_header(title: str, subtitle: str | None = None) -> None:
    """A screen title and the sentence that explains it."""
    st.title(title)
    if subtitle:
        st.caption(subtitle)
