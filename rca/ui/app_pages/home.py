"""Home: what this tool does, how an investigation works, and the one way to start it.

The page answers three questions and nothing else: what is this, what will happen, and what
do I do now. Everything else on the screen would compete with the answer.
"""

import streamlit as st

from rca.ui import navigation, services, state, theme
from rca.ui.strings import t

STEPS = ("home.step_1", "home.step_2", "home.step_3", "home.step_4")


def hero() -> None:
    """The name of the tool, what it is for, and the action that starts everything."""
    _, middle, _ = st.columns([1, 3, 1])
    with middle:
        st.title(t("home.title"), text_alignment="center")
        st.markdown(t("home.subtitle"), text_alignment="center")
        st.space("small")
        with st.container(horizontal=True, horizontal_alignment="center"):
            if st.button(
                t("home.cta"),
                type="primary",
                icon=theme.ICONS["start_rca"],
                help=t("home.cta_help"),
            ):
                st.switch_page(navigation.START_RCA)
        with st.container(horizontal=True, horizontal_alignment="center"):
            st.page_link(navigation.HISTORY, label=t("home.history_link"), icon=theme.ICONS["history"])


def how_it_works() -> None:
    """The four steps of an RCA, so nobody has to guess what the button leads to."""
    st.subheader(t("home.how_it_works"))
    for column, step in zip(st.columns(len(STEPS), gap="medium"), STEPS):
        with column, st.container(border=True, height="stretch"):
            st.markdown(f":gray[**{t(f'{step}.number')}**]")
            st.markdown(f"**{t(f'{step}.title')}**")
            st.caption(t(f"{step}.text"))
    st.caption(t("home.closing"))


def waiting_for_the_expert() -> None:
    """Only for the Technical Expert: how much is waiting, and the way to it.

    The number is read from the stored analyses, so the page never promises work that is
    not there. If the data cannot be read, the block simply does not appear.
    """
    if not state.is_technical_expert():
        return
    try:
        waiting = len(services.list_rcas(status="PENDING_REVIEW"))
    except services.ServiceError:
        return

    st.space("small")
    with st.container(border=True):
        if waiting == 0:
            st.markdown(t("home.expert.waiting_none"))
            return
        message = t("home.expert.waiting_one") if waiting == 1 else t("home.expert.waiting_many", count=waiting)
        st.markdown(f"**{message}**")
        if st.button(t("home.expert.open_review"), type="primary", icon=theme.ICONS["review"]):
            st.switch_page(navigation.REVIEW)


hero()
st.space("medium")
how_it_works()
waiting_for_the_expert()
