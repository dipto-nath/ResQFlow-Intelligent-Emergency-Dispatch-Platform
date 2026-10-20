"""Main FastAPI application for Sahayak Dispatch."""
from contextlib import asynccontextmanager
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import json

from backend.config import get_settings
from backend.database import init_database, reset_database
from backend.schemas import (
    IncidentCreate, IncidentSummary, IncidentDetail,
    ResponderSummary, DispatchCreate, DispatchResponse,
    FaultFlags, ScenarioPlayRequest, ConcurrencyTestResult,
    HealthResponse, SummaryResponse, EvaluationMetrics
)
from backend.incident_service import (
    create_incident, get_incident_summary, get_incident_detail,
    add_fact_confirmation, flag_incident, resolve_incident, analyze_incident
)
from backend.dispatch_service import create_dispatch, complete_dispatch, cancel_dispatch, get_dispatches, DispatchConflict
from backend.demo_controls import (
    get_fault_state, set_fault_state, play_scenario,
    run_concurrency_test, run_evaluation, reset_demo, SCENARIOS
)
from backend.routing_service import get_route


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    import asyncio
    from backend.demo_controls import seed_demo_data
    asyncio.create_task(seed_demo_data())
    yield


settings = get_settings()

app = FastAPI(
    title="Sahayak Dispatch",
    description="Intelligent Emergency Dispatch Decision Support - Demo Prototype",
    version="1.0.0-prototype",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DispatchConflict)
async def dispatch_conflict_handler(request, exc: DispatchConflict):
    return JSONResponse(
        status_code=409,
        content={
            "error": "responder_unavailable",
            "responder_id": exc.responder_id,
            "taken_by": exc.taken_by,
            "taken_at": "",
            "next_best": [r.model_dump() for r in exc.next_best]
        }
    )


@app.exception_handler(ValueError)
async def value_error_handler(request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc), "code": "INVALID_INPUT"}
    )


# Health & Status
@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="ok",
        version="1.0.0-prototype",
        demo_mode=settings.demo_mode
    )


@app.get("/summary", response_model=SummaryResponse)
async def get_summary():
    from backend.database import get_db_connection
    with get_db_connection() as conn:
        open_incidents = conn.execute(
            "SELECT COUNT(*) as cnt FROM incidents WHERE status IN ('pending', 'under_review')"
        ).fetchone()["cnt"]
        available_responders = conn.execute(
            "SELECT COUNT(*) as cnt FROM responders WHERE status = 'available'"
        ).fetchone()["cnt"]
        active_dispatches = conn.execute(
            "SELECT COUNT(*) as cnt FROM dispatches WHERE status = 'active'"
        ).fetchone()["cnt"]
    
    return SummaryResponse(
        open_incidents=open_incidents,
        available_responders=available_responders,
        active_dispatches=active_dispatches,
        last_updated=__import__('datetime').datetime.utcnow().isoformat() + "Z"
    )


# Incidents
@app.post("/incidents", status_code=201)
async def create_incident_endpoint(incident: IncidentCreate):
    result = await create_incident(incident)
    return result


@app.get("/incidents", response_model=List[IncidentSummary])
async def list_incidents(
    status: Optional[str] = Query(None),
    type: Optional[str] = Query(None)
):
    filters = {}
    if status:
        filters["status"] = status
    if type:
        filters["type"] = type
    return get_incident_summary(filters)


@app.get("/incidents/{incident_id}", response_model=IncidentDetail)
async def get_incident(incident_id: str):
    incident = get_incident_detail(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@app.post("/incidents/{incident_id}/analyze")
async def analyze_incident_endpoint(
    incident_id: str,
    reanalyze: bool = False,
    fault_llm_down: bool = False,
    fault_llm_malformed: bool = False
):
    result = await analyze_incident(
        incident_id, reanalyze,
        fault_llm_down or get_fault_state().llm_down,
        fault_llm_malformed or get_fault_state().llm_malformed
    )
    if not result:
        raise HTTPException(status_code=404, detail="Incident not found")
    return result


@app.post("/incidents/{incident_id}/confirmations")
async def add_confirmation(incident_id: str, field: str, value: dict):
    result = add_fact_confirmation(incident_id, field, value)
    if not result:
        raise HTTPException(status_code=404, detail="Incident not found")
    return result


@app.post("/incidents/{incident_id}/flag")
async def flag_incident_endpoint(incident_id: str, reason: str):
    success = flag_incident(incident_id, reason)
    if not success:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"status": "flagged"}


@app.post("/incidents/{incident_id}/resolve")
async def resolve_incident_endpoint(incident_id: str):
    success = resolve_incident(incident_id)
    if not success:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"status": "resolved"}


@app.get("/incidents/{incident_id}/events")
async def get_incident_events(incident_id: str):
    from backend.database import get_db_connection, parse_json_safe
    with get_db_connection() as conn:
        events = conn.execute(
            "SELECT * FROM incident_events WHERE incident_id = ? ORDER BY created_at",
            (incident_id,)
        ).fetchall()
    return [{
        "id": e["id"],
        "event_type": e["event_type"],
        "old_value": parse_json_safe(e["old_value_json"]),
        "new_value": parse_json_safe(e["new_value_json"]),
        "created_at": e["created_at"],
        "actor_label": e["actor_label"]
    } for e in events]


# Responders
@app.get("/responders", response_model=List[ResponderSummary])
async def list_responders(
    type: Optional[str] = Query(None),
    status: Optional[str] = Query(None)
):
    from backend.database import get_db_connection, parse_json_safe
    query = "SELECT * FROM responders WHERE 1=1"
    params = []
    
    if type:
        query += " AND unit_type = ?"
        params.append(type)
    if status:
        query += " AND status = ?"
        params.append(status)
    
    with get_db_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    
    return [ResponderSummary(
        id=r["id"],
        unit_type=r["unit_type"],
        latitude=r["latitude"],
        longitude=r["longitude"],
        status=r["status"],
        capabilities=parse_json_safe(r["capabilities_json"], []),
        updated_at=r["updated_at"]
    ) for r in rows]


# Recommendations
@app.get("/incidents/{incident_id}/recommendations")
async def get_recommendations(
    incident_id: str,
    fault_routing_down: bool = False
):
    from backend.incident_service import get_incident_detail
    from backend.responder_matcher import get_recommendations
    
    incident = get_incident_detail(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    if not fault_routing_down:
        fault_routing_down = get_fault_state().routing_down
    
    recommendations = get_recommendations(
        incident_id,
        incident.latitude,
        incident.longitude,
        incident.extracted_facts,
        fault_routing_down=fault_routing_down
    )
    return recommendations.model_dump()


# Dispatches
@app.post("/dispatches", status_code=201)
async def create_dispatch_endpoint(
    dispatch: DispatchCreate,
    fault_routing_down: bool = False
):
    if not fault_routing_down:
        fault_routing_down = get_fault_state().routing_down
    
    try:
        result = create_dispatch(dispatch, fault_routing_down=fault_routing_down)
        return result
    except DispatchConflict as e:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "responder_unavailable",
                "responder_id": e.responder_id,
                "taken_by": e.taken_by,
                "taken_at": __import__('datetime').datetime.utcnow().isoformat() + "Z",
                "next_best": [r.model_dump() for r in e.next_best]
            }
        )


@app.post("/dispatches/{dispatch_id}/complete")
async def complete_dispatch_endpoint(dispatch_id: str):
    success = complete_dispatch(dispatch_id)
    if not success:
        raise HTTPException(status_code=404, detail="Dispatch not found or not active")
    return {"status": "completed"}


@app.post("/dispatches/{dispatch_id}/cancel")
async def cancel_dispatch_endpoint(dispatch_id: str):
    success = cancel_dispatch(dispatch_id)
    if not success:
        raise HTTPException(status_code=404, detail="Dispatch not found or not active")
    return {"status": "cancelled"}


@app.get("/dispatches")
async def list_dispatches(incident_id: Optional[str] = None):
    return get_dispatches(incident_id)


# Demo Controls (only in demo mode)
@app.get("/demo/faults", response_model=FaultFlags)
async def get_faults():
    if not settings.demo_mode:
        raise HTTPException(status_code=404)
    return get_fault_state()


@app.post("/demo/faults", response_model=FaultFlags)
async def set_faults(flags: FaultFlags):
    if not settings.demo_mode:
        raise HTTPException(status_code=404)
    return set_fault_state(flags)


@app.post("/demo/scenarios/{scenario_id}/play")
async def play_scenario_endpoint(scenario_id: str):
    if not settings.demo_mode:
        raise HTTPException(status_code=404)
    
    result = await play_scenario(
        scenario_id,
        get_fault_state().llm_down,
        get_fault_state().llm_malformed
    )
    return result


@app.post("/demo/concurrency-proof", response_model=ConcurrencyTestResult)
async def concurrency_proof():
    if not settings.demo_mode:
        raise HTTPException(status_code=404)
    return await run_concurrency_test()


@app.post("/demo/evaluation/run")
async def run_evaluation_endpoint():
    if not settings.demo_mode:
        raise HTTPException(status_code=404)
    return await run_evaluation()


@app.get("/demo/evaluation/latest")
async def get_latest_evaluation():
    if not settings.demo_mode:
        raise HTTPException(status_code=404)
    
    import os
    eval_path = os.path.join(os.path.dirname(__file__), "..", "evaluation", "latest.json")
    if os.path.exists(eval_path):
        with open(eval_path) as f:
            return json.load(f)
    return {"measured": False}


@app.post("/demo/reset")
async def reset_demo_endpoint():
    if not settings.demo_mode:
        raise HTTPException(status_code=404)
    return reset_demo()


@app.get("/demo/scenarios")
async def list_scenarios():
    if not settings.demo_mode:
        raise HTTPException(status_code=404)
    return {k: {"name": v["name"], "talking_point": v["talking_point"]} for k, v in SCENARIOS.items()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)