"""Dispatch service - atomic dispatch with conflict detection."""
import json
from typing import List, Dict, Any, Optional
from backend.database import get_db_connection, get_db_transaction, parse_json_safe, now_iso, generate_id
from backend.schemas import DispatchCreate, DispatchResponse, DispatchConflictResponse, ResponderRecommendation, RouteSource
from backend.responder_matcher import get_recommendations
from backend.incident_service import get_incident_detail
from backend.config import get_settings


def create_dispatch(
    dispatch: DispatchCreate,
    fault_routing_down: bool = False
) -> Dict[str, Any]:
    incident = get_incident_detail(dispatch.incident_id)
    if not incident:
        raise ValueError("Incident not found")
    
    if incident.status not in ("pending", "under_review"):
        raise ValueError(f"Incident not dispatchable: status is {incident.status}")
    
    recommendations = get_recommendations(
        incident.id,
        incident.latitude,
        incident.longitude,
        incident.extracted_facts,
        fault_routing_down=fault_routing_down
    )
    
    valid_responder_ids = {r.responder_id for r in recommendations.recommendations}
    for responder_id in dispatch.responder_ids:
        if responder_id not in valid_responder_ids:
            raise ValueError(f"Responder {responder_id} is not a valid recommendation")
    
    now = now_iso()
    dispatch_ids = []
    
    with get_db_transaction() as conn:
        for responder_id in dispatch.responder_ids:
            cursor = conn.execute(
                """UPDATE responders SET status = 'busy', updated_at = ?
                   WHERE id = ? AND status = 'available'""",
                (now, responder_id)
            )
            if cursor.rowcount == 0:
                taken_row = conn.execute(
                    "SELECT id FROM dispatches WHERE responder_id = ? AND status = 'active'",
                    (responder_id,)
                ).fetchone()
                taken_by = taken_row["id"] if taken_row else "unknown"
                
                next_best = []
                for rec in recommendations.recommendations:
                    if rec.responder_id != responder_id:
                        next_best.append(ResponderRecommendation(
                            responder_id=rec.responder_id,
                            unit_type=rec.unit_type,
                            status=rec.status,
                            matched_capabilities=rec.matched_capabilities,
                            eta_seconds=rec.eta_seconds,
                            distance_m=rec.distance_m,
                            route_source=rec.route_source,
                            route_geometry=rec.route_geometry,
                            why=rec.why,
                            recommended_at=rec.recommended_at,
                            stale_after_seconds=rec.stale_after_seconds
                        ))
                        break
                
                raise DispatchConflict(
                    responder_id=responder_id,
                    taken_by=taken_by,
                    next_best=next_best
                )
            
            dispatch_id = generate_id("DSP")
            dispatch_ids.append(dispatch_id)
            
            route_source = RouteSource.unavailable
            eta_seconds = None
            route_geometry = None
            
            for rec in recommendations.recommendations:
                if rec.responder_id == responder_id:
                    route_source = rec.route_source
                    eta_seconds = rec.eta_seconds
                    route_geometry = rec.route_geometry
                    break
            
            conn.execute(
                """INSERT INTO dispatches
                   (id, incident_id, responder_id, status, approved_at, eta_seconds, route_source, route_geometry_json)
                   VALUES (?, ?, ?, 'active', ?, ?, ?, ?)""",
                (dispatch_id, dispatch.incident_id, responder_id, now,
                 eta_seconds, route_source,
                 json.dumps(route_geometry) if route_geometry else None)
            )
        
        conn.execute(
            "UPDATE incidents SET status = 'dispatched' WHERE id = ?",
            (dispatch.incident_id,)
        )
        
        for responder_id in dispatch.responder_ids:
            conn.execute(
                """INSERT INTO incident_events
                   (id, incident_id, event_type, new_value_json, created_at, actor_label)
                   VALUES (?, ?, 'dispatched', ?, ?, ?)""",
                (generate_id("EVT"), dispatch.incident_id,
                 json.dumps({"responder_id": responder_id, "dispatcher": dispatch.dispatcher_id}),
                 now, dispatch.dispatcher_id)
            )
        
        conn.commit()
    
    if len(dispatch_ids) == 1:
        return DispatchResponse(
            id=dispatch_ids[0],
            incident_id=dispatch.incident_id,
            responder_id=dispatch.responder_ids[0],
            status="active",
            approved_at=now,
            eta_seconds=eta_seconds,
            route_source=route_source
        )
    
    return {"dispatch_ids": dispatch_ids, "incident_id": dispatch.incident_id}


class DispatchConflict(Exception):
    def __init__(self, responder_id: str, taken_by: str, next_best: List[ResponderRecommendation]):
        self.responder_id = responder_id
        self.taken_by = taken_by
        self.next_best = next_best
        super().__init__(f"Responder {responder_id} is no longer available")


def complete_dispatch(dispatch_id: str) -> bool:
    now = now_iso()
    
    with get_db_transaction() as conn:
        dispatch = conn.execute(
            "SELECT * FROM dispatches WHERE id = ? AND status = 'active'",
            (dispatch_id,)
        ).fetchone()
        
        if not dispatch:
            return False
        
        conn.execute(
            "UPDATE dispatches SET status = 'completed', completed_at = ? WHERE id = ?",
            (now, dispatch_id)
        )
        
        conn.execute(
            "UPDATE responders SET status = 'available', updated_at = ? WHERE id = ?",
            (now, dispatch["responder_id"])
        )
        
        conn.execute(
            """INSERT INTO incident_events
               (id, incident_id, event_type, new_value_json, created_at, actor_label)
               VALUES (?, ?, 'completed', ?, ?, 'DISPATCHER-DEMO')""",
            (generate_id("EVT"), dispatch["incident_id"],
             json.dumps({"dispatch_id": dispatch_id}), now)
        )
        
        conn.commit()
    
    return True


def cancel_dispatch(dispatch_id: str) -> bool:
    now = now_iso()
    
    with get_db_transaction() as conn:
        dispatch = conn.execute(
            "SELECT * FROM dispatches WHERE id = ? AND status = 'active'",
            (dispatch_id,)
        ).fetchone()
        
        if not dispatch:
            return False
        
        conn.execute(
            "UPDATE dispatches SET status = 'cancelled', cancelled_at = ? WHERE id = ?",
            (now, dispatch_id)
        )
        
        conn.execute(
            "UPDATE responders SET status = 'available', updated_at = ? WHERE id = ?",
            (now, dispatch["responder_id"])
        )
        
        conn.execute(
            """INSERT INTO incident_events
               (id, incident_id, event_type, new_value_json, created_at, actor_label)
               VALUES (?, ?, 'cancelled', ?, ?, 'DISPATCHER-DEMO')""",
            (generate_id("EVT"), dispatch["incident_id"],
             json.dumps({"dispatch_id": dispatch_id}), now)
        )
        
        conn.commit()
    
    return True


def get_dispatches(incident_id: Optional[str] = None) -> List[Dict[str, Any]]:
    query = "SELECT * FROM dispatches WHERE 1=1"
    params = []
    
    if incident_id:
        query += " AND incident_id = ?"
        params.append(incident_id)
    
    query += " ORDER BY approved_at DESC"
    
    with get_db_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    
    return [dict(row) for row in rows]