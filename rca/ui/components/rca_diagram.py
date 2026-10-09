"""The cause diagram for the Technical Expert: 5 Whys or Fishbone, as rca/diagram.py chooses it.

Every box shows the evidence behind it; a box without evidence is dashed and marked "to check".
The same content is written out underneath, which is also what a screen reader gets.
"""

import streamlit as st

from rca.diagram import choose_diagram
from rca.models import RCARecord
from rca.ui.components.cause_diagram import _palette, _wrap
from rca.ui.strings import t


def _citations(record: RCARecord, evidence_ids: list[str]) -> str:
    known = {item.evidence_id: item.citation for item in record.evidence}
    return ", ".join(f"{evidence_id} {known[evidence_id]}" for evidence_id in evidence_ids if evidence_id in known)


def _node(name: str, label: str, supported: bool, colours: dict) -> str:
    fill, line, text = colours["evidence"] if supported else colours["LOW"]
    style = "rounded,filled" if supported else "rounded,filled,dashed"
    return f'  {name} [label="{label}", fillcolor="{fill}", color="{line}", fontcolor="{text}", style="{style}"];'


def dot(record: RCARecord, incident_title: str | None = None) -> str | None:
    diagram = choose_diagram(record.hypotheses)
    if diagram is None:
        return None
    colours = _palette()
    edge = colours["edge"]
    fill, line, text = colours["incident"]
    lines = [
        "digraph cause {",
        "  bgcolor=\"transparent\"; nodesep=0.3; ranksep=0.45;",
        f"  edge [color=\"{edge}\", arrowsize=0.7, fontname=\"Inter\", fontsize=9, fontcolor=\"{edge}\"];",
        "  node [shape=box, fontname=\"Inter\", fontsize=10, margin=\"0.16,0.1\"];",
        f'  problem [label="{_wrap(incident_title or record.incident_id)}", fillcolor="{fill}", color="{line}", '
        f'fontcolor="{text}", style="rounded,filled"];',
    ]
    if diagram.kind == "five_whys":
        lines.insert(1, "  rankdir=TB;")
        previous = "problem"
        for index, step in enumerate(diagram.steps):
            supported = bool(step.evidence)
            evidence = _wrap(_citations(record, step.evidence), width=40, limit=2) if supported else t("diagram.to_check")
            label = f"{t('diagram.why', number=index + 1)}\\n{_wrap(step.because, width=34)}\\n{evidence}"
            lines.append(_node(f"why{index}", label, supported, colours))
            lines.append(f'  {previous} -> why{index} [label="{t("diagram.because")}"];')
            previous = f"why{index}"
    else:
        lines.insert(1, "  rankdir=RL;")
        categories = list(dict.fromkeys(factor.category for _, factor in diagram.factors))
        for index, category in enumerate(categories):
            lines.append(f'  cat{index} [label="{category}", shape=plaintext, fontsize=11];')
            lines.append(f"  cat{index} -> problem [penwidth=1.6, arrowhead=none];")
            for position, (hypothesis_id, factor) in enumerate(f for f in diagram.factors if f[1].category == category):
                supported = bool(factor.evidence)
                evidence = _wrap(_citations(record, factor.evidence), width=40, limit=2) if supported else t("diagram.to_check")
                label = f"{_wrap(factor.factor, width=32)}\\n({hypothesis_id}) {evidence}"
                lines.append(_node(f"f{index}_{position}", label, supported, colours))
                lines.append(f"  f{index}_{position} -> cat{index} [arrowhead=none];")
    lines.append("}")
    return "\n".join(lines)


def rca_diagram(record: RCARecord, incident_title: str | None = None) -> None:
    diagram = choose_diagram(record.hypotheses)
    drawing = dot(record, incident_title)
    if diagram is None or drawing is None:
        return
    if diagram.kind == "five_whys":
        st.subheader(t("diagram.five_whys_title"))
        st.caption(t("diagram.five_whys_how", hypothesis=diagram.hypothesis_id))
    else:
        st.subheader(t("diagram.fishbone_title"))
        st.caption(t("diagram.fishbone_how"))
    st.graphviz_chart(drawing, width="stretch")
    with st.expander(t("diagram.written")):
        if diagram.kind == "five_whys":
            for index, step in enumerate(diagram.steps, start=1):
                cited = _citations(record, step.evidence) or t("diagram.to_check")
                st.markdown(f"{index}. **{step.why}** {step.because} ({cited})")
        else:
            for hypothesis_id, factor in diagram.factors:
                cited = _citations(record, factor.evidence) or t("diagram.to_check")
                st.markdown(f"- **{factor.category}** · {factor.factor} ({hypothesis_id}; {cited})")
