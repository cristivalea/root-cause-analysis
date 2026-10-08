import json
from dataclasses import asdict
import os
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from streamlit import user

from rca import problems, storage, store, suggestions
from rca.config import DB_PATH
from rca.models import Incident, InvestigationGuidance, RCARecord, RCAStatus
from rca.pipeline import run_investigation

from datetime import datetime, timedelta, timezone
import os

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from rca import auth
from rca import observability

observability.setup()
app = FastAPI(
    title="Root Cause Analysis Multi-Agent Engine API",
    description="Backend decuplat pentru analiză RCA și HITL Problem Management",
    version="1.0.0"
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

class StartInvestigationRequest(BaseModel):
    incident_id: str
    owner: str
    guidance: InvestigationGuidance | None = None  # optional notes and wider search from the Problem Manager
    previous_rca_id: str | None = None  # an RCA sent back for more details: run its next revision


class ApplyReviewRequest(BaseModel):
    reviewer: str
    decision: str
    comment: str
    hypothesis_id: Optional[str] = None
    requested_checks: Optional[List[str]] = None
    guidance: InvestigationGuidance | None = None  # wider searches the expert asks for, with REQUEST_MORE_DETAILS


class CreateProblemRequest(BaseModel):
    incident_ids: List[str]
    title: Optional[str] = None
    description: Optional[str] = None
    move_reason: Optional[str] = None  # needed when an incident is moved from another problem


class AttachIncidentRequest(BaseModel):
    incident_id: str
    move_reason: Optional[str] = None


class ReasonRequest(BaseModel):
    reason: str


class RejectSuggestionRequest(BaseModel):
    targets: List[str]  # the suggested problem, or the incidents of a proposed new problem


def _problem_result(result: problems.Result) -> dict:
    return {"problem": _serialize(result.problem), "warnings": result.warnings}


class LinkCaseRequest(BaseModel):
    previous_rca_id: str
    new_rca_id: str


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
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/v1/incidents/{incident_id}/dismiss")
def api_dismiss_incident(incident_id: str, req: ReasonRequest, user: dict = Depends(require_roles("problem_manager"))):
    try:
        problems.dismiss_incident(incident_id, user["username"], req.reason, db_path=DB_PATH)
        return {"incident_id": incident_id, "dismissed": True}
    except problems.ProblemError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/v1/incidents/{incident_id}")
def api_get_incident(incident_id: str, user: dict[str, Any] = Depends(
        require_roles("problem_manager", "technical_expert")
    ),):
    try:
        inc = storage.get_incident(DB_PATH, incident_id)
        # if not inc:
        #     raise HTTPException(status_code=404, detail=f"Incidentul {incident_id} nu a fost găsit.")
        if user["role"] == "technical_expert":
            pending = store.list_rcas(status="PENDING_REVIEW", db_path=DB_PATH)
            if not any(record.incident_id == incident_id for record in pending):
                raise HTTPException(status_code=404, detail="Incidentul nu este disponibil pentru review.")
        return _serialize(inc)
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/services")
def api_list_services():
    """Every service of the CMDB, for the services the Problem Manager may add to an investigation."""
    return storage.list_services(DB_PATH)


@app.get("/api/v1/services/{service_name}/teams")
def api_teams_for_service(service_name: str):
    try:
        items = storage.get_config_items_for_service(DB_PATH, service_name)
        return sorted({item.owner_team for item in items})
    except Exception:
        return []


# 1b. Probleme (Problem Management): every change is made by the Problem Manager, with the rules of rca/problems.py

@app.get("/api/v1/problems")
def api_list_problems(status_filter: Optional[str] = None, user: dict = Depends(require_roles("problem_manager"))):
    return [_serialize(item) for item in problems.list_problems(status_filter, db_path=DB_PATH)]


@app.get("/api/v1/problems/proposed")
def api_proposed_problems(user: dict = Depends(require_roles("problem_manager"))):
    """Groups of at least three alike incidents in no problem, proposed as new problems."""
    try:
        return suggestions.proposed_problems(DB_PATH)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=503, detail=f"Proposed problems are not available: {exc}")


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
        return _problem_result(problems.create_problem(req.incident_ids, user["username"], req.title, req.description,
                                                       req.move_reason, db_path=DB_PATH))
    except problems.ProblemError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/v1/problems/{problem_id}/incidents")
def api_attach_incident(problem_id: str, req: AttachIncidentRequest, user: dict = Depends(require_roles("problem_manager"))):
    try:
        return _problem_result(problems.attach_incident(problem_id, req.incident_id, user["username"], req.move_reason,
                                                        db_path=DB_PATH))
    except problems.ProblemError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/v1/problems/{problem_id}/incidents/{incident_id}/remove")
def api_detach_incident(problem_id: str, incident_id: str, req: ReasonRequest,
                        user: dict = Depends(require_roles("problem_manager"))):
    try:
        return _problem_result(problems.detach_incident(problem_id, incident_id, user["username"], req.reason, db_path=DB_PATH))
    except problems.ProblemError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/v1/problems/{problem_id}/close")
def api_close_problem(problem_id: str, req: ReasonRequest, user: dict = Depends(require_roles("problem_manager"))):
    try:
        return _problem_result(problems.close_problem(problem_id, user["username"], req.reason, db_path=DB_PATH))
    except problems.ProblemError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/v1/problems/{problem_id}/reopen")
def api_reopen_problem(problem_id: str, req: ReasonRequest, user: dict = Depends(require_roles("problem_manager"))):
    try:
        return _problem_result(problems.reopen_problem(problem_id, user["username"], req.reason, db_path=DB_PATH))
    except problems.ProblemError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# 2. Rapoarte RCA & Technical Review (HITL)

@app.get("/api/v1/rcas")
def api_list_rcas(
    status: Optional[str] = None,
    user: dict[str, Any] = Depends(
        require_roles("problem_manager", "technical_expert")
    ),
):
    try:
        rca_status = None
        if status:
            try:
                rca_status = RCAStatus(status)
            except Exception:
                rca_status = status

        # records = store.list_rcas(status=rca_status, db_path=DB_PATH)
        if user["role"] == "technical_expert":
            records = store.list_rcas(status="PENDING_REVIEW", db_path=DB_PATH)
        else:
            records = store.list_rcas(status=rca_status, db_path=DB_PATH)
        return [_serialize(r) for r in records]
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/rcas/{rca_id}")
def api_get_rca(rca_id: str, user: dict[str, Any] = Depends(
        require_roles("problem_manager", "technical_expert")
    ),):
    try:
        rca = store.get_rca(rca_id, db_path=DB_PATH)
        # if not rca:
        #     raise HTTPException(status_code=404, detail=f"RCA {rca_id} nu a fost găsit.")
        if user["role"] == "technical_expert" and rca.status != "PENDING_REVIEW":
            raise HTTPException(status_code=404, detail="RCA-ul nu este disponibil pentru review.")
        return _serialize(rca)
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/v1/rcas/{rca_id}/submit-review")
def api_submit_for_review(rca_id: str):
    try:
        updated = store.submit_for_review(rca_id, db_path=DB_PATH)
        return _serialize(updated)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


# @app.post("/api/v1/rcas/{rca_id}/review")
# def api_apply_review(rca_id: str, req: ApplyReviewRequest):
#     try:
#         result = store.apply_review(
#             rca_id=rca_id,
#             reviewer=req.reviewer,
#             decision=req.decision,
#             comment=req.comment,
#             hypothesis_id=req.hypothesis_id,
#             db_path=DB_PATH,
#             requested_checks=req.requested_checks,
#         )
#         return _serialize(result)
#     except Exception as exc:
#         traceback.print_exc()
#         raise HTTPException(status_code=500, detail=str(exc))

@app.post("/api/v1/rcas/{rca_id}/review")
def api_apply_review(
    rca_id: str,
    req: ApplyReviewRequest,
    user: dict[str, Any] = Depends(require_roles("technical_expert")),
):
    try:
        result = store.apply_review(
            rca_id=rca_id,
            reviewer=user["username"],
            decision=req.decision,
            comment=req.comment,
            hypothesis_id=req.hypothesis_id,
            db_path=DB_PATH,
            requested_checks=req.requested_checks,
            guidance=req.guidance,
        )
        return _serialize(result)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


# 3. Cazuri (History)

@app.get("/api/v1/cases")
def api_list_cases():
    try:
        cases = store.list_cases(db_path=DB_PATH)
        return [[_serialize(r) for r in case] for case in cases]
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/cases/{case_id}")
def api_list_case(case_id: str):
    try:
        case = store.list_case(case_id, db_path=DB_PATH)
        return [_serialize(r) for r in case]
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/v1/cases/link")
def api_link_to_case(req: LinkCaseRequest):
    try:
        linked = store.start_next_cycle(req.previous_rca_id, req.new_rca_id, db_path=DB_PATH)
        return _serialize(linked)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


# 4. Pipeline Investigație

@app.post("/api/v1/investigations/start")
def api_start_investigation(req: StartInvestigationRequest):
    try:
        result = run_investigation(
            incident_id=req.incident_id,
            owner=req.owner,
            db_path=DB_PATH,
            on_step=None,
            guidance=req.guidance,
            previous_rca_id=req.previous_rca_id,
        )
        return _serialize(result)
    except ValueError as exc:  # an unknown incident or a service the CMDB does not know
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)