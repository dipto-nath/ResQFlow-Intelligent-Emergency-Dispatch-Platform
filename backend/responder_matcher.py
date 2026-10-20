"""Responder matching with 'why not' ledger and capability-aware filtering."""
import math
from typing import List, Dict, Optional, Tuple, Any
from backend.schemas import (
    ResponderSummary, ResponderRecommendation, RankedOutResponder,
    RecommendationResponse, ResponderType, CapabilityType, RouteSource,
    HazardType
)
from backend.database import get_db_connection, parse_json_safe
from backend.routing_service import get_route, RouteResult
from backend.config import get_settings


CAPABILITY_REQUIREMENTS = {
    "unconscious": {"ambulance": ["ALS"]},
    "fuel_leak": {"fire": ["hazmat"]},
    "gas_leak": {"fire": ["hazmat"]},
    "fire": {"fire": ["water_tender", "hazmat"]},
    "electrical_hazard": {"fire": ["hazmat"]},
    "smoke": {"fire": ["water_tender"]},
}


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    a = math.sin(delta_phi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


def get_required_units_and_capabilities(facts) -> Tuple[List[Dict[str, Any]], List[str]]:
    required = []
    
    if facts.type == "road_accident":
        required.append({"unit_type": "ambulance", "capabilities": []})
        required.append({"unit_type": "police", "capabilities": ["traffic_control"]})
        if any(h in facts.hazards for h in ["fuel_leak", "fire", "smoke", "electrical_hazard", "gas_leak"]):
            required.append({"unit_type": "fire", "capabilities": ["hazmat"] if "fuel_leak" in facts.hazards or "gas_leak" in facts.hazards else ["water_tender"]})
    
    elif facts.type == "fire":
        required.append({"unit_type": "fire", "capabilities": ["water_tender"]})
        if facts.injured_count and facts.injured_count > 0:
            required.append({"unit_type": "ambulance", "capabilities": ["BLS"]})
        if facts.unconscious:
            for r in required:
                if r["unit_type"] == "ambulance":
                    r["capabilities"] = ["ALS"]
                    break
            else:
                required.append({"unit_type": "ambulance", "capabilities": ["ALS"]})
    
    elif facts.type == "medical_emergency":
        caps = ["ALS"] if facts.unconscious else ["BLS"]
        required.append({"unit_type": "ambulance", "capabilities": caps})
    
    for unit_type in facts.required_units:
        if not any(r["unit_type"] == unit_type for r in required):
            required.append({"unit_type": unit_type, "capabilities": []})
    
    return required, []


def has_required_capabilities(responder_caps: List[str], required_caps: List[str]) -> bool:
    return all(cap in responder_caps for cap in required_caps)


def get_recommendations(
    incident_id: str,
    incident_lat: float,
    incident_lng: float,
    facts,
    fault_routing_down: bool = False
) -> RecommendationResponse:
    settings = get_settings()
    required, uncovered = get_required_units_and_capabilities(facts)
    
    with get_db_connection() as conn:
        responders = conn.execute(
            "SELECT * FROM responders WHERE status = 'available'"
        ).fetchall()
    
    responder_objects = []
    for r in responders:
        caps = parse_json_safe(r["capabilities_json"], [])
        responder_objects.append(ResponderSummary(
            id=r["id"],
            unit_type=r["unit_type"],
            latitude=r["latitude"],
            longitude=r["longitude"],
            status=r["status"],
            capabilities=caps,
            updated_at=r["updated_at"]
        ))
    
    recommendations = []
    ranked_out = []
    
    for req in required:
        unit_type = req["unit_type"]
        required_caps = req["capabilities"]
        
        candidates = [r for r in responder_objects if r.unit_type == unit_type]
        
        eligible = []
        for cand in candidates:
            if has_required_capabilities(cand.capabilities, required_caps):
                eligible.append(cand)
            else:
                missing = [c for c in required_caps if c not in cand.capabilities]
                ranked_out.append(RankedOutResponder(
                    responder_id=cand.id,
                    reason_code="MISSING_CAPABILITY",
                    detail=f"Lacks required capability: {', '.join(missing)}"
                ))
        
        with get_db_connection() as conn:
            all_type = conn.execute(
                "SELECT * FROM responders WHERE unit_type = ?", (unit_type,)
            ).fetchall()
        
        for r in all_type:
            caps = parse_json_safe(r["capabilities_json"], [])
            if r["status"] == "busy":
                ranked_out.append(RankedOutResponder(
                    responder_id=r["id"],
                    reason_code="BUSY",
                    detail="Assigned to another incident"
                ))
            elif r["status"] == "offline":
                ranked_out.append(RankedOutResponder(
                    responder_id=r["id"],
                    reason_code="OFFLINE",
                    detail="Unit is offline"
                ))
        
        if not eligible:
            continue
        
        for cand in eligible:
            cand.distance_straight = haversine_distance(
                incident_lat, incident_lng, cand.latitude, cand.longitude
            )
        eligible.sort(key=lambda x: x.distance_straight)
        shortlisted = eligible[:4]
        
        routed = []
        for cand in shortlisted:
            if fault_routing_down:
                route_result = RouteResult(
                    duration_seconds=None,
                    distance_meters=None,
                    geometry=None,
                    source="unavailable"
                )
            else:
                route_result = get_route(
                    incident_lng, incident_lat,
                    cand.longitude, cand.latitude,
                    use_cache=True
                )
            
            if route_result.duration_seconds is not None:
                cand.eta_seconds = route_result.duration_seconds
                cand.distance_m = route_result.distance_meters
                cand.route_source = route_result.source
                cand.route_geometry = route_result.geometry
            else:
                cand.eta_seconds = None
                cand.distance_m = int(cand.distance_straight)
                cand.route_source = "approximate_straight_line"
                cand.route_geometry = None
            
            routed.append(cand)
        
        routed.sort(key=lambda x: (
            x.route_source == "approximate_straight_line",
            x.eta_seconds or float('inf')
        ))
        
        for i, cand in enumerate(routed):
            why = ["Available"]
            if has_required_capabilities(cand.capabilities, required_caps):
                why.append(f"Has required capabilities: {', '.join(required_caps) if required_caps else 'none'}")
            if cand.route_source != "approximate_straight_line":
                why.append(f"Fastest valid road ETA of {len(routed)} eligible units")
            else:
                why.append(f"Closest by straight-line distance (routing unavailable)")
            
            recommendations.append(ResponderRecommendation(
                responder_id=cand.id,
                unit_type=cand.unit_type,
                status=cand.status,
                matched_capabilities=[c for c in cand.capabilities if c in required_caps],
                eta_seconds=cand.eta_seconds,
                distance_m=cand.distance_m,
                route_source=cand.route_source,
                route_geometry=cand.route_geometry,
                why=why,
                recommended_at=__import__('datetime').datetime.utcnow().isoformat() + "Z",
                stale_after_seconds=60
            ))
        
        for cand in routed[1:]:
            if cand.route_source != "approximate_straight_line":
                diff = cand.eta_seconds - routed[0].eta_seconds if routed[0].eta_seconds else 0
                ranked_out.append(RankedOutResponder(
                    responder_id=cand.id,
                    reason_code="AVAILABLE_NOT_CHOSEN",
                    detail=f"Slower by {diff//60}m {diff%60}s"
                ))
            else:
                ranked_out.append(RankedOutResponder(
                    responder_id=cand.id,
                    reason_code="AVAILABLE_NOT_CHOSEN",
                    detail="Further by straight-line distance"
                ))
        
        for cand in eligible[4:]:
            ranked_out.append(RankedOutResponder(
                responder_id=cand.id,
                reason_code="NOT_SHORTLISTED",
                detail=f"Farther than nearest 4 (straight-line: {int(cand.distance_straight)}m)"
            ))
    
    type_order = {"ambulance": 0, "fire": 1, "police": 2}
    recommendations.sort(key=lambda x: type_order.get(x.unit_type, 99))
    
    return RecommendationResponse(
        incident_id=incident_id,
        recommended_at=__import__('datetime').datetime.utcnow().isoformat() + "Z",
        stale_after_seconds=60,
        required=required,
        recommendations=recommendations,
        ranked_out=ranked_out,
        uncovered_requirements=uncovered
    )