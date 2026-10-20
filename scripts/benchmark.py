"""Benchmark script for evaluation runs."""
import json
import os
import sys
import time
import statistics
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.database import reset_database, init_database, get_db_connection
from backend.demo_controls import seed_demo_data, SCENARIOS, run_concurrency_test
from backend.incident_service import create_incident, analyze_incident
from backend.schemas import IncidentCreate
from backend.responder_matcher import get_recommendations
import asyncio


async def run_benchmark():
    """Run full benchmark suite."""
    print("Starting benchmark...")
    
    # Reset and seed
    reset_database()
    init_database()
    await seed_demo_data()
    
    results = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "git_commit": "unknown",
        "llm_mode": "none",
        "scenario_count": len(SCENARIOS),
        "repetitions": 5,
        "submission_to_recommendation_ms": {},
        "eligible_units_accuracy_pct": 0.0,
        "extraction_schema_failure_rate": 0.0,
        "extraction_fallback_rate": 0.0,
        "evidence_demotion_count": 0,
        "concurrency_attempts": 0,
        "concurrency_rejected": 0,
        "routing_live_count": 0,
        "routing_cached_count": 0,
        "routing_approximate_count": 0,
        "routing_unavailable_count": 0
    }
    
    all_times = []
    correct_units = 0
    total_units = 0
    schema_failures = 0
    fallback_count = 0
    evidence_demotions = 0
    
    # Run each scenario multiple times
    for scenario_id, scenario in SCENARIOS.items():
        scenario_times = []
        
        for rep in range(results["repetitions"]):
            # Create incident
            incident = IncidentCreate(
                type=scenario["type"],
                description=scenario["description"],
                latitude=scenario["latitude"],
                longitude=scenario["longitude"]
            )
            
            start = time.perf_counter()
            create_result = await create_incident(incident)
            incident_id = create_result["id"]
            
            # Get recommendations
            with get_db_connection() as conn:
                row = conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
            
            if row:
                from backend.schemas import ExtractedFacts
                facts = ExtractedFacts(**json.loads(row["extracted_facts_json"])) if row["extracted_facts_json"] else ExtractedFacts()
                
                recommendations = get_recommendations(
                    incident_id,
                    scenario["latitude"],
                    scenario["longitude"],
                    facts
                )
                
                # Check eligible units accuracy
                expected = set(scenario["expected_units"])
                actual = set(r.unit_type for r in recommendations.recommendations)
                if expected == actual:
                    correct_units += 1
                total_units += 1
                
                # Count routing sources
                for rec in recommendations.recommendations:
                    if rec.route_source == "osrm_live":
                        results["routing_live_count"] += 1
                    elif rec.route_source == "osrm_cached":
                        results["routing_cached_count"] += 1
                    elif rec.route_source == "approximate_straight_line":
                        results["routing_approximate_count"] += 1
                    else:
                        results["routing_unavailable_count"] += 1
            
            elapsed = (time.perf_counter() - start) * 1000
            scenario_times.append(elapsed)
            all_times.append(elapsed)
        
        if scenario_times:
            results["submission_to_recommendation_ms"][scenario_id] = {
                "median": statistics.median(scenario_times),
                "p95": sorted(scenario_times)[int(len(scenario_times) * 0.95)]
            }
    
    # Overall timing stats
    if all_times:
        results["submission_to_recommendation_ms"]["overall"] = {
            "median": statistics.median(all_times),
            "p95": sorted(all_times)[int(len(all_times) * 0.95)]
        }
    
    # Accuracy
    if total_units > 0:
        results["eligible_units_accuracy_pct"] = (correct_units / total_units) * 100
    
    # Run concurrency test
    print("Running concurrency test...")
    concurrency_result = await run_concurrency_test()
    results["concurrency_attempts"] = concurrency_result.attempts
    results["concurrency_rejected"] = concurrency_result.conflicts
    
    # Save results
    eval_dir = os.path.join(os.path.dirname(__file__), "..", "evaluation")
    os.makedirs(eval_dir, exist_ok=True)
    
    eval_path = os.path.join(eval_dir, "latest.json")
    with open(eval_path, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"Benchmark complete. Results saved to {eval_path}")
    print(f"Overall median: {results['submission_to_recommendation_ms'].get('overall', {}).get('median', 0):.1f}ms")
    print(f"Accuracy: {results['eligible_units_accuracy_pct']:.1f}%")
    print(f"Concurrency: {results['concurrency_rejected']}/{results['concurrency_attempts']} rejected")
    
    return results


if __name__ == "__main__":
    asyncio.run(run_benchmark())