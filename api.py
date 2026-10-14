import json
from dataclasses import asdict
import os
import traceback
from typing import Any, List, Literal, Optional
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from rca import problems, storage, store, suggestions
from rca.config import DB_PATH
from rca.models import InvestigationGuidance
from rca.pipeline import run_investigation

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from rca import auth
from rca import observability

observability.setup()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """At start: a run still RUNNING was stopped with the previous process (a restart, a crash). It is saved
    FAILED with the reason, so it can be run again instead of staying in progress forever."""
    if DB_PATH.exists():
        for revision in store.recover_interrupted(DB_PATH):
            print(f"{revision}: interrupted by the restart, saved as FAILED")
    yield


app = FastAPI(
    title="Root Cause Analysis Multi-Agent Engine API",
    description="Backend decuplat pentru analiză RCA și HITL Problem Management",
    version="1.0.0",
    lifespan=lifespan,
)

bearer_scheme = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str
    password: str


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError("Lipsește JWT_SECRET din configurația backend-ului.")
    return secret


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autentificarea este necesară.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            _jwt_secret(),
            algorithms=["HS256"],
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalid sau expirat.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    username = payload.get("sub")
    if not isinstance(username, str):
        raise HTTPException(status_code=401, detail="Token invalid.")

    user = auth.get_user(username)
    if user is None or not user["active"]:
        raise HTTPException(status_code=401, detail="Cont inexistent sau dezactivat.")

    # Rolul este recitit din SQLite, nu este acceptat dintr-o valoare trimisă de browser.
    return user


def require_roles(*allowed_roles: str):
    def dependency(
        user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="Nu ai dreptul să folosești această funcție.")
        return user

    return dependency


def _serialize(obj: Any) -> Any:
    """Helper sigur pentru serializarea obiectelor Pydantic evitând eroarea typing.Literal."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "dict"):
        return json.loads(obj.json())
    return obj


# --- DTO-uri ---

class StartRCARequest(BaseModel):
    """Start RCA on a problem, or the next revision of an RCA. guidance holds the notes and the instructions
    or questions of the Problem Manager, and wider searches. request_key, one per click, makes a repeated
    request (a double click, a retry of the browser) return what the first one created."""

    guidance: InvestigationGuidance | None = None
    request_key: Optional[str] = None


class ApplyReviewRequest(BaseModel):
    """The reviewer is the signed-in expert; a reviewer in the request is ignored."""

    reviewer: Optional[str] = None
    decision: str
    comment: str
    hypothesis_id: Optional[str] = None
    requested_checks: Optional[List[str]] = None
    guidance: InvestigationGuidance | None = None  # wider searches the expert asks for, with REQUEST_MORE_DETAILS


class CreateProblemRequest(BaseModel):
    incident_ids: List[str]
    title: Optional[str] = None
    description: Optional[str] = None
    reason: Optional[str] = None  # required: why these incidents belong together, kept in the history


class AttachIncidentRequest(BaseModel):
    incident_id: str
    reason: Optional[str] = None  # optional: why the incident belongs to the problem, kept in the history


class GuidanceRequest(BaseModel):
    guidance: InvestigationGuidance | None = None  # empty clears the guidance of the problem


class ReasonRequest(BaseModel):
    reason: str


class ProposalRequest(BaseModel):
    """A proposal of the Proposed Problem Records page, as the page received it. The key is computed again
    from the rest, so a proposal cannot be changed on the way; the rules are checked again on accept."""

    key: str
    kind: Literal["group", "attach", "single"]
    incident_ids: List[str]
    problem_id: Optional[str] = None
    title: Optional[str] = None  # the title of the new problem; the most recent incident's when empty
    reason: Optional[str] = None  # why it is accepted or rejected, kept in the history


class RejectSuggestionRequest(BaseModel):
    targets: List[str]  # the suggested problem, or the incidents of a proposed new problem


def _problem_result(result: problems.Result) -> dict:
    return {"problem": _serialize(result.problem), "warnings": result.warnings}


def _rca_error(exc: Exception) -> HTTPException:
    """404 for an unknown RCA, 409 for a status that does not allow the operation, 400 for a refused rule."""
    if isinstance(exc, store.RCANotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (store.TransitionError, problems.ProblemConflict)):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def _problem_error(exc: problems.ProblemError) -> HTTPException:
    """409 when the change conflicts with the current state (an incident already in a problem), else 400."""
    return HTTPException(status_code=409 if isinstance(exc, problems.ProblemConflict) else 400, detail=str(exc))


# --- Rute ---

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    db_ok = DB_PATH.exists()
    return {
        "status": "healthy" if db_ok else "degraded",
        "database_connected": db_ok,
        "service": "RCA Core API"
    }

@app.post("/api/v1/auth/login")
def api_login(req: LoginRequest):
    user = auth.get_user(req.username)

    if (
        user is None
        or not user["active"]
        or not auth.verify_password(req.password, user["password_hash"])
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilizator sau parolă incorectă.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=60)
    token = jwt.encode(
        {"sub": user["username"], "exp": expires_at},
        _jwt_secret(),
        algorithm="HS256",
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user["username"],
        "role": user["role"],
    }

# 1. Incidente & CMDB

@app.get("/api/v1/incidents")
def api_list_incidents( user: dict = Depends(require_roles("problem_manager")),):
    try:
        incidents = storage.list_incidents(DB_PATH)
        sorted_incidents = sorted(incidents, key=lambda inc: inc.detected_at, reverse=True)
        return [_serialize(inc) for inc in sorted_incidents]
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/incidents/unassigned")
def api_unassigned_incidents(user: dict = Depends(require_roles("problem_manager"))):
    """The incidents in no problem that were not marked as needing none."""
    return [_serialize(item) for item in problems.unassigned_incidents(DB_PATH)]


@app.get("/api/v1/incidents/unassigned/suggestions")
def api_suggestions(user: dict = Depends(require_roles("problem_manager"))):
    """A grouping suggestion, or null, for every incident in no problem, with its reasons."""
    try:
        return {incident_id: (asdict(item) if item else None)
                for incident_id, item in suggestions.suggest_all(DB_PATH).items()}
    except Exception as exc:  # ChromaDB not built yet: the suggestions are missing, the rest still works
        traceback.print_exc()
        raise HTTPException(status_code=503, detail=f"Suggestions are not available: {exc}")


@app.post("/api/v1/incidents/{incident_id}/reject-suggestion")
def api_reject_suggestion(incident_id: str, req: RejectSuggestionRequest,
                          user: dict = Depends(require_roles("problem_manager"))):
    try:
        problems.reject_suggestion(incident_id, req.targets, user["username"], db_path=DB_PATH)
        return {"incident_id": incident_id, "rejected": req.targets}
    except problems.ProblemError as exc:
        raise _problem_error(exc)


@app.get("/api/v1/incidents/{incident_id}")
def api_get_incident(incident_id: str, user: dict[str, Any] = Depends(
        require_roles("problem_manager", "technical_expert")
    ),):
    try:
        inc = storage.get_incident(DB_PATH, incident_id)
        # if not inc:
        #     raise HTTPException(status_code=404, detail=f"Incidentul {incident_id} nu a fost găsit.")
        if user["role"] == "technical_expert":
            # the expert reads the incidents of the RCAs sent to the expert, not the whole incident list
            sent = store.list_rcas(db_path=DB_PATH, sent_to_expert=True)
            if not any(incident_id in ((record.context.incident_ids if record.context else []) + [record.incident_id])
                       for record in sent):
                raise HTTPException(status_code=404, detail="Incidentul nu este disponibil pentru review.")
        return _serialize(inc)
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/services")
def api_list_services(user: dict = Depends(require_roles("problem_manager", "technical_expert"))):
    """Every service of the CMDB, for the services the Problem Manager may add to an investigation."""
    return storage.list_services(DB_PATH)


@app.get("/api/v1/services/{service_name}/teams")
def api_teams_for_service(service_name: str,
                          user: dict = Depends(require_roles("problem_manager", "technical_expert"))):
    try:
        items = storage.get_config_items_for_service(DB_PATH, service_name)
        return sorted({item.owner_team for item in items})
    except Exception:
        return []


# 1b. Probleme (Problem Management): every change is made by the Problem Manager, with the rules of rca/problems.py

@app.get("/api/v1/problems")
def api_list_problems(status_filter: Optional[str] = None, user: dict = Depends(require_roles("problem_manager"))):
    return [_serialize(item) for item in problems.list_problems(status_filter, db_path=DB_PATH)]


@app.get("/api/v1/proposals")
def api_proposals(user: dict = Depends(require_roles("problem_manager"))):
    """The Proposed Problem Records: groups of alike incidents, incidents for an open problem, single major
    incidents; each with its score (explained), its reasons and its evidence."""
    try:
        return [asdict(item) for item in suggestions.proposals(DB_PATH)]
    except Exception as exc:  # ChromaDB not built yet: the proposals are missing, the rest still works
        traceback.print_exc()
        raise HTTPException(status_code=503, detail=f"Proposals are not available: {exc}")


def _checked_proposal(req: ProposalRequest) -> tuple[str, str]:
    if req.key != suggestions.proposal_key(req.kind, req.incident_ids, req.problem_id):
        raise HTTPException(status_code=400, detail="The proposal does not match its key: reload the proposals.")
    if req.kind == "attach" and (len(req.incident_ids) != 1 or not req.problem_id):
        raise HTTPException(status_code=400, detail="A proposal to add to a problem has one incident and the problem.")
    return req.key, req.kind


@app.post("/api/v1/proposals/accept")
def api_accept_proposal(req: ProposalRequest, user: dict = Depends(require_roles("problem_manager"))):
    """Accept a proposal: the problem is created (or the incident added) and the proposal marked accepted in one
    transaction, after the rules are checked again. Accepting it again returns the same problem (created false)."""
    proposal = _checked_proposal(req)
    try:
        if req.kind == "attach":
            result = problems.attach_incident(req.problem_id, req.incident_ids[0], user["username"], req.reason,
                                              db_path=DB_PATH, proposal=proposal)
        else:
            result = problems.create_problem(req.incident_ids, user["username"], req.title, None, req.reason,
                                             db_path=DB_PATH, proposal=proposal)
    except problems.ProblemError as exc:
        raise _problem_error(exc)
    return {**_problem_result(result), "created": result.created}


@app.post("/api/v1/proposals/reject")
def api_reject_proposal(req: ProposalRequest, user: dict = Depends(require_roles("problem_manager"))):
    key, kind = _checked_proposal(req)
    try:
        problems.reject_proposal(key, kind, req.incident_ids, user["username"], req.problem_id, req.reason,
                                 db_path=DB_PATH)
    except problems.ProblemError as exc:
        raise _problem_error(exc)
    return {"key": key, "rejected": True}


@app.get("/api/v1/problems/{problem_id}")
def api_get_problem(problem_id: str, user: dict = Depends(require_roles("problem_manager"))):
    problem = storage.get_problem(DB_PATH, problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail=f"Problem '{problem_id}' was not found.")
    return {
        "problem": _serialize(problem),
        "events": [_serialize(item) for item in problems.problem_events(problem_id, DB_PATH)],
        "rcas": [_serialize(item) for item in problems.rcas_of(problem_id, DB_PATH)],
    }


@app.post("/api/v1/problems")
def api_create_problem(req: CreateProblemRequest, user: dict = Depends(require_roles("problem_manager"))):
    try:
        # created here, the problem is the choice of the Problem Manager; a proposal is accepted at /proposals/accept
        return _problem_result(problems.create_problem(req.incident_ids, user["username"], req.title, req.description,
                                                       req.reason, db_path=DB_PATH, manual=True))
    except problems.ProblemError as exc:
        raise _problem_error(exc)


@app.post("/api/v1/problems/{problem_id}/incidents")
def api_attach_incident(problem_id: str, req: AttachIncidentRequest, user: dict = Depends(require_roles("problem_manager"))):
    try:
        return _problem_result(problems.attach_incident(problem_id, req.incident_id, user["username"], req.reason,
                                                        db_path=DB_PATH))
    except problems.ProblemError as exc:
        raise _problem_error(exc)


@app.get("/api/v1/problems/{problem_id}/candidates")
def api_problem_candidates(problem_id: str, user: dict = Depends(require_roles("problem_manager"))):
    """The incidents that may be added to the problem, with their text similarity to it (cosine, 0 to 1)."""
    if storage.get_problem(DB_PATH, problem_id) is None:
        raise HTTPException(status_code=404, detail=f"Problem '{problem_id}' was not found.")
    try:
        return [asdict(item) for item in suggestions.candidates_for_problem(problem_id, DB_PATH)]
    except Exception as exc:  # ChromaDB not built yet: the scores are missing, the rest still works
        traceback.print_exc()
        raise HTTPException(status_code=503, detail=f"Similarity scores are not available: {exc}")


@app.put("/api/v1/problems/{problem_id}/guidance")
def api_set_guidance(problem_id: str, req: GuidanceRequest, user: dict = Depends(require_roles("problem_manager"))):
    """Save the guidance for the investigation of the problem; Start RCA uses it and saves it too."""
    try:
        return _problem_result(problems.set_guidance(problem_id, req.guidance, user["username"], db_path=DB_PATH))
    except problems.ProblemError as exc:
        raise _problem_error(exc)


@app.post("/api/v1/problems/{problem_id}/incidents/{incident_id}/remove")
def api_detach_incident(problem_id: str, incident_id: str, req: ReasonRequest,
                        user: dict = Depends(require_roles("problem_manager"))):
    try:
        return _problem_result(problems.detach_incident(problem_id, incident_id, user["username"], req.reason, db_path=DB_PATH))
    except problems.ProblemError as exc:
        raise _problem_error(exc)


@app.post("/api/v1/problems/{problem_id}/close")
def api_close_problem(problem_id: str, req: ReasonRequest, user: dict = Depends(require_roles("problem_manager"))):
    try:
        return _problem_result(problems.close_problem(problem_id, user["username"], req.reason, db_path=DB_PATH))
    except problems.ProblemError as exc:
        raise _problem_error(exc)


@app.post("/api/v1/problems/{problem_id}/reopen")
def api_reopen_problem(problem_id: str, req: ReasonRequest, user: dict = Depends(require_roles("problem_manager"))):
    try:
        return _problem_result(problems.reopen_problem(problem_id, user["username"], req.reason, db_path=DB_PATH))
    except problems.ProblemError as exc:
        raise _problem_error(exc)


# 2. RCA-uri, revizii și Technical Review (rca/store.py: every change of status is checked there)


def _expert_may_read(rca_id: str) -> bool:
    summary = store.get_summary(rca_id.rsplit("-R", 1)[0] if "-R" in rca_id[9:] else rca_id, db_path=DB_PATH)
    return summary is not None and summary.sent_to_expert


@app.get("/api/v1/rcas")
def api_list_rcas(status: Optional[str] = None, problem_id: Optional[str] = None,
                  user: dict[str, Any] = Depends(require_roles("problem_manager", "technical_expert"))):
    """The latest revision of every RCA, filtered by the status of the RCA. The expert sees only the RCAs
    the Problem Manager sent to the expert."""
    sent = True if user["role"] == "technical_expert" else None
    return [_serialize(r) for r in store.list_rcas(status=status or None, problem_id=problem_id, db_path=DB_PATH,
                                                   sent_to_expert=sent)]


@app.get("/api/v1/rcas/summaries")
def api_rca_summaries(user: dict[str, Any] = Depends(require_roles("problem_manager", "technical_expert"))):
    """Every RCA (models.RCA: its problem, title, status, revisions, decisions, dates), the most recent first.
    The expert sees only the RCAs sent to the expert. Listed as soon as an RCA is created, while it runs."""
    sent = user["role"] == "technical_expert"
    return [_serialize(item) for item in store.list_summaries(db_path=DB_PATH) if item.sent_to_expert or not sent]


@app.get("/api/v1/rcas/{rca_id}")
def api_get_rca(rca_id: str, user: dict[str, Any] = Depends(require_roles("problem_manager", "technical_expert"))):
    """The latest revision of an RCA (RCA-2026-00001), or one revision (RCA-2026-00001-R2)."""
    record = store.get_rca(rca_id, db_path=DB_PATH)
    if record is None or (user["role"] == "technical_expert" and not _expert_may_read(rca_id)):
        raise HTTPException(status_code=404, detail=f"RCA {rca_id} nu a fost găsit.")
    return _serialize(record)


@app.get("/api/v1/rcas/{rca_id}/revisions")
def api_list_revisions(rca_id: str, user: dict[str, Any] = Depends(require_roles("problem_manager", "technical_expert"))):
    if store.get_summary(rca_id, db_path=DB_PATH) is None or (
            user["role"] == "technical_expert" and not _expert_may_read(rca_id)):
        raise HTTPException(status_code=404, detail=f"RCA {rca_id} nu a fost găsit.")
    return [_serialize(r) for r in store.list_revisions(rca_id, db_path=DB_PATH)]


@app.get("/api/v1/rcas/{rca_id}/history")
def api_rca_history(rca_id: str, user: dict[str, Any] = Depends(require_roles("problem_manager", "technical_expert"))):
    """The RCA and every change of its status, the decisions of the expert included."""
    summary = store.get_summary(rca_id, db_path=DB_PATH)
    if summary is None or (user["role"] == "technical_expert" and not summary.sent_to_expert):
        raise HTTPException(status_code=404, detail=f"RCA {rca_id} nu a fost găsit.")
    return {"rca": _serialize(summary), "history": [_serialize(item) for item in store.status_history(rca_id, DB_PATH)]}


@app.post("/api/v1/rcas/{rca_id}/submit-review")
def api_submit_for_review(rca_id: str, user: dict[str, Any] = Depends(require_roles("problem_manager"))):
    try:
        return _serialize(store.submit_for_review(rca_id, user["username"], db_path=DB_PATH))
    except (store.RCAError, store.RCANotFound) as exc:
        raise _rca_error(exc)


@app.post("/api/v1/rcas/{rca_id}/review")
def api_apply_review(rca_id: str, req: ApplyReviewRequest,
                     user: dict[str, Any] = Depends(require_roles("technical_expert"))):
    try:
        return _serialize(store.apply_review(
            rca_id=rca_id, reviewer=user["username"], decision=req.decision, comment=req.comment,
            hypothesis_id=req.hypothesis_id, db_path=DB_PATH, requested_checks=req.requested_checks,
            guidance=req.guidance,
        ))
    except (store.RCAError, store.RCANotFound) as exc:
        raise _rca_error(exc)


# 3. RCA-uri cu reviziile lor (RCA History)

@app.get("/api/v1/cases")
def api_list_cases(user: dict[str, Any] = Depends(require_roles("problem_manager", "technical_expert"))):
    """Every RCA as the list of its revisions, the most recent RCA first."""
    sent = True if user["role"] == "technical_expert" else None
    return [[_serialize(r) for r in case] for case in store.list_cases(db_path=DB_PATH, sent_to_expert=sent)]


@app.get("/api/v1/cases/{rca_id}")
def api_list_case(rca_id: str, user: dict[str, Any] = Depends(require_roles("problem_manager", "technical_expert"))):
    return api_list_revisions(rca_id, user)


# 4. Pipeline Investigație: the RCA and its revision are saved at once, the graph runs in the background


def _run(revision_id: str, owner: str) -> None:
    """Run the graph for a revision that already exists, saving each step as soon as it finishes. An error is
    saved on the revision (FAILED, with the error) by run_investigation; a failure before the run could even
    start is saved here, so no revision stays RUNNING."""
    try:
        run_investigation(revision_id=revision_id, owner=owner, db_path=DB_PATH,
                          on_step=lambda step: store.record_step(revision_id, step, db_path=DB_PATH),
                          on_node_start=lambda name: store.record_current_step(revision_id, name, db_path=DB_PATH))
    except Exception as exc:
        traceback.print_exc()
        store.fail_revision(revision_id, f"{type(exc).__name__}: {exc}", db_path=DB_PATH)


def _launch(started, background: BackgroundTasks, owner: str) -> dict:
    """Run a revision in the background when this request created it. A repeated request (the same
    request_key) gets the revision back without a second run: the store says which request created it."""
    revision, created = started
    if created:
        background.add_task(_run, revision.revision_id, owner)
    return _serialize(revision)


def _start_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, problems.ProblemError):
        return _problem_error(exc)
    if isinstance(exc, (store.RCAError, store.RCANotFound)):
        return _rca_error(exc)
    return HTTPException(status_code=400, detail=str(exc))  # an unknown problem or incident


@app.post("/api/v1/problems/{problem_id}/rcas", status_code=status.HTTP_202_ACCEPTED)
def api_start_rca(problem_id: str, req: StartRCARequest, background: BackgroundTasks,
                  user: dict[str, Any] = Depends(require_roles("problem_manager"))):
    """Start RCA: the RCA and its first revision are saved now (visible at once in RCA History), the graph
    runs in the background. Answers with the revision, RUNNING; the Investigation page follows it."""
    if storage.get_problem(DB_PATH, problem_id) is None:
        raise HTTPException(status_code=404, detail=f"Problem '{problem_id}' was not found.")
    try:
        started = store.begin_rca(problem_id, user["username"], req.guidance, db_path=DB_PATH,
                                  request_key=req.request_key)
    except (problems.ProblemError, store.RCAError, store.RCANotFound, ValueError) as exc:
        raise _start_errors(exc)
    return _launch(started, background, user["username"])


@app.post("/api/v1/rcas/{rca_id}/revisions", status_code=status.HTTP_202_ACCEPTED)
def api_start_next_revision(rca_id: str, req: StartRCARequest, background: BackgroundTasks,
                            user: dict[str, Any] = Depends(require_roles("problem_manager"))):
    """The next revision of an RCA the expert sent back for more details, or whose last run failed."""
    try:
        started = store.begin_next_revision(rca_id, user["username"], req.guidance, db_path=DB_PATH,
                                            request_key=req.request_key)
    except (problems.ProblemError, store.RCAError, store.RCANotFound, ValueError) as exc:
        raise _start_errors(exc)
    return _launch(started, background, user["username"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)