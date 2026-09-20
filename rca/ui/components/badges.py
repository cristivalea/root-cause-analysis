"""Badges for severity and for the two kinds of status.

Each badge is a colour plus a word. The word is always there, so the meaning survives on a
black-and-white screen, for a colour-blind reader, and in a screen reader.

Two shapes, because the screens need both:
- `*_badge()` places a badge on the page;
- `*_chip()` returns the same badge as text, to put inside a sentence, a table or a card.
"""

import streamlit as st

from rca.ui import theme
from rca.ui.strings import t_or_value


def _chip(style: theme.Style, label: str, with_icon: bool) -> str:
    icon = f"{style.icon} " if with_icon and style.icon else ""
    return f":{style.color}-badge[{icon}{label}]"


# ---- Severity: how bad the incident was ----


def severity_label(severity: str) -> str:
    return t_or_value(f"severity.{severity}", severity)


def severity_chip(severity: str) -> str:
    return _chip(theme.style_for(theme.SEVERITY, severity), severity_label(severity), False)


def severity_badge(severity: str) -> None:
    style = theme.style_for(theme.SEVERITY, severity)
    st.badge(severity_label(severity), color=style.color)


# ---- Incident status: where the incident stands ----


def incident_status_label(status: str) -> str:
    return t_or_value(f"incident_status.{status}", status)


def incident_status_chip(status: str, *, with_icon: bool = True) -> str:
    style = theme.style_for(theme.INCIDENT_STATUS, status)
    return _chip(style, incident_status_label(status), with_icon)


def incident_status_badge(status: str) -> None:
    style = theme.style_for(theme.INCIDENT_STATUS, status)
    st.badge(incident_status_label(status), color=style.color, icon=style.icon)


# ---- RCA status: where the analysis stands ----


def rca_status_label(status: str) -> str:
    return t_or_value(f"rca_status.{status}", status)


def rca_status_chip(status: str, *, with_icon: bool = True) -> str:
    style = theme.style_for(theme.RCA_STATUS, status)
    return _chip(style, rca_status_label(status), with_icon)


def rca_status_badge(status: str) -> None:
    style = theme.style_for(theme.RCA_STATUS, status)
    st.badge(rca_status_label(status), color=style.color, icon=style.icon)
