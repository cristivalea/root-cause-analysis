"""RCAs for the tests, built only through the lifecycle of rca/store.py: never written to the tables directly.

make_rca(db, problem_id, template, "draft", "submit", "approve") walks the RCA through those steps:

    draft     the running revision ends with a draft (DRAFT)
    escalate  the running revision ends with ESCALATED_MANUAL (the guardrail refused every draft)
    fail      the running revision ends FAILED (a technical error)
    submit    the draft is sent to the expert (AWAITING_TECHNICAL_REVIEW)
    approve   the expert validates the first hypothesis (VALIDATED)
    reject    the expert rejects it (REJECTED)
    more      the expert asks for more details (REQUEST_MORE_DETAILS, or ESCALATED_MANUAL at the last decision)
    next      the next revision starts (RUNNING)
"""

from pathlib import Path

from rca import store
from rca.models import InvestigationGuidance, RCARecord

EXPERT_COMMENT = "Check the pool size.\nCheck the retry settings."


def make_rca(db: Path, problem_id: str, template: RCARecord, *steps: str, by: str = "pm",
             guidance: InvestigationGuidance | None = None, comment: str | None = None,
             expert_guidance: InvestigationGuidance | None = None, **changes) -> RCARecord:
    """Walk a new RCA of the problem through the steps; returns the latest revision as read."""
    revision = store.start_rca(problem_id, by, guidance, db_path=db)
    for step in steps:
        if step in ("draft", "escalate", "fail"):
            content = template.model_copy(update={
                "rca_id": revision.rca_id, "revision": revision.revision, "run_status": "RUNNING",
                "previous_revision_id": revision.previous_revision_id, "problem_id": problem_id, "owner": by,
                "created_at": revision.created_at, "guidance": revision.guidance, "review": None,
                "final_root_cause": None, "status": "DRAFT", **changes,
            })
            outcome = {"draft": "DRAFT", "escalate": "ESCALATED_MANUAL", "fail": "FAILED"}[step]
            if step == "fail":
                content = content.model_copy(update={"hypotheses": [], "error": "ConnectionError after investigation_planner"})
            store.complete_revision(content, outcome, None if step == "draft" else f"{step} in a test", db_path=db)
        elif step == "submit":
            store.submit_for_review(revision.rca_id, by, db_path=db)
        elif step == "approve":
            store.apply_review(revision.rca_id, "expert", "APPROVE", comment or "Confirmed with the pool metrics.",
                               template.hypotheses[0].hypothesis_id, db_path=db)
        elif step == "reject":
            store.apply_review(revision.rca_id, "expert", "REJECT", comment or "The deploy is not on the failing path.",
                               db_path=db)
        elif step == "more":
            store.apply_review(revision.rca_id, "expert", "REQUEST_MORE_DETAILS", comment or EXPERT_COMMENT, db_path=db,
                               requested_checks=["Check the pool size.", "Check the retry settings."],
                               guidance=expert_guidance)
        elif step == "next":
            revision = store.start_next_revision(revision.rca_id, by, db_path=db)
        else:
            raise ValueError(f"Unknown step '{step}'.")
    return store.get_rca(revision.rca_id, db_path=db)
