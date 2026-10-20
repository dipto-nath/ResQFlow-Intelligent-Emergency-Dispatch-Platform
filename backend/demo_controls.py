"""Demo controls - fault injection, scenario player, conflict lab."""
import json
import asyncio
import threading
import time
from typing import Dict, List, Any, Optional
from backend.config import get_settings
from backend.database import get_db_connection, get_db_transaction, reset_database, init_database, parse_json_safe, now_iso, generate_id
from backend.incident_service import create_incident, analyze_incident, add_fact_confirmation
from backend.schemas import IncidentCreate, FaultFlags, ConcurrencyTestResult
from backend.routing_service import save_route_cache


_fault_state = {
    "llm_down": False,
    "llm_malformed": False,
    "routing_down": False,
    "routing_slow": False
}


def get_fault_state() -> FaultFlags:
    return FaultFlags(**_fault_state)


def set_fault_state(flags: FaultFlags) -> FaultFlags:
    _fault_state["llm_down"] = flags.llm_down
    _fault_state["llm_malformed"] = flags.llm_malformed
    _fault_state["routing_down"] = flags.routing_down
    _fault_state["routing_slow"] = flags.routing_slow
    return get_fault_state()


SCENARIOS = {
    "S1": {
        "name": "Hero Flow - Unconscious + Fuel Leak",
        "type": "road_accident",
        "description": "A rider has fallen after a collision near the flyover. One person is unconscious and there is a fuel leak from the bike.",
        "latitude": 22.5726,
        "longitude": 88.3639,
        "expected_units": ["ambulance", "fire", "police"],
        "talking_point": "Clear multi-hazard incident requiring ambulance (ALS), fire (hazmat), and police"
    },
    "S2": {
        "name": "Vague Report - Needs Verification",
        "type": "other",
        "description": "Something happened near the crossing, people are shouting, come quickly.",
        "latitude": 22.5800,
        "longitude": 88.3700,
        "expected_units": [],
        "talking_point": "Vague report with wide floor/ceiling gap - demonstrates unknown handling"
    },
    "S3": {
        "name": "Misspelled Multi-Hazard",
        "type": "fire",
        "description": "kitchen fire at resturant, smoke everywhere, 2 peple coughing, smell of gas",
        "latitude": 22.5600,
        "longitude": 88.3500,
        "expected_units": ["fire", "ambulance"],
        "talking_point": "Misspellings handled by fuzzy matching - gas leak + smoke + injured"
    },
    "S4": {
        "name": "No Eligible Unit - All ALS Busy",
        "type": "medical_emergency",
        "description": "Elderly man collapsed at the bus stand, not responding.",
        "latitude": 22.5900,
        "longitude": 88.3800,
        "expected_units": [],
        "talking_point": "No ALS ambulance available - demonstrates honest empty state"
    },
    "S5": {
        "name": "Higher Priority Competes for Same Unit",
        "type": "road_accident",
        "description": "Multi-vehicle collision, four injured, one unconscious, petrol leaking across the road.",
        "latitude": 22.5750,
        "longitude": 88.3650,
        "expected_units": ["ambulance", "fire", "police"],
        "talking_point": "Higher priority incident competes for S1's ambulance - forces 409 conflict"
    },
    "S6": {
        "name": "Duplicate-Looking Report",
        "type": "road_accident",
        "description": "Bike accident by the flyover, man not moving, petrol on road.",
        "latitude": 22.5730,
        "longitude": 88.3640,
        "expected_units": ["ambulance", "fire", "police"],
        "talking_point": "Near-duplicate of S1 - flagged but both retained"
    },
    "S7": {
        "name": "Conflicting Statements",
        "type": "medical_emergency",
        "description": "He is conscious but not responding to us.",
        "latitude": 22.5650,
        "longitude": 88.3550,
        "expected_units": ["ambulance"],
        "talking_point": "Conflicting evidence on consciousness - flagged, stays unknown"
    },
    "S8": {
        "name": "Explicit Negation",
        "type": "fire",
        "description": "Small electrical short in a shop, smoke, no one is hurt.",
        "latitude": 22.5850,
        "longitude": 88.3750,
        "expected_units": ["fire"],
        "talking_point": "Explicit 'no one hurt' - injured_count=0 with evidence"
    }
}


async def play_scenario(scenario_id: str, fault_llm_down: bool = False, fault_llm_malformed: bool = False) -> Dict[str, Any]:
    if scenario_id not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario_id}")
    
    scenario = SCENARIOS[scenario_id]
    
    incident = IncidentCreate(
        type=scenario["type"],
        description=scenario["description"],
        latitude=scenario["latitude"],
        longitude=scenario["longitude"]
    )
    
    result = await create_incident(incident)
    
    if fault_llm_down or fault_llm_malformed:
        await analyze_incident(result["id"], fault_llm_down=fault_llm_down, fault_llm_malformed=fault_llm_malformed)
    
    return {
        "scenario": scenario_id,
        "incident_id": result["id"],
        "talking_point": scenario["talking_point"]
    }


async def run_concurrency_test() -> ConcurrencyTestResult:
    reset_database()
    init_database()
    await seed_demo_data()
    
    incident = IncidentCreate(
        type="medical_emergency",
        description="Test patient unconscious, needs ALS ambulance.",
        latitude=22.5726,
        longitude=88.3639
    )
    result = await create_incident(incident)
    incident_id = result["id"]
    
    with get_db_connection() as conn:
        amb = conn.execute(
            "SELECT id FROM responders WHERE unit_type = 'ambulance' AND capabilities_json LIKE '%ALS%' AND status = 'available' LIMIT 1"
        ).fetchone()
    
    if not amb:
        return ConcurrencyTestResult(
            attempts=0, successes=0, conflicts=0,
            final_active_count=0, details=[]
        )
    
    responder_id = amb["id"]
    
    results = []
    
    def dispatch_attempt(attempt_num: int):
        try:
            from backend.dispatch_service import create_dispatch, DispatchConflict
            from backend.schemas import DispatchCreate
            
            dispatch = DispatchCreate(
                incident_id=incident_id,
                responder_ids=[responder_id]
            )
            result = create_dispatch(dispatch)
            results.append({"attempt": attempt_num, "success": True, "dispatch_id": result.id if hasattr(result, 'id') else str(result)})
        except DispatchConflict as e:
            results.append({"attempt": attempt_num, "success": False, "error": "conflict", "responder_id": e.responder_id})
        except Exception as e:
            results.append({"attempt": attempt_num, "success": False, "error": str(e)})
    
    threads = []
    for i in range(5):
        t = threading.Thread(target=dispatch_attempt, args=(i,))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    with get_db_connection() as conn:
        active = conn.execute(
            "SELECT COUNT(*) as cnt FROM dispatches WHERE responder_id = ? AND status = 'active'",
            (responder_id,)
        ).fetchone()
        final_count = active["cnt"] if active else 0
    
    successes = sum(1 for r in results if r.get("success"))
    conflicts = sum(1 for r in results if not r.get("success"))
    
    return ConcurrencyTestResult(
        attempts=len(results),
        successes=successes,
        conflicts=conflicts,
        final_active_count=final_count,
        details=results
    )


async def run_evaluation() -> Dict[str, Any]:
    import subprocess
    import os
    
    script_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "benchmark.py")
    
    try:
        result = subprocess.run(
            ["python3", script_path],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            eval_path = os.path.join(os.path.dirname(__file__), "..", "evaluation", "latest.json")
            if os.path.exists(eval_path):
                with open(eval_path) as f:
                    return json.load(f)
        return {"error": "Benchmark failed", "stderr": result.stderr}
    except Exception as e:
        return {"error": str(e)}


async def seed_demo_data() -> None:
    settings = get_settings()
    
    responders = [
        {"id": "AMB-01", "unit_type": "ambulance", "latitude": 22.5700, "longitude": 88.3600, "capabilities": ["BLS", "trauma_care"], "status": "available"},
        {"id": "AMB-02", "unit_type": "ambulance", "latitude": 22.5800, "longitude": 88.3700, "capabilities": ["ALS", "trauma_care"], "status": "available"},
        {"id": "AMB-03", "unit_type": "ambulance", "latitude": 22.5600, "longitude": 88.3500, "capabilities": ["ALS", "trauma_care"], "status": "available"},
        {"id": "AMB-04", "unit_type": "ambulance", "latitude": 22.5900, "longitude": 88.3800, "capabilities": ["BLS"], "status": "available"},
        {"id": "AMB-05", "unit_type": "ambulance", "latitude": 22.5650, "longitude": 88.3550, "capabilities": ["BLS"], "status": "available"},
        {"id": "AMB-06", "unit_type": "ambulance", "latitude": 22.5850, "longitude": 88.3750, "capabilities": ["ALS"], "status": "busy"},
        {"id": "AMB-07", "unit_type": "ambulance", "latitude": 22.5500, "longitude": 88.3400, "capabilities": ["BLS"], "status": "available"},
        
        {"id": "FIRE-01", "unit_type": "fire", "latitude": 22.5700, "longitude": 88.3600, "capabilities": ["water_tender", "hazmat"], "status": "available"},
        {"id": "FIRE-02", "unit_type": "fire", "latitude": 22.5800, "longitude": 88.3700, "capabilities": ["water_tender", "rescue"], "status": "available"},
        {"id": "FIRE-03", "unit_type": "fire", "latitude": 22.5600, "longitude": 88.3500, "capabilities": ["water_tender", "hazmat"], "status": "available"},
        {"id": "FIRE-04", "unit_type": "fire", "latitude": 22.5900, "longitude": 88.3800, "capabilities": ["rescue"], "status": "available"},
        {"id": "FIRE-05", "unit_type": "fire", "latitude": 22.5650, "longitude": 88.3550, "capabilities": ["water_tender"], "status": "offline"},
        {"id": "FIRE-06", "unit_type": "fire", "latitude": 22.5850, "longitude": 88.3750, "capabilities": ["water_tender", "rescue"], "status": "available"},
        
        {"id": "POL-01", "unit_type": "police", "latitude": 22.5700, "longitude": 88.3600, "capabilities": ["traffic_control"], "status": "available"},
        {"id": "POL-02", "unit_type": "police", "latitude": 22.5800, "longitude": 88.3700, "capabilities": ["traffic_control"], "status": "available"},
        {"id": "POL-03", "unit_type": "police", "latitude": 22.5600, "longitude": 88.3500, "capabilities": ["traffic_control"], "status": "available"},
        {"id": "POL-04", "unit_type": "police", "latitude": 22.5900, "longitude": 88.3800, "capabilities": ["traffic_control"], "status": "available"},
        {"id": "POL-05", "unit_type": "police", "latitude": 22.5650, "longitude": 88.3550, "capabilities": ["traffic_control"], "status": "available"},
    ]
    
    with get_db_transaction() as conn:
        for r in responders:
            conn.execute(
                """INSERT OR REPLACE INTO responders
                   (id, unit_type, latitude, longitude, status, capabilities_json, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (r["id"], r["unit_type"], r["latitude"], r["longitude"],
                 r["status"], json.dumps(r["capabilities"]), now_iso())
            )
        
        import datetime
        demo_routes = [
            {"origin": (88.3639, 22.5726), "dest": (88.3500, 22.5600), "duration": 240, "distance": 1900},
            {"origin": (88.3639, 22.5726), "dest": (88.3700, 22.5800), "duration": 300, "distance": 2400},
            {"origin": (88.3639, 22.5726), "dest": (88.3600, 22.5700), "duration": 180, "distance": 1400},
        ]
        
        for route in demo_routes:
            key = f"{route['origin'][0]:.6f},{route['origin'][1]:.6f}->{route['dest'][0]:.6f},{route['dest'][1]:.6f}"
            conn.execute(
                """INSERT OR REPLACE INTO route_cache
                   (id, origin_lat, origin_lng, dest_lat, dest_lng, route_json, source, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'osrm_cached', ?, ?)""",
                (key, route['origin'][1], route['origin'][0], route['dest'][1], route['dest'][0],
                 json.dumps({"duration_seconds": route["duration"], "distance_meters": route["distance"], "geometry": None}),
                 datetime.datetime.utcnow().isoformat(),
                 (datetime.datetime.utcnow() + datetime.timedelta(days=30)).isoformat())
            )
        
        conn.commit()
    
    save_route_cache()


def reset_demo() -> Dict[str, Any]:
    reset_database()
    init_database()
    import asyncio
    asyncio.run(seed_demo_data())
    return {"status": "reset complete"}