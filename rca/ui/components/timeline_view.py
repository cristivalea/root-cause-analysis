"""The timeline of an analysis, for the Technical Expert: the facts in time order, the first error marked.

It is drawn from the stored analysis only (RCARecord.timeline, built by rca/timeline.py), so every line
is a fact of the evidence ledger, with its evidence id.
"""

import streamlit as st

from rca.models import RCARecord
from rca.ui import formatting, theme
from rca.ui.strings import t, t_or_value

MARKER_COLOURS = {"first error": "red", "before the first error": "orange", "after the first error": "gray",
                  "incident detected": "blue"}


def timeline_view(record: RCARecord) -> None:
    if not record.timeline:
        return
    st.subheader(t("timeline.title"))
    st.caption(t("timeline.how_to_read"))
    for entry in record.timeline:
        style = theme.style_for(theme.EVIDENCE, entry.type)
        marker = (f" :{MARKER_COLOURS.get(entry.marker, 'gray')}-badge[{t_or_value(f'timeline.{entry.marker}', entry.marker)}]"
                  if entry.marker else "")
        st.markdown(f"**{formatting.date_time(entry.at)}** {style.icon} `{entry.citation}` · {entry.evidence_id}{marker}")
        st.caption(entry.what)
