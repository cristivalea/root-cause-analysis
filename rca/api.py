import os
import traceback
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from rca import storage, store
from rca.config import DB_PATH
from rca.models import Incident, RCARecord, RCAStatus
from rca.pipeline import run_investigation

app = FastAPI(
    title="Root Cause Analysis Multi-Agent Engine API",
    description="Enterprise SRE/ITIL Problem Management AI Engine Backend",
    version="1.0.0"
)


# --- DTO-uri pentru cereri ---

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


# --- Rute API ---

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

@app.get("/api/v1/incidents", response_model=List[Incident])
def api_list_incidents():
    """Returnează lista completă a incidentelor pentru interfața Streamlit."""
    try:
        incidents = storage.list_incidents(DB_PATH)
        return sorted(incidents, key=lambda inc: inc.detected_at, reverse=True)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/incidents/{incident_id}", response_model=Optional[Incident])
def api_get_incident(incident_id: str):
    """Returnează detaliile complete ale unui incident specific."""
    try:
        inc = storage.get_incident(DB_PATH, incident_id)
        if not inc:
            raise HTTPException(status_code=404, detail=f"Incidentul {incident_id} nu a fost găsit.")
        return inc
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/services/{service_name}/teams", response_model=List[str])
def api_teams_for_service(service_name: str):
    """Returnează echipele responsabile din CMDB pentru un serviciu."""
    try:
        items = storage.get_config_items_for_service(DB_PATH, service_name)
        return sorted({item.owner_team for item in items})
    except Exception:
        return []


# 2. Rapoarte RCA & Technical Review (HITL)

@app.get("/api/v1/rcas", response_model=List[RCARecord])
def api_list_rcas(status: Optional[str] = None):
    """Returnează analizele RCA stocate, filtrate opțional după status."""
    try:
        rca_status = None
        if status:
            try:
                rca_status = RCAStatus(status)
            except (ValueError, KeyError, AttributeError):
                rca_status = status

        return store.list_rcas(status=rca_status, db_path=DB_PATH)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/rcas/{rca_id}", response_model=Optional[RCARecord])
def api_get_rca(rca_id: str):
    """Extrage un raport RCA după identificator."""
    try:
        rca = store.get_rca(rca_id, db_path=DB_PATH)
        if not rca:
            raise HTTPException(status_code=404, detail=f"RCA {rca_id} nu a fost găsit.")
        return rca
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/v1/rcas/{rca_id}/submit-review", response_model=RCARecord)
def api_submit_for_review(rca_id: str):
    """Trimite analiza către Technical Expert."""
    try:
        return store.submit_for_review(rca_id, db_path=DB_PATH)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/v1/rcas/{rca_id}/review", response_model=RCARecord)
def api_apply_review(rca_id: str, req: ApplyReviewRequest):
    """Înregistrează decizia expertului uman: Approve, Reject sau Request More Details."""
    try:
        return store.apply_review(
            rca_id=rca_id,
            reviewer=req.reviewer,
            decision=req.decision,
            comment=req.comment,
            hypothesis_id=req.hypothesis_id,
            db_path=DB_PATH,
            requested_checks=req.requested_checks,
        )
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


# 3. Istoric Cazuri (History)

@app.get("/api/v1/cases", response_model=List[List[RCARecord]])
def api_list_cases():
    """Returnează toate cazurile de investigație grupate pe cicluri."""
    try:
        return store.list_cases(db_path=DB_PATH)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/v1/cases/{case_id}", response_model=List[RCARecord])
def api_list_case(case_id: str):
    """Returnează istoricul de investigații pentru un caz anume."""
    try:
        return store.list_case(case_id, db_path=DB_PATH)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/v1/cases/link", response_model=RCARecord)
def api_link_to_case(req: LinkCaseRequest):
    """Leagă o investigație nouă la ciclul anterior al cazului."""
    try:
        return store.start_next_cycle(req.previous_rca_id, req.new_rca_id, db_path=DB_PATH)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


# 4. Rulare Investigație Multi-Agent

@app.post("/api/v1/investigations/start", response_model=RCARecord)
def api_start_investigation(req: StartInvestigationRequest):
    """Execută pipeline-ul complet multi-agent direct pe backend."""
    try:
        return run_investigation(
            incident_id=req.incident_id,
            owner=req.owner,
            db_path=DB_PATH,
            on_step=None
        )
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)