"""The investigation while it happens, and afterwards.

Each step of the investigation is one line: what it is doing, whether it is waiting,
running, done or failed, and how long it took. A finished step can be opened to see what
it actually did — which sources it checked, what it found, what it set aside.

What is shown is what the investigation observably did. The model's own reasoning is never
exposed: only its results, and the evidence they point to.
"""

import re

import streamlit as st

from rca.models import InvestigationStep
from rca.ui import formatting, theme
from rca.ui.strings import readable, t

# The steps in the order they run. The saving of the record is not a step a person cares
# about, and it records no trace, so it is not listed.
STEPS = (
    "similar_incidents",
    "investigation_planner",
    "tools",
    "historical_rca_agent",
    "rca_reasoning_agent",
    "guardrail",
    "confidence",
)


def step_title(name: str) -> str:
    try:
        return t(f"step.{name}.title")
    except KeyError:
        return readable(name)


def _step_text(name: str) -> str | None:
    try:
        return t(f"step.{name}.text")
    except KeyError:
        return None


def _duration(step: InvestigationStep) -> str | None:
    if step.finished_at is None:
        return None
    return formatting.seconds((step.finished_at - step.started_at).total_seconds())


def _listing(label: str, values: list) -> None:
    if not values:
        return
    st.caption(label)
    for value in values:
        if isinstance(value, dict):
            st.markdown(f"- `{value.get('id', '')}` — {value.get('reason', '')}")
        else:
            st.markdown(f"- {value}")


def _details(step: InvestigationStep, plan=None) -> None:
    """What this step did, told in the words of the step rather than of the code."""
    details = step.details or {}
    st.markdown(step.summary)

    if step.name == "similar_incidents":
        _listing(t("step.related_found"), list(details.get("found", [])))
    elif step.name == "investigation_planner":
        if plan is not None:
            st.caption(t("step.service"))
            st.markdown(plan.service)
            st.caption(t("step.window"))
            st.markdown(f"{formatting.date_time(plan.window_start)} - {formatting.date_time(plan.window_end)}")
            st.caption(t("step.sources"))
            st.markdown(", ".join(plan.sources))
        _listing(t("step.searched_for"), list(details.get("search_queries", [])))
        if details.get("rationale"):
            st.caption(t("step.why"))
            st.markdown(details["rationale"])
    elif step.name == "tools":
        if details.get("evidence") is not None:
            st.caption(t("step.evidence_collected"))
            st.markdown(str(details["evidence"]))
    elif step.name == "historical_rca_agent":
        _listing(t("step.kept"), list(details.get("kept", [])))
        _listing(t("step.dropped"), list(details.get("dropped", [])))
    elif step.name == "guardrail":
        if details.get("attempt"):
            st.caption(t("step.attempt", number=details["attempt"]))
        _listing(t("step.problems"), list(details.get("problems", [])))

    if not details and step.name in ("rca_reasoning_agent", "confidence"):
        st.caption(t("step.no_detail"))


def _counted(summary: str, pattern: str) -> int | None:
    """A number the step reported, when it reported one."""
    found = re.search(pattern, summary)
    return int(found.group(1)) if found else None


def _result_line(step: InvestigationStep, plan=None, limit: int = 70) -> str:
    """What the step found, in the words of the interface where the step has a number to give.

    The investigation writes its own summaries for the record and for the audit, in its own
    vocabulary. Where that vocabulary would reach the screen — hypotheses, schemas, ids —
    the number is taken out of it and said plainly. Anything unrecognised falls back to the
    summary as written, so a change in the investigation never leaves an empty line here.
    """
    summary = (step.summary or t("step.found")).strip()
    details = step.details or {}

    if step.name == "similar_incidents":
        found = details.get("found")
        if found is not None:
            count = len(found)
            if not count:
                return t("step.related_none")
            return t("step.related_one") if count == 1 else t("step.related_many", count=count)

    if step.name == "investigation_planner" and plan is not None:
        window = (f"{formatting.date(plan.window_start)}, "
                  f"{plan.window_start.strftime('%H:%M')} - {plan.window_end.strftime('%H:%M')} UTC")
        return t("step.plan_line", service=plan.service, window=window)

    if step.name == "tools" and details.get("evidence") is not None:
        count = details["evidence"]
        return t("step.collected_count_one") if count == 1 else t("step.collected_count", count=count)

    if step.name == "rca_reasoning_agent":
        count = _counted(summary, r"(\d+) hypothesis")
        if count is not None:
            return t("step.causes_one") if count == 1 else t("step.causes_many", count=count)

    if step.name == "guardrail" and summary.lower().startswith("draft accepted"):
        return t("step.checked_ok")

    if step.name == "confidence":
        count = len(re.findall(r"HYP-\d+", summary))
        if count:
            return t("step.rated_one") if count == 1 else t("step.rated_many", count=count)

    first = summary.split(". ")[0]
    return first if len(first) <= limit else first[: limit - 1].rstrip(" ,;") + "..."


def _line(name: str, state: str, step: InvestigationStep | None, plan=None) -> None:
    """One step: its name, where it stands, how long it took, and what it did."""
    style = theme.STEP_STATE[state]
    duration = _duration(step) if step else None
    heading = f"{style.icon} **{step_title(name)}**"

    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute"):
            st.markdown(heading)
            st.caption(duration or t(f"step.state.{state}"))
        if state in ("queued", "running"):
            text = _step_text(name)
            if text:
                st.caption(text)
        elif step is not None:
            with st.expander(_result_line(step, plan)):
                _details(step, plan)


def timeline(finished: list[InvestigationStep], *, running: bool, failed: bool = False, plan=None) -> None:
    """The whole investigation: what is done, what is happening now, what is still to come.

    Steps can repeat — a refused draft is asked again — so the last run of each step is the
    one shown, with its attempt number inside.
    """
    done = {step.name: step for step in finished}
    order = list(STEPS) + [step.name for step in finished if step.name not in STEPS]
    current = next((name for name in order if name not in done), None)

    for name in order:
        if name in done:
            state = "done"
        elif failed and name == current:
            state = "failed"
        elif running and name == current:
            state = "running"
        else:
            state = "queued"
        _line(name, state, done.get(name), plan)
