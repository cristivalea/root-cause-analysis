import json
import os
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from rca import storage, store
from rca.config import DB_PATH
from rca.models import Incident, RCARecord, RCAStatus
from rca.pipeline import run_investigation

app = FastAPI(
    title="Root Cause Analysis Multi-Agent Engine API",
    description="Backend decuplat pentru analiză RCA și HITL Problem Management",
    version="1.0.0"
)


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


class ApplyReviewRequest(BaseModel):
    reviewer: str
    decision: str
    comment: str
    hypothesis_id: Optional[str] = None
    requested_checks: Optional[List[str]] = None


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


# 1. Incidente & CMDB

@app.get("/api/v1/incidents")
def api_list_incidents():
    try:
        incidents = storage.list_incidents(DB_PATH)
        sorted_incidents = sorted(incidents, key=lambda inc: inc.detected_at, reverse=True)
        return [_serialize(inc) for inc in sorted_incidents]
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/incidents/{incident_id}")
def api_get_incident(incident_id: str):
    try:
        inc = storage.get_incident(DB_PATH, incident_id)
        if not inc:
            raise HTTPException(status_code=404, detail=f"Incidentul {incident_id} nu a fost găsit.")
        return _serialize(inc)
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/services/{service_name}/teams")
def api_teams_for_service(service_name: str):
    try:
        items = storage.get_config_items_for_service(DB_PATH, service_name)
        return sorted({item.owner_team for item in items})
    except Exception:
        return []


# 2. Rapoarte RCA & Technical Review (HITL)

@app.get("/api/v1/rcas")
def api_list_rcas(status: Optional[str] = None):
    try:
        rca_status = None
        if status:
            try:
                rca_status = RCAStatus(status)
            except Exception:
                rca_status = status

        records = store.list_rcas(status=rca_status, db_path=DB_PATH)
        return [_serialize(r) for r in records]
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/rcas/{rca_id}")
def api_get_rca(rca_id: str):
    try:
        rca = store.get_rca(rca_id, db_path=DB_PATH)
        if not rca:
            raise HTTPException(status_code=404, detail=f"RCA {rca_id} nu a fost găsit.")
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


@app.post("/api/v1/rcas/{rca_id}/review")
def api_apply_review(rca_id: str, req: ApplyReviewRequest):
    try:
        result = store.apply_review(
            rca_id=rca_id,
            reviewer=req.reviewer,
            decision=req.decision,
            comment=req.comment,
            hypothesis_id=req.hypothesis_id,
            db_path=DB_PATH,
            requested_checks=req.requested_checks,
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
            on_step=None
        )
        return _serialize(result)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)