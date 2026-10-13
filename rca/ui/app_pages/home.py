"""Home: what this tool does, how an investigation works, and the one way to start it.

The page answers three questions and nothing else: what is this, what will happen, and what
do I do now. Everything else on the screen would compete with the answer.
"""

import streamlit as st

from rca.ui import formatting, navigation, services, state, theme
from rca.ui.strings import t

STEPS = ("home.step_1", "home.step_2", "home.step_3", "home.step_4")


# def hero() -> None:
#     """The name of the tool, what it is for, and the action that starts everything."""
#     _, middle, _ = st.columns([1, 3, 1])
#     with middle:
#         st.title(t("home.title"), text_alignment="center")
#         st.markdown(t("home.subtitle"), text_alignment="center")
#         st.space("small")
#         with st.container(horizontal=True, horizontal_alignment="center"):
#             if st.button(
#                 t("home.cta"),
#                 type="primary",
#                 icon=theme.ICONS["start_rca"],
#                 help=t("home.cta_help"),
#             ):
#                 st.switch_page(navigation.START_RCA)
#         with st.container(horizontal=True, horizontal_alignment="center"):
#             st.page_link(navigation.HISTORY, label=t("home.history_link"), icon=theme.ICONS["history"])

def hero() -> None:
    """Problem Manager: numele aplicației, scopul ei și acțiunea care pornește totul."""
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
                st.switch_page(navigation.PROBLEMS)
        with st.container(horizontal=True, horizontal_alignment="center"):
            st.page_link(navigation.HISTORY, label=t("home.history_link"), icon=theme.ICONS["history"])

def how_it_works() -> None:
    """The four steps of an RCA, so nobody has to guess what the button leads to."""
    st.header(t("home.how_it_works"))
    for column, step in zip(st.columns(len(STEPS), gap="medium"), STEPS):
        with column, st.container(border=True, height="stretch"):
            st.markdown(f":gray[**{t(f'{step}.number')}**]")
            st.markdown(f"**{t(f'{step}.title')}**")
            st.caption(t(f"{step}.text"))


# def waiting_for_the_expert() -> None:
#     """Only for the Technical Expert: how much is waiting, and the way to it.

#     The number is read from the stored analyses, so the page never promises work that is
#     not there. If the data cannot be read, the block simply does not appear.
#     """
#     # if not state.is_technical_expert():
#     #     return
#     # try:
#     #     waiting = len(services.list_rcas(status="AWAITING_TECHNICAL_REVIEW"))
#     # except services.ServiceError:
#     #     return

#     st.space("small")
#     with st.container(border=True):
#         if waiting == 0:
#             st.markdown(t("home.expert.waiting_none"))
#             return
#         message = t("home.expert.waiting_one") if waiting == 1 else t("home.expert.waiting_many", count=waiting)
#         st.markdown(f"**{message}**")
#         if st.button(t("home.expert.open_review"), type="primary", icon=theme.ICONS["review"]):
#             st.switch_page(navigation.REVIEW)

NOTIFICATIONS = 5  # the newest RCAs waiting, listed on the home of the expert


def expert_home() -> None:
    """Technical Expert: what waits for a decision, newest first, and the way to it."""
    _, middle, _ = st.columns([1, 3, 1])
    with middle:
        st.title(t("review.title"), text_alignment="center")
        st.markdown(t("review.subtitle"), text_alignment="center")
        st.space("small")

        try:
            waiting = services.list_rcas(status="AWAITING_TECHNICAL_REVIEW")
            titles = {item.rca_id: item.title for item in services.list_rca_summaries()}
        except services.ServiceError as error:
            st.error(t("state.error_data"), icon=theme.ICONS["error"])
            st.caption(t("state.error_detail", detail=error))
            return

        with st.container(border=True):
            if not waiting:
                st.markdown(t("home.expert.waiting_none"))
                return
            message = (
                t("home.expert.waiting_one")
                if len(waiting) == 1
                else t("home.expert.waiting_many", count=len(waiting))
            )
            st.markdown(f"**{message}**")
            for record in waiting[:NOTIFICATIONS]:
                kind = (t("home.expert.answers_request", revision=record.revision) if record.revision > 1
                        else t("home.expert.new_rca"))
                with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
                    st.markdown(f"`{record.rca_id}` · `{record.problem_id}` {titles.get(record.rca_id, '')}  \n"
                                f":gray[{kind} · {formatting.date_time(record.created_at)}]")
                    if st.button(t("review.open"), key=f"notify-{record.rca_id}", icon=theme.ICONS["review"]):
                        st.switch_page(navigation.REVIEW, query_params={"rca": record.rca_id})
            if st.button(t("home.expert.open_review"), type="primary", icon=theme.ICONS["review"]):
                st.switch_page(navigation.REVIEW)


# hero()
# st.space("medium")
# how_it_works()
# waiting_for_the_expert()

if state.is_technical_expert():
    expert_home()
else:
    hero()
    st.space("medium")
    how_it_works()
