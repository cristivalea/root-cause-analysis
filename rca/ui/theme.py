"""The design system: what each meaning looks like.

The colours, fonts and radii live in `.streamlit/config.toml`. This module holds the other
half of the design system — which colour and which icon carry which meaning — so that a
severity looks the same on every screen and nothing picks a colour by itself.

Two rules from the brief are encoded here:

- Severity and status are different things and never share a visual language.
- Colour never carries the meaning on its own; every badge also has a text label, which
  comes from `rca.ui.strings`.
"""

from dataclasses import dataclass

# Streamlit badge colours: red, orange, yellow, green, blue, violet, gray.
BadgeColor = str


@dataclass(frozen=True)
class Style:
    """How one value of a set is shown: a colour, and an optional icon."""

    color: BadgeColor
    icon: str | None = None


# How bad the incident was. Critical is the only red on the screen, on purpose.
SEVERITY: dict[str, Style] = {
    "SEV-1": Style("red"),
    "SEV-2": Style("orange"),
    "SEV-3": Style("yellow"),
    "SEV-4": Style("gray"),
}

# Where the incident stands. Green means the service is working again.
INCIDENT_STATUS: dict[str, Style] = {
    "Resolved": Style("green", ":material/check_circle:"),
    "Closed": Style("gray", ":material/task_alt:"),
}

# Where the analysis stands. Orange means somebody has to act.
RCA_STATUS: dict[str, Style] = {
    "INVESTIGATING": Style("blue", ":material/progress_activity:"),
    "DRAFT": Style("gray", ":material/description:"),
    "PENDING_REVIEW": Style("orange", ":material/pending:"),
    "MORE_DETAILS_REQUESTED": Style("violet", ":material/help:"),
    "ESCALATED": Style("red", ":material/priority_high:"),
    "REJECTED": Style("red", ":material/cancel:"),
    "FINAL": Style("green", ":material/verified:"),
}

# How sure the investigation is about a candidate cause. The level is calculated by the
# application from the evidence, never written by the model.
CONFIDENCE: dict[str, Style] = {
    "HIGH": Style("green"),
    "MEDIUM": Style("orange"),
    "LOW": Style("gray"),
}

# Where one step of the investigation stands.
STEP_STATE: dict[str, Style] = {
    "done": Style("green", ":material/check_circle:"),
    "running": Style("blue", ":material/progress_activity:"),
    "queued": Style("gray", ":material/radio_button_unchecked:"),
    "failed": Style("red", ":material/error:"),
}

# Where a piece of evidence came from.
EVIDENCE: dict[str, Style] = {
    "LOG": Style("gray", ":material/description:"),
    "CHANGE": Style("gray", ":material/build:"),
    "CMDB": Style("gray", ":material/lan:"),
    "HISTORICAL_RCA": Style("gray", ":material/menu_book:"),
    "HISTORICAL_INCIDENT": Style("gray", ":material/replay:"),
}

FALLBACK = Style("gray")

# Icons used by the shell and the shared components, named once so they stay consistent.
ICONS = {
    "home": ":material/home:",
    "start_rca": ":material/troubleshoot:",
    "investigation": ":material/graphic_eq:",
    "review": ":material/fact_check:",
    "history": ":material/history:",
    "back": ":material/arrow_back:",
    "role": ":material/badge:",
    "scaffold": ":material/construction:",
    "error": ":material/error:",
}


def style_for(styles: dict[str, Style], value: str) -> Style:
    """The style of a value, or a neutral one when the data holds something unexpected."""
    return styles.get(value, FALLBACK)
