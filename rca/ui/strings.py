"""Every word the user reads, in one place.

The interface is in English. Keeping the text here instead of inside the pages means a
second language is added by writing a second catalogue, and that no screen invents its own
wording for something another screen already names.

Use it as `t("home.title")`. Values can be filled in: `t("review.decided_by", name=...)`.
"""

from typing import Any

import streamlit as st

DEFAULT_LANGUAGE = "en"
LANGUAGE_KEY = "language"

EN: dict[str, str] = {
    # ---- The application itself ----
    "app.name": "Root Cause Analysis",
    "app.tagline": "Investigate major incidents, identify their root causes, and submit "
                   "the analysis for technical review.",
    # ---- Navigation ----
    "nav.home": "Home",
    "nav.start_rca": "Start an RCA",
    "nav.investigation": "Investigation",
    "nav.review": "Technical review",
    "nav.history": "RCA history",
    # ---- Roles ----
    "role.label": "Working as",
    "role.problem_manager": "Problem Manager",
    "role.technical_expert": "Technical Expert",
    "role.help": "The Problem Manager starts investigations. The Technical Expert reviews "
                 "the analysis and decides whether it is valid.",
    # ---- Pages ----
    "home.title": "Root Cause Analysis",
    "home.subtitle": "Investigate major incidents, identify their root causes, and submit "
                     "the analysis for technical review.",
    "home.cta": "Start an RCA",
    "home.cta_help": "Choose a major incident and begin its investigation.",
    "home.how_it_works": "How it works",
    "home.step_1.number": "01",
    "home.step_1.title": "Select an incident",
    "home.step_1.text": "Choose the major incident you want to investigate.",
    "home.step_2.number": "02",
    "home.step_2.title": "Investigate",
    "home.step_2.text": "The investigation searches past incidents, past analyses, service "
                        "dependencies, recent changes and logs.",
    "home.step_3.number": "03",
    "home.step_3.title": "Review the findings",
    "home.step_3.text": "Read the candidate root causes, the evidence behind each one and "
                        "what could not be checked.",
    "home.step_4.number": "04",
    "home.step_4.title": "Get technical approval",
    "home.step_4.text": "Send the analysis to a Technical Expert, who validates it, rejects "
                        "it, or asks for more detail.",
    "home.expert.waiting_one": "One analysis is waiting for your review.",
    "home.expert.waiting_many": "{count} analyses are waiting for your review.",
    "home.expert.waiting_none": "Nothing is waiting for your review right now.",
    "home.expert.open_review": "Open technical review",
    "home.history_link": "See past analyses",
    "start_rca.title": "Start an RCA investigation",
    "start_rca.subtitle": "Select one major incident to begin the investigation.",
    "investigation.title": "RCA investigation",
    "investigation.subtitle": "Follow the investigation and review the analysis it produces.",
    "review.title": "RCA technical review",
    "review.subtitle": "Review the RCA findings and decide whether the analysis is ready "
                       "to be validated.",
    "history.title": "RCA history",
    "history.subtitle": "Past investigations, expert decisions and completed analyses.",
    # ---- Severity (how bad the incident was) ----
    "severity.SEV-1": "Critical",
    "severity.SEV-2": "High",
    "severity.SEV-3": "Medium",
    "severity.SEV-4": "Low",
    "severity.label": "Severity",
    # ---- Incident status (where the incident stands) ----
    "incident_status.Resolved": "Resolved",
    "incident_status.Closed": "Closed",
    "incident_status.label": "Status",
    # ---- RCA status ----
    "rca_status.INVESTIGATING": "Investigating",
    "rca_status.DRAFT": "Draft ready",
    "rca_status.PENDING_REVIEW": "Awaiting technical review",
    "rca_status.MORE_DETAILS_REQUESTED": "More details requested",
    "rca_status.ESCALATED": "Escalated",
    "rca_status.ESCALATED_MANUAL": "Escalated for manual resolution",
    "rca_status.REJECTED": "Rejected",
    "rca_status.FINAL": "Validated",
    "rca_status.label": "RCA status",
    # ---- Shared wording ----
    "common.back": "Back",
    "common.incident": "Incident",
    "common.service": "Service",
    "common.date": "Date",
    "common.duration": "Duration",
    "common.unknown": "Not recorded",
    # ---- States every screen can show ----
    "state.loading_incidents": "Loading incidents…",
    "state.no_incidents": "There are no incidents to investigate yet.",
    "state.no_matches": "No incidents match your filters.",
    "state.investigating": "Investigation in progress",
    "state.error_data": "We couldn't load the data for this screen.",
    "state.error_investigation": "We couldn't complete the investigation.",
    "state.error_detail": "Technical detail: {detail}",
    # ---- How values are written ----
    "format.minutes": "{count} min",
    "format.hours": "{count} h",
    "format.hours_minutes": "{hours} h {minutes} min",
    "format.seconds": "{count} s",
    # ---- Finding an incident ----
    "search.label": "Search incidents",
    "search.placeholder": "Search by incident ID or title, for example INC-2026-00482",
    "filters.button": "Filters",
    "filters.active": "Filters ({count})",
    "filters.severity": "Severity",
    "filters.service": "Service",
    "filters.status": "Status",
    "filters.date": "Detected between",
    "filters.show_all": "Show all incidents",
    "filters.chip_date": "Detected {range}",
    "filters.chip_date_from": "from {date}",
    "filters.chip_date_to": "until {date}",
    "filters.remove": "Remove this filter",
    # ---- The incident list ----
    "table.incident": "Incident",
    "table.description": "What happened",
    "table.service": "Service",
    "table.severity": "Severity",
    "table.status": "Status",
    "table.date": "Detected",
    "table.details": "Details",
    "list.showing": "Showing {first}-{last} of {total} incidents",
    "list.page": "Page {page} of {pages}",
    "list.previous": "Previous",
    "list.next": "Next",
    "list.select_hint": "Select one incident to continue.",
    # ---- The selected incident and the action ----
    "selection.title": "Selected incident",
    "selection.clear": "Clear selection",
    "selection.view_details": "View incident details",
    "selection.analyze": "Analyze Root Cause",
    "selection.analyze_help": "Start the investigation for the selected incident.",
    # ---- Problems ----
    "nav.problems": "Problems",
    "nav.incidents": "Incidents",
    "problems.title": "Problems",
    "problems.subtitle": "Each problem groups the incidents that share one unknown cause. Start the RCA from here.",
    "problems.filter": "Show",
    "problems.filter.Open": "Open",
    "problems.filter.Closed": "Closed",
    "problems.filter.all": "All",
    "problems.filter.Manual": "Manual resolution",
    "problems.manual": "This problem is solved by people, outside the application: the expert rejected two cases, "
                       "or a case went past its last revision. Close it with the outcome once it is solved.",
    "problems.active_case": "{rca} is in progress ({status}). One RCA case at a time: continue it instead of starting another.",
    "problems.rejected_count": "Rejected cases: {count} of {maximum}. After the last one the problem is solved manually.",
    "problems.after_rejection": "{rca} was rejected. Start a new case only with something new: add guidance below "
                                "or incidents to the problem. The same input would give the same answer.",
    "problems.none": "No problem to show.",
    "problems.select_hint": "Select a problem to see its incidents, its RCAs and its history.",
    "problems.col.problem": "Problem",
    "problems.col.title": "Title",
    "problems.col.priority": "Priority",
    "problems.col.incidents": "Incidents",
    "problems.col.services": "Services",
    "problems.col.status": "Status",
    "problems.col.created": "Opened",
    "problems.proposed_title": "Proposed problems ({count})",
    "problems.proposed_hint": "Groups of at least three alike incidents in no problem. Create a problem from a group, "
                              "or ignore it; nothing is created without you.",
    "problems.proposed_create": "Create this problem",
    "problems.back": "All problems",
    "problems.status": "Status",
    "problems.priority": "Priority",
    "problems.services": "Services",
    "problems.opened_by": "Opened by {name} on {date}",
    "problems.closed_because": "Closed on {date}: {reason}",
    "problems.closed_by_rca": "Closed by {rca}",
    "problems.incidents_title": "Incidents ({count})",
    "problems.linked": "Attached by {name} on {date}",
    "problems.add_title": "Add an incident",
    "problems.add_choose": "Incident in no problem",
    "problems.add_action": "Add to the problem",
    "problems.remove_title": "Remove an incident",
    "problems.remove_choose": "Incident",
    "problems.remove_reason": "Why it does not belong here",
    "problems.remove_action": "Remove from the problem",
    "problems.remove_last": "The last incident cannot be removed. Close the problem instead.",
    "problems.rcas_title": "RCAs of this problem",
    "problems.rcas_none": "No RCA has been run for this problem yet.",
    "problems.rca_line": "{rca} · revision {cycle} · {status}",
    "problems.open_rca": "Open",
    "problems.start_title": "Start the RCA",
    "problems.start_hint": "The investigation covers every incident of the problem. The most recent one, {incident}, "
                           "is the reference.",
    "problems.start_action": "Start RCA",
    "problems.close_title": "Close the problem",
    "problems.close_reason": "Why it needs no RCA",
    "problems.close_action": "Close the problem",
    "problems.reopen_title": "Reopen the problem",
    "problems.reopen_reason": "Why it is reopened, for example it came back after the fix",
    "problems.reopen_action": "Reopen",
    "problems.history_title": "History",
    "problems.event": "{date} · {name} · {action}",
    "problems.reason_required": "Write the reason first.",
    "problems.done": "Done.",
    "event.created": "created the problem",
    "event.incident_added": "added {incident}",
    "event.incident_removed": "removed {incident}",
    "event.incident_moved_in": "moved {incident} here",
    "event.incident_moved_out": "moved {incident} to another problem",
    "event.closed": "closed the problem",
    "event.reopened": "reopened the problem",
    "event.manual": "sent the problem to manual resolution",
    "cycle.rejected_next": "A new case for this problem must start from something new: guidance or other incidents. "
                           "Add them on the problem page and start the RCA there.",
    "cycle.open_problem": "Open {problem}",
    # ---- Incidents in no problem ----
    "incidents.title": "Incidents in no problem",
    "incidents.subtitle": "Each incident comes with a suggestion. You decide: attach it, start a new problem, "
                          "or mark it as needing none.",
    "incidents.none": "Every incident is in a problem or was marked as needing none.",
    "incidents.suggestions_missing": "The suggestions are not available right now. You can still create problems.",
    "incidents.col.suggestion": "Suggestion",
    "incidents.selected": "{count} incident(s) selected",
    "incidents.select_hint": "Select one incident to see its suggestion, or several to create a problem from them.",
    "incidents.create_title": "Create a problem from the selected incidents",
    "incidents.create_name": "Title (optional, the most recent incident's title is used otherwise)",
    "incidents.create_action": "Create problem",
    "incidents.suggestion_title": "Suggestion for {incident}",
    "incidents.no_suggestion": "No incident looks like this one. Create a problem for it alone if it needs one.",
    "incidents.why": "Why this suggestion",
    "incidents.accept_open": "Add to {problem}",
    "incidents.accept_closed_reopen": "Reopen {problem} and add",
    "incidents.accept_new": "Create a problem with the alike incidents",
    "incidents.reject": "Reject the suggestion",
    "incidents.dismiss_title": "Needs no problem",
    "incidents.dismiss_reason": "Why no problem is needed",
    "incidents.dismiss_action": "Mark as needing no problem",
    "incidents.reopen_reason": "Why {problem} is reopened",
    "suggestion.open_problem": "Add to {problem}",
    "suggestion.closed_problem": "Possible recurrence of {problem}",
    "suggestion.new_problem": "New problem with {count} alike incident(s)",
    "suggestion.none": "-",
    # ---- Guidance from the Problem Manager ----
    "guidance.title": "Guidance for the investigation (optional)",
    "guidance.hint": "The investigation covers every incident of the problem, with fixed windows. "
                     "Add what you already know; the defaults are used for anything left empty.",
    "guidance.notes": "Notes for the investigation",
    "guidance.notes_help": "What you suspect or want checked. The planner reads it as a hint, not as a fact.",
    "guidance.services": "Also search these services",
    "guidance.services_help": "Their logs and changes are searched too, for example a service the CMDB does not link.",
    "guidance.change_days": "Search changes this many days before the first incident",
    "guidance.change_days_help": "Default 7 days. Use more when the problem may have started with an older change.",
    "guidance.log_hours": "Search logs this many hours before each incident",
    "guidance.log_hours_help": "Default 2 hours. Use more for a slow degradation.",
    # ---- Incident details ----
    "details.title": "Incident details",
    "details.summary": "Summary",
    "details.symptoms": "Symptoms",
    "details.mitigation": "Initial mitigation",
    "details.service_context": "Service",
    "details.business_service": "Business service",
    "details.environment": "Environment",
    "details.teams": "Owner teams",
    "details.teams_source": "From the CMDB, for the components of this service.",
    "details.timing": "Timing",
    "details.detected": "Detected",
    "details.resolved": "Resolved",
    "details.duration": "Duration",
    "details.impact": "Impact",
    "details.failed_transactions": "Failed transactions",
    "details.customers": "Customers affected",
    "details.error_rate": "Peak error rate",
    "details.regions": "Affected regions",
    "details.why_rca": "Why it needs an analysis",
    "details.reported_by": "Reported by",
    "details.past_analyses": "Analyses made for this incident",
    "details.no_past_analyses": "No analysis has been made for this incident yet.",
    "details.close": "Close",
    # ---- The investigation as it runs ----
    "investigation.nothing_selected": "No incident is selected yet.",
    "investigation.not_found": "This analysis could not be found.",
    "investigation.not_found_hint": "It may have been removed. You can pick an incident and "
                                    "start a new investigation.",
    "investigation.incident_missing": "The incident of this analysis is no longer in the "
                                      "incident data.",
    "investigation.choose_incident": "Choose an incident",
    "investigation.start": "Start investigation",
    "investigation.running": "Investigation in progress",
    "investigation.running_hint": "This usually takes under a minute. Keep this tab open "
                                  "while the investigation runs.",
    "investigation.steps_title": "What the investigation is doing",
    "investigation.steps_title_done": "What the investigation did",
    "investigation.failed": "We couldn't complete the investigation.",
    "investigation.failed_hint": "Nothing was saved. You can try again.",
    "investigation.try_again": "Try again",
    "investigation.technical_detail": "Technical detail",
    "investigation.escalated": "The investigation could not produce an analysis.",
    "investigation.escalated_manual": "Escalated for manual resolution",
    "investigation.escalated_manual_hint": "The Technical Expert still asked for more after the last allowed "
                                           "revision of this case. The case continues outside the application.",
    "investigation.escalated_hint": "The investigation stopped before it could propose a cause, and the case was escalated. You can run it again.",
    "step.state.done": "Completed",
    "step.state.running": "Running",
    "step.state.queued": "Waiting",
    "step.state.failed": "Failed",
    "step.similar_incidents.title": "Find related incidents",
    "step.similar_incidents.text": "Searches past incidents with the same symptoms.",
    "step.investigation_planner.title": "Plan the investigation",
    "step.investigation_planner.text": "Writes the searches for past incidents and analyses. The services "
                                       "and time windows come from the problem and its incidents.",
    "step.build_timeline.title": "Order the events",
    "step.build_timeline.text": "Puts the incidents, the logs and the changes on one time axis and marks the first error.",
    "step.timeline_line": "{count} moments in time order",
    "timeline.title": "Timeline",
    "timeline.how_to_read": "The facts of the investigation in time order. A change before the first error can have "
                            "caused it; a change after it cannot.",
    "timeline.first error": "first error",
    "timeline.before the first error": "before the first error",
    "timeline.after the first error": "after the first error",
    "timeline.incident detected": "incident detected",
    "step.tools.title": "Collect evidence",
    "step.tools.text": "Checks the logs around every incident, the changes since a week before the first one, "
                       "and the service dependencies.",
    "step.historical_rca_agent.title": "Compare with past analyses",
    "step.historical_rca_agent.text": "Keeps only the past incidents and analyses that are "
                                      "really comparable.",
    "step.rca_reasoning_agent.title": "Form candidate causes",
    "step.rca_reasoning_agent.text": "Builds possible causes from the evidence collected.",
    "step.guardrail.title": "Check the findings",
    "step.guardrail.text": "Verifies that every claim points to evidence that exists.",
    "step.confidence.title": "Rate the confidence",
    "step.confidence.text": "Scores each candidate cause from the evidence behind it.",
    "step.found": "What was found",
    "step.related_found": "Related incidents found",
    "step.service": "Service investigated",
    "step.window": "Time window",
    "step.sources": "Sources checked",
    "step.searched_for": "Searched for",
    "step.why": "Why these choices",
    "step.kept": "Kept as comparable",
    "step.dropped": "Set aside",
    "step.evidence_collected": "Pieces of evidence collected",
    "step.collected_count_one": "1 piece of evidence collected",
    "step.collected_count": "{count} pieces of evidence collected",
    "step.related_one": "1 related incident found",
    "step.related_many": "{count} related incidents found",
    "step.related_none": "No related incident found",
    "step.plan_line": "{service} · {window}",
    "step.causes_one": "1 candidate cause proposed",
    "step.causes_many": "{count} candidate causes proposed",
    "step.checked_ok": "Every claim points to evidence that exists",
    "step.rated_one": "1 candidate cause rated",
    "step.rated_many": "{count} candidate causes rated",
    "step.attempt": "Attempt {number}",
    "step.problems": "What had to be corrected",
    "step.warnings": "To check: evidence named in the text without being cited",
    "step.no_detail": "No further detail was recorded for this step.",
    "step.services_searched": "Services searched",
    "step.log_windows": "Logs read around each incident",
    "step.change_window": "Changes searched",
    "step.found_logs": "Log patterns found ({count})",
    "step.found_changes": "Changes found ({count})",
    "step.found_cmdb": "Components depended on, from the CMDB ({count})",
    "step.found_problem_incidents": "Other incidents of the problem ({count})",
    "step.found_none": "Nothing found: this rules it out for the searched window.",
    "step.attempts": "The answer was asked {count} times before it was valid.",
    # ---- The analysis itself ----
    "draft.title": "Analysis",
    "draft.candidate_causes": "Candidate root causes",
    "draft.candidate_note": "The investigation proposes candidate causes. A Technical Expert "
                            "decides which one is the root cause.",
    "draft.confidence": "Confidence",
    "draft.confidence_points": "{points} points",
    "draft.why": "Why this cause is proposed",
    "draft.supported_by": "Supported by",
    "draft.contradicted_by": "Evidence against",
    "draft.how_to_validate": "How to validate it",
    "draft.summary": "Investigation summary",
    "draft.patterns": "What the investigation observed",
    "draft.evidence": "Evidence",
    "draft.related_incidents": "Related incidents",
    "draft.not_checked": "What could not be checked",
    "draft.workaround": "Suggested workaround",
    "draft.change_required": "Fixing the cause will probably need a change request.",
    "draft.weak": "The evidence behind these candidate causes is thin. More investigation is "
                  "recommended before validating.",
    "draft.no_hypotheses": "The investigation did not produce any candidate cause.",
    "draft.duration": "Investigation time",
    "draft.evidence_count": "Evidence",
    "draft.no_evidence": "No evidence was collected.",
    "evidence.LOG": "Log lines",
    "evidence.CHANGE": "Change",
    "evidence.CMDB": "Service dependency",
    "evidence.HISTORICAL_RCA": "Past analysis",
    "evidence.HISTORICAL_INCIDENT": "Past incident",
    "evidence.INCIDENT": "The incident",
    "draft.missing_evidence": "What would confirm or rule it out, not found yet",
    "evidence.source": "Source",
    # ---- Sending the analysis on ----
    "send.action": "Send to Technical Expert",
    "send.help": "The Technical Expert reviews the analysis and decides whether it is valid.",
    "send.sent_title": "Sent for technical review",
    "send.sent_text": "A Technical Expert will validate this analysis, reject it, or ask for "
                      "more detail. You can follow it in the RCA history.",
    "send.open_history": "Open RCA history",
    "send.confirmation": "The analysis was sent for technical review.",
    # ---- The picture of the findings ----
    "diagram.title": "How the findings connect",
    "diagram.how_to_read": "The incident, the causes the investigation proposes for it, and "
                           "the evidence behind each one. Dashed lines are evidence against.",
    "diagram.possible_cause": "possible cause",
    "diagram.based_on": "based on",
    "diagram.against": "against",
    # ---- The technical review ----
    "review.wrong_role": "Technical review is the Technical Expert's screen.",
    "review.switch_role": "Work as Technical Expert",
    "review.queue_title": "Waiting for your review",
    "review.queue_empty": "No analysis is waiting for review.",
    "review.queue_hint": "Analyses sent by a Problem Manager appear here.",
    "review.open": "Review",
    "review.back_to_queue": "All analyses waiting",
    "review.for_incident": "For incident",
    "review.created": "Investigated",
    "review.reviewer": "Your name",
    "review.instructions": "Decide what happens to this analysis.",
    "review.not_found": "This analysis could not be found.",
    "review.not_for_review": "This analysis is not waiting for a decision.",
    "review.decision_failed": "The decision could not be saved.",
    "review.comment_required": "Please write a short comment first.",
    # ---- The three decisions ----
    "decision.approve": "Approve analysis",
    "decision.request": "Request more details",
    "decision.reject": "Reject analysis",
    "decision.approve_help": "Validate one candidate cause as the root cause of this incident.",
    "decision.request_help": "Ask for another investigation that verifies something specific.",
    "decision.reject_help": "Reject the analysis. A new investigation will be needed.",
    "approve.title": "Approve analysis",
    "approve.choose": "Which candidate cause is the root cause?",
    "approve.comment": "Comment (optional)",
    "approve.confirm": "Approve analysis",
    "approve.done_title": "Analysis approved",
    "approve.done_text": "The analysis is validated. The root cause below is now the final "
                         "result of this case.",
    "approve.final_cause": "Root cause",
    "approve.close": "Close",
    "request.title": "Request more details",
    "request.intro": "Tell the investigation what you want verified. A new investigation of "
                     "this case will be needed to answer it.",
    "request.current": "Candidate causes in this analysis",
    "request.question": "What would you like the investigation to verify?",
    "request.placeholder": "For example: check whether the connection pool limit was reached "
                           "on the database side.",
    "request.send": "Send request",
    "request.search_title": "Search wider in the next revision (optional)",
    "request.revision": "This is revision {number} of {maximum}. Your request starts the next revision of the case.",
    "request.last_revision": "This is the last revision ({maximum} of {maximum}). Asking for more details now "
                             "escalates the case for manual resolution instead of starting another revision.",
    "request.done_title": "More details requested",
    "request.done_text": "Your request was recorded. The next investigation of this case will "
                         "answer it; the analysis you read is kept as it is.",
    "reject.title": "Reject analysis",
    "reject.warning": "This analysis will be rejected. It is kept as part of the case, and a "
                      "new investigation will be needed.",
    "reject.comment": "Why are you rejecting it?",
    "reject.confirm": "Reject analysis",
    "reject.done_title": "Analysis rejected",
    "reject.done_text": "The analysis is kept as part of the case. A new investigation is "
                        "needed to replace it.",
    "review.decided_by": "Decided by {name} on {date}",
    "review.comment": "Comment",
    "review.requested_checks": "What was asked for",
    # ---- The next investigation of a case ----
    "cycle.rejected_title": "This analysis was rejected",
    "cycle.more_details_title": "The Technical Expert asked for more details",
    "cycle.start_next": "Start the next investigation",
    "cycle.start_next_help": "A new investigation of this case, kept next to the one you have.",
    "cycle.number": "Investigation {number} of this case",
    # ---- The history of the cases ----
    "history.search": "Search analyses",
    "history.search_placeholder": "Search by analysis ID, incident ID or incident title",
    "history.filter_status": "Status",
    "history.filter_service": "Service",
    "history.none": "No analysis has been made yet.",
    "history.none_hint": "An analysis appears here as soon as an investigation finishes.",
    "history.no_matches": "No analysis matches your search.",
    "history.count": "{count} cases",
    "history.open_case": "Open case",
    "history.back_to_list": "All cases",
    "history.investigations_one": "1 investigation",
    "history.investigations_many": "{count} investigations",
    "history.started": "Started",
    "history.last_decision": "Last decision",
    "history.awaiting": "Waiting for a Technical Expert.",
    "history.no_decision": "No decision has been taken yet.",
    "case.title": "RCA case",
    "case.for_incident": "Incident",
    "case.final_title": "Validated root cause",
    "case.final_text": "This is the result of the case, as validated by a Technical Expert.",
    "case.open_investigation": "Open the investigation",
    "case.open_review": "Open the review",
    "case.show_analysis": "Show the analysis",
    "case.cycle": "Investigation {number}",
    "case.no_review": "No decision was taken on this investigation.",
    "case.not_found": "This case could not be found.",
}

CATALOGUES: dict[str, dict[str, str]] = {"en": EN}


def active_language() -> str:
    """The language the interface is showing. One language for now, chosen here."""
    try:
        return str(st.session_state.get(LANGUAGE_KEY, DEFAULT_LANGUAGE))
    except Exception:  # outside a Streamlit run, for example in a test
        return DEFAULT_LANGUAGE


def t(key: str, **values: Any) -> str:
    """The text for a key, in the active language, with any values filled in."""
    catalogue = CATALOGUES.get(active_language(), EN)
    text = catalogue.get(key, EN.get(key))
    if text is None:
        raise KeyError(f"No text is defined for '{key}'.")
    return text.format(**values) if values else text


def readable(value: str) -> str:
    """A value the catalogue does not know yet, written as well as we can: a stored status
    such as MORE_DETAILS_REQUESTED becomes "More details requested"."""
    return value.replace("_", " ").capitalize() if "_" in value else value


def t_or_value(key: str, value: str) -> str:
    """The text for a key, or the value itself when no text is defined for it.

    Used by the badges: the data can hold a status the interface has no word for yet, and a
    missing translation must never take a screen down.
    """
    try:
        return t(key)
    except KeyError:
        return readable(value)
