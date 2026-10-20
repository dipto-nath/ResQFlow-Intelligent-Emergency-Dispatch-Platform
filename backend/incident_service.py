"""Incident service - business logic for incident management."""
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from backend.database import get_db_connection, get_db_transaction, parse_json_safe, now_iso, generate_id
from backend.schemas import (
    IncidentCreate, IncidentSummary, IncidentDetail, ExtractedFacts,
    EvidenceSpan, ExtractionResult, PriorityBreakdown
)
from backend.ai_parser import extract_facts
from backend.priority_engine import compute_priority
from backend.evidence import verify_evidence
from backend.config import get_settings


async def create_incident(incident: IncidentCreate) -> Dict[str, Any]:
    incident_id = generate_id("INC")
    now = now_iso()
    
    with get_db_transaction() as conn:
        conn.execute(
            """INSERT INTO incidents
               (id, type, description, latitude, longitude, created_at, status)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            (incident_id, incident.type, incident.description,
             incident.latitude, incident.longitude, now)
        )
        
        conn.execute(
            """INSERT INTO incident_events
               (id, incident_id, event_type, new_value_json, created_at, actor_label)
               VALUES (?, ?, 'created', ?, ?, 'CITIZEN-DEMO')""",
            (generate_id("EVT"), incident_id, json.dumps({"type": incident.type}), now)
        )
        
        conn.commit()
    
    await analyze_incident(incident_id)
    
    return {"id": incident_id, "created_at": now, "status": "pending"}


async def analyze_incident(
    incident_id: str,
    reanalyze: bool = False,
    fault_llm_down: bool = False,
    fault_llm_malformed: bool = False
) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM incidents WHERE id = ?", (incident_id,)
        ).fetchone()
    
    if not row:
        return None
    
    extraction = await extract_facts(
        row["description"], row["type"],
        fault_llm_down, fault_llm_malformed
    )
    
    with get_db_connection() as conn:
        confirmations = conn.execute(
            "SELECT field, value_json FROM fact_confirmations WHERE incident_id = ?",
            (incident_id,)
        ).fetchall()
    
    confirmation_dict = {}
    for c in confirmations:
        confirmation_dict[c["field"]] = parse_json_safe(c["value_json"])
    
    priority = compute_priority(extraction.facts, confirmation_dict)
    
    new_status = "under_review" if priority.needs_review else "pending"
    analysis_status = "completed"
    
    now = now_iso()
    
    with get_db_transaction() as conn:
        conn.execute(
            """UPDATE incidents SET
               extracted_facts_json = ?,
               evidence_json = ?,
               extraction_source = ?,
               uncertainty_flags_json = ?,
               priority_score = ?,
               priority_ceiling = ?,
               priority_level = ?,
               ceiling_level = ?,
               score_breakdown_json = ?,
               priority_explanation = ?,
               needs_review = ?,
               last_analyzed_at = ?,
               analysis_status = ?,
               status = ?
               WHERE id = ?""",
            (
                json.dumps(extraction.facts.model_dump()),
                json.dumps({k: v.model_dump() for k, v in extraction.evidence.items()}),
                extraction.source,
                json.dumps(extraction.uncertainty_flags),
                priority.score,
                priority.ceiling,
                priority.level,
                priority.ceiling_level,
                json.dumps([f.model_dump() for f in priority.breakdown]),
                priority.explanation,
                priority.needs_review,
                now,
                analysis_status,
                new_status,
                incident_id
            )
        )
        
        conn.execute(
            """INSERT INTO incident_events
               (id, incident_id, event_type, new_value_json, created_at, actor_label)
               VALUES (?, ?, 'analyzed', ?, ?, 'AI-DEMO')""",
            (generate_id("EVT"), incident_id, json.dumps({
                "score": priority.score,
                "level": priority.level,
                "source": extraction.source
            }), now)
        )
        
        conn.commit()
    
    return {
        "extraction": extraction.model_dump(),
        "priority": priority.model_dump()
    }


def get_incident_summary(filters: Dict[str, Any] = None) -> List[IncidentSummary]:
    filters = filters or {}
    
    query = "SELECT * FROM incidents WHERE 1=1"
    params = []
    
    if filters.get("status"):
        query += " AND status = ?"
        params.append(filters["status"])
    if filters.get("type"):
        query += " AND type = ?"
        params.append(filters["type"])
    
    query += " ORDER BY priority_score DESC, priority_ceiling DESC, created_at ASC"
    
    with get_db_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    
    results = []
    for row in rows:
        created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
        age = int((datetime.utcnow() - created).total_seconds())
        
        results.append(IncidentSummary(
            id=row["id"],
            type=row["type"],
            description=row["description"][:200] + ("..." if len(row["description"]) > 200 else ""),
            latitude=row["latitude"],
            longitude=row["longitude"],
            created_at=row["created_at"],
            status=row["status"],
            priority_score=row["priority_score"],
            priority_ceiling=row["priority_ceiling"],
            priority_level=row["priority_level"],
            ceiling_level=row["ceiling_level"],
            needs_review=row["needs_review"],
            age_seconds=age
        ))
    
    return results


def get_incident_detail(incident_id: str) -> Optional[IncidentDetail]:
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
    
    if not row:
        return None
    
    with get_db_connection() as conn:
        events = conn.execute(
            "SELECT * FROM incident_events WHERE incident_id = ? ORDER BY created_at",
            (incident_id,)
        ).fetchall()
    
    facts = parse_json_safe(row["extracted_facts_json"], {})
    evidence = parse_json_safe(row["evidence_json"], {})
    flags = parse_json_safe(row["uncertainty_flags_json"], [])
    breakdown = parse_json_safe(row["score_breakdown_json"], [])
    
    evidence_spans = {}
    for k, v in evidence.items():
        if isinstance(v, dict):
            evidence_spans[k] = EvidenceSpan(**v)
    
    from backend.schemas import ScoreFactor
    breakdown_factors = [ScoreFactor(**f) for f in breakdown]
    
    event_list = []
    for e in events:
        event_list.append({
            "id": e["id"],
            "event_type": e["event_type"],
            "old_value": parse_json_safe(e["old_value_json"]),
            "new_value": parse_json_safe(e["new_value_json"]),
            "created_at": e["created_at"],
            "actor_label": e["actor_label"]
        })
    
    return IncidentDetail(
        id=row["id"],
        type=row["type"],
        description=row["description"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        created_at=row["created_at"],
        status=row["status"],
        extracted_facts=ExtractedFacts(**facts) if facts else ExtractedFacts(),
        evidence=evidence_spans,
        extraction_source=row["extraction_source"],
        uncertainty_flags=flags,
        priority_score=row["priority_score"],
        priority_ceiling=row["priority_ceiling"],
        priority_level=row["priority_level"],
        ceiling_level=row["ceiling_level"],
        score_breakdown=breakdown_factors,
        priority_explanation=row["priority_explanation"],
        needs_review=row["needs_review"],
        last_analyzed_at=row["last_analyzed_at"],
        analysis_status=row["analysis_status"],
        events=event_list
    )


def add_fact_confirmation(
    incident_id: str,
    field: str,
    value: Any,
    actor: str = "DISPATCHER-DEMO"
) -> Dict[str, Any]:
    now = now_iso()
    
    with get_db_transaction() as conn:
        old_row = conn.execute(
            "SELECT value_json FROM fact_confirmations WHERE incident_id = ? AND field = ?",
            (incident_id, field)
        ).fetchone()
        
        old_value = parse_json_safe(old_row["value_json"]) if old_row else None
        
        conn.execute(
            """INSERT OR REPLACE INTO fact_confirmations
               (id, incident_id, field, value_json, actor_label, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (generate_id("FC"), incident_id, field, json.dumps(value), actor, now)
        )
        
        conn.execute(
            """INSERT INTO incident_events
               (id, incident_id, event_type, old_value_json, new_value_json, created_at, actor_label)
               VALUES (?, ?, 'confirmation', ?, ?, ?, ?)""",
            (generate_id("EVT"), incident_id,
             json.dumps(old_value) if old_value is not None else None,
             json.dumps(value), now, actor)
        )
        
        incident_row = conn.execute(
            "SELECT * FROM incidents WHERE id = ?", (incident_id,)
        ).fetchone()
        
        if incident_row:
            facts = parse_json_safe(incident_row["extracted_facts_json"], {})
            extraction_facts = ExtractedFacts(**facts) if facts else ExtractedFacts()
            
            all_confirmations = conn.execute(
                "SELECT field, value_json FROM fact_confirmations WHERE incident_id = ?",
                (incident_id,)
            ).fetchall()
            
            confirmation_dict = {}
            for c in all_confirmations:
                confirmation_dict[c["field"]] = parse_json_safe(c["value_json"])
            
            priority = compute_priority(extraction_facts, confirmation_dict)
            
            conn.execute(
                """UPDATE incidents SET
                   priority_score = ?,
                   priority_ceiling = ?,
                   priority_level = ?,
                   ceiling_level = ?,
                   score_breakdown_json = ?,
                   priority_explanation = ?,
                   needs_review = ?,
                   last_analyzed_at = ?
                   WHERE id = ?""",
                (priority.score, priority.ceiling, priority.level,
                 priority.ceiling_level,
                 json.dumps([f.model_dump() for f in priority.breakdown]),
                 priority.explanation, priority.needs_review, now, incident_id)
            )
            
            conn.commit()
            
            return {
                "old_score": incident_row["priority_score"],
                "new_score": priority.score,
                "old_level": incident_row["priority_level"],
                "new_level": priority.level,
                "delta": priority.score - incident_row["priority_score"]
            }
    
    return {}


def flag_incident(incident_id: str, reason: str) -> bool:
    now = now_iso()
    
    with get_db_transaction() as conn:
        conn.execute(
            """INSERT INTO incident_events
               (id, incident_id, event_type, new_value_json, created_at, actor_label)
               VALUES (?, ?, 'flagged', ?, ?, 'DISPATCHER-DEMO')""",
            (generate_id("EVT"), incident_id, json.dumps({"reason": reason}), now)
        )
        conn.commit()
    
    return True


def resolve_incident(incident_id: str) -> bool:
    now = now_iso()
    
    with get_db_transaction() as conn:
        conn.execute(
            "UPDATE incidents SET status = 'resolved' WHERE id = ?",
            (incident_id,)
        )
        conn.execute(
            """INSERT INTO incident_events
               (id, incident_id, event_type, created_at, actor_label)
               VALUES (?, ?, 'resolved', ?, 'DISPATCHER-DEMO')""",
            (generate_id("EVT"), incident_id, now)
        )
        conn.commit()
    
    return True