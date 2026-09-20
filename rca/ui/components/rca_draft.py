"""The analysis the investigation produced.

The same analysis is read by the Problem Manager who starts it and by the Technical Expert
who decides on it, so it is written once here and used by both screens.

Two product rules shape it. The analysis never states a root cause: it proposes candidate
causes, and a person decides. And every candidate cause is shown together with the evidence
it rests on and with what the investigation could not check, so nobody has to take it on
trust.
"""

import streamlit as st

from rca.models import Evidence, RCARecord
from rca.ui import formatting, theme
from rca.ui.components import badges
from rca.ui.strings import t, t_or_value


def _evidence_label(item: Evidence) -> str:
    return t_or_value(f"evidence.{item.type}", item.type)


def _cited(record: RCARecord, evidence_ids: list[str]) -> list[Evidence]:
    known = {item.evidence_id: item for item in record.evidence}
    return [known[item_id] for item_id in evidence_ids if item_id in known]


def _evidence_line(item: Evidence) -> str:
    style = theme.style_for(theme.EVIDENCE, item.type)
    when = f" · {formatting.date(item.timestamp)}" if item.timestamp else ""
    return f"{style.icon} **{_evidence_label(item)}** · `{item.citation}`{when}"


def header(record: RCARecord) -> None:
    """Which analysis this is, where it stands, and what it cost to produce."""
    with st.container(horizontal=True, vertical_alignment="center", gap="small", wrap=True):
        st.markdown(f"`{record.rca_id}`")
        badges.rca_status_badge(record.status)
    facts = [
        f"{t('draft.duration')}: {formatting.seconds(record.duration_seconds)}",
        f"{t('draft.evidence_count')}: {len(record.evidence)}",
    ]
    st.caption(" · ".join(facts))


def candidate_causes(record: RCARecord) -> None:
    """Each candidate cause with its confidence, its reasons and the evidence behind it."""
    st.subheader(t("draft.candidate_causes"))
    st.caption(t("draft.candidate_note"))

    if not record.hypotheses:
        st.info(t("draft.no_hypotheses"), icon=":material/info:")
        return

    if record.weakly_supported:
        st.warning(t("draft.weak"), icon=":material/warning:")

    for hypothesis in record.hypotheses:
        with st.container(border=True):
            with st.container(horizontal=True, vertical_alignment="center", gap="small", wrap=True):
                confidence = theme.style_for(theme.CONFIDENCE, hypothesis.confidence)
                st.badge(f"{t('draft.confidence')}: {hypothesis.confidence}", color=confidence.color)
                st.caption(t("draft.confidence_points", points=hypothesis.confidence_points))
            st.markdown(f"**{hypothesis.candidate_root_cause}**")

            if hypothesis.reasons:
                st.caption(t("draft.why"))
                for reason in hypothesis.reasons:
                    st.markdown(f"- {reason}")

            supporting = _cited(record, hypothesis.supporting_evidence)
            if supporting:
                st.caption(t("draft.supported_by"))
                for item in supporting:
                    st.markdown(f"- {_evidence_line(item)}")

            contradicting = _cited(record, hypothesis.contradicting_evidence)
            if contradicting:
                st.caption(t("draft.contradicted_by"))
                for item in contradicting:
                    st.markdown(f"- {_evidence_line(item)}")

            if hypothesis.recommended_validation:
                with st.expander(t("draft.how_to_validate")):
                    for check in hypothesis.recommended_validation:
                        st.markdown(f"- {check}")


def summary(record: RCARecord) -> None:
    """What the investigation understood, and the patterns it saw."""
    if not (record.investigation_summary or record.observed_patterns):
        return
    st.subheader(t("draft.summary"))
    if record.investigation_summary:
        st.markdown(record.investigation_summary)
    if record.observed_patterns:
        st.caption(t("draft.patterns"))
        for pattern in record.observed_patterns:
            st.markdown(f"- {pattern}")


def evidence(record: RCARecord) -> None:
    """Everything the investigation collected, each piece with the record it came from."""
    st.subheader(t("draft.evidence"))
    if not record.evidence:
        st.caption(t("draft.no_evidence"))
        return
    for item in record.evidence:
        with st.container(border=True):
            st.markdown(f"`{item.evidence_id}` {_evidence_line(item)}")
            st.caption(item.description)


def related_incidents(record: RCARecord) -> None:
    if not record.linked_incidents:
        return
    st.subheader(t("draft.related_incidents"))
    st.markdown(" ".join(f"`{incident_id}`" for incident_id in record.linked_incidents))


def next_steps(record: RCARecord) -> None:
    """What to do about it, as far as the analysis can say."""
    if record.suggested_workaround:
        st.subheader(t("draft.workaround"))
        st.markdown(record.suggested_workaround)
    if record.change_likely_required:
        st.caption(t("draft.change_required"))


def limitations(record: RCARecord) -> None:
    """What the investigation could not check. Saying so is part of the result."""
    if not record.not_checked:
        return
    with st.expander(t("draft.not_checked")):
        for item in record.not_checked:
            st.markdown(f"- {item}")


def extra_checks(review) -> list[str]:
    """The checks an expert asked for, unless they only repeat the request itself.

    A request written as one sentence is stored as the comment and as a single check. Saying
    it twice on the screen helps nobody, so the list is shown only when it adds something.
    """
    if review is None or not review.requested_checks:
        return []
    comment = (review.comment or "").strip()
    checks = [check.strip() for check in review.requested_checks if check.strip()]
    if len(checks) == 1 and checks[0] == comment:
        return []
    return checks


def rca_draft(record: RCARecord) -> None:
    """The whole analysis, in the order it is read."""
    candidate_causes(record)
    summary(record)
    related_incidents(record)
    next_steps(record)
    evidence(record)
    limitations(record)
