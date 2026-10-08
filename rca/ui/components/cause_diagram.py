"""How the findings connect: the incident, the causes proposed for it, and the evidence.

The picture is drawn from the stored analysis and from nothing else. Every box is a real
record: the incident, a candidate cause the investigation proposed, a piece of evidence it
collected. If the analysis has no candidate causes, there is no diagram — an empty shape
would only suggest work that was never done.

Every piece of evidence a cause cites is drawn. To keep the picture readable, the evidence of
one cause is grouped by type: one box for the log lines, one for the changes, and so on, each
listing all its citations.

It is a reading aid, not the analysis: the same content is written out underneath, which is
also what a screen reader gets.
"""

import textwrap

import streamlit as st

from rca.models import Evidence, RCARecord
from rca.ui import theme
from rca.ui.strings import t, t_or_value

WRAP = 30

# Fill, line and text colours for the two themes. Kept here rather than in config.toml
# because Graphviz draws its own boxes and cannot read the Streamlit theme.
PALETTE = {
    "light": {
        "incident": ("#1b2130", "#1b2130", "#ffffff"),
        "HIGH": ("#dff3e8", "#116b45", "#0d4a30"),
        "MEDIUM": ("#fdeed8", "#a85a08", "#6d3a05"),
        "LOW": ("#eceef2", "#5a6372", "#1b2130"),
        "evidence": ("#f7f8fa", "#c9ced8", "#3b4354"),
        "edge": "#8a93a3",
    },
    "dark": {
        "incident": ("#e4e8ef", "#e4e8ef", "#101419"),
        "HIGH": ("#17372a", "#5ac091", "#bdf0d8"),
        "MEDIUM": ("#3a2c16", "#e0a35c", "#f6dcb8"),
        "LOW": ("#20262f", "#98a1b0", "#e4e8ef"),
        "evidence": ("#181d25", "#2f3744", "#c3cad6"),
        "edge": "#6c7686",
    },
}


def _wrap(text: str, width: int = WRAP, limit: int = 4) -> str:
    lines = textwrap.wrap(text.strip(), width=width)[:limit]
    if not lines:
        return ""
    if len(textwrap.wrap(text.strip(), width=width)) > limit:
        lines[-1] = lines[-1] + "..."
    return "\\n".join(line.replace('"', "'") for line in lines)


def _palette() -> dict:
    try:
        mode = st.context.theme.type
    except Exception:  # outside a browser session
        mode = "light"
    return PALETTE.get(mode, PALETTE["light"])


def _by_type(evidence_ids: list[str], known: dict[str, Evidence]) -> list[list[Evidence]]:
    """The cited evidence grouped by type, in the order the types first appear."""
    groups: dict[str, list[Evidence]] = {}
    for evidence_id in evidence_ids:
        item = known.get(evidence_id)
        if item is not None:
            groups.setdefault(item.type, []).append(item)
    return list(groups.values())


def _group_label(items: list[Evidence]) -> str:
    kind = t_or_value(f"evidence.{items[0].type}", items[0].type)
    return f"{kind} ({len(items)})\\n" + "\\n".join(item.citation for item in items)


def dot(record: RCARecord, incident_title: str | None = None) -> str:
    """The analysis as a Graphviz drawing: incident, candidate causes, evidence."""
    colours = _palette()
    known = {item.evidence_id: item for item in record.evidence}
    lines = [
        "digraph rca {",
        "  rankdir=LR;",
        "  bgcolor=\"transparent\";",
        "  ranksep=0.7; nodesep=0.35;",
        f"  edge [color=\"{colours['edge']}\", penwidth=1.1, arrowsize=0.7, "
        f"fontname=\"Inter\", fontsize=9, fontcolor=\"{colours['edge']}\"];",
        "  node [shape=box, style=\"rounded,filled\", fontname=\"Inter\", fontsize=10, margin=\"0.18,0.12\"];",
    ]

    fill, line, text = colours["incident"]
    label = _wrap(incident_title or record.incident_id)
    lines.append(
        f'  incident [label="{record.incident_id}\\n{label}", fillcolor="{fill}", '
        f'color="{line}", fontcolor="{text}"];'
    )

    for index, hypothesis in enumerate(record.hypotheses):
        fill, line, text = colours.get(hypothesis.confidence, colours["LOW"])
        node = f"cause{index}"
        title = _wrap(hypothesis.candidate_root_cause)
        lines.append(
            f'  {node} [label="{hypothesis.confidence}\\n{title}", fillcolor="{fill}", '
            f'color="{line}", fontcolor="{text}"];'
        )
        lines.append(f'  incident -> {node} [label="{t("diagram.possible_cause")}"];')

        fill, line, text = colours["evidence"]
        for position, group in enumerate(_by_type(hypothesis.supporting_evidence, known)):
            evidence_node = f"{node}_ev{position}"
            lines.append(
                f'  {evidence_node} [label="{_group_label(group)}", fillcolor="{fill}", '
                f'color="{line}", fontcolor="{text}", fontsize=9];'
            )
            lines.append(f'  {node} -> {evidence_node} [label="{t("diagram.based_on")}"];')

        for position, group in enumerate(_by_type(hypothesis.contradicting_evidence, known)):
            evidence_node = f"{node}_against{position}"
            lines.append(
                f'  {evidence_node} [label="{_group_label(group)}", fillcolor="{fill}", '
                f'color="{line}", fontcolor="{text}", fontsize=9, style="rounded,filled,dashed"];'
            )
            lines.append(f'  {node} -> {evidence_node} [label="{t("diagram.against")}", style=dashed];')

    lines.append("}")
    return "\n".join(lines)


def cause_diagram(record: RCARecord, incident_title: str | None = None) -> None:
    """The drawing, with the sentence that says how to read it."""
    if not record.hypotheses:
        return
    st.subheader(t("diagram.title"))
    st.caption(t("diagram.how_to_read"))
    st.graphviz_chart(dot(record, incident_title), width="stretch")
