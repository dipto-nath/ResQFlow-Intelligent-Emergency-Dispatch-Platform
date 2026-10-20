"""Deterministic priority engine with floor/ceiling scoring and sensitivity analysis."""
from typing import List, Dict, Optional, Any
from backend.schemas import (
    ExtractedFacts, ScoreFactor, PriorityBreakdown, PriorityLevel,
    HazardType
)
from backend.database import parse_json_safe


# Priority weights (prototype-only, not clinically validated)
WEIGHTS = {
    "type_base": {
        "road_accident": 15,
        "fire": 20,
        "medical_emergency": 15,
        "other": 5,
    },
    "unconscious": 40,
    "fuel_leak": 25,
    "gas_leak": 25,
    "electrical_hazard": 15,
    "smoke": 10,
    "additional_victim": 10,
}

CEILING_POTENTIAL = {
    "unconscious": 40,
    "injured_count": 20,
    "hazards": 25,
}

BANDS = [
    (0, 29, "LOW"),
    (30, 54, "MODERATE"),
    (55, 79, "HIGH"),
    (80, 100, "CRITICAL"),
]


def get_band(score: int) -> PriorityLevel:
    for low, high, band in BANDS:
        if low <= score <= high:
            return band
    return "CRITICAL"


def compute_priority(
    facts: ExtractedFacts,
    confirmations: Optional[Dict[str, Any]] = None
) -> PriorityBreakdown:
    confirmations = confirmations or {}
    effective_facts = apply_confirmations(facts, confirmations)
    
    breakdown = []
    floor_score = 0
    
    type_score = WEIGHTS["type_base"].get(effective_facts.type, 0)
    floor_score += type_score
    breakdown.append(ScoreFactor(
        factor="type_base",
        points=type_score,
        evidence_quote=None,
        status="counted" if effective_facts.type else "unknown",
        origin="rules"
    ))
    
    unconscious_val = effective_facts.unconscious
    if unconscious_val is True:
        floor_score += WEIGHTS["unconscious"]
        breakdown.append(ScoreFactor(
            factor="unconscious",
            points=WEIGHTS["unconscious"],
            evidence_quote="confirmed by dispatcher" if confirmations.get("unconscious") else None,
            status="counted",
            origin="dispatcher" if confirmations.get("unconscious") else "rules"
        ))
    elif unconscious_val is None:
        breakdown.append(ScoreFactor(
            factor="unconscious",
            points=0,
            evidence_quote=None,
            status="unknown",
            origin="rules"
        ))
    
    hazard_points = 0
    for hazard in effective_facts.hazards:
        if hazard in WEIGHTS:
            hazard_points += WEIGHTS[hazard]
            breakdown.append(ScoreFactor(
                factor=hazard,
                points=WEIGHTS[hazard],
                evidence_quote=None,
                status="counted",
                origin="rules"
            ))
    floor_score += hazard_points
    
    injured = effective_facts.injured_count
    if injured is not None and injured > 1:
        additional = min(injured - 1, 4)
        victim_points = additional * WEIGHTS["additional_victim"]
        floor_score += victim_points
        breakdown.append(ScoreFactor(
            factor="additional_victims",
            points=victim_points,
            evidence_quote=f"{injured} injured reported",
            status="counted",
            origin="rules"
        ))
    elif injured is None:
        breakdown.append(ScoreFactor(
            factor="additional_victims",
            points=0,
            evidence_quote=None,
            status="unknown",
            origin="rules"
        ))
    
    floor_score = min(floor_score, 100)
    floor_level = get_band(floor_score)
    
    ceiling_score = floor_score
    if effective_facts.unconscious is None:
        ceiling_score += CEILING_POTENTIAL["unconscious"]
    if effective_facts.injured_count is None:
        ceiling_score += CEILING_POTENTIAL["injured_count"]
    if effective_facts.type in ("fire", "road_accident") and len(effective_facts.hazards) == 0:
        ceiling_score += CEILING_POTENTIAL["hazards"]
    
    ceiling_score = min(ceiling_score, 100)
    ceiling_level = get_band(ceiling_score)
    
    sensitivity = []
    if effective_facts.unconscious is None:
        sensitivity.append({
            "field": "unconscious",
            "status": "unresolved",
            "points_if_confirmed": CEILING_POTENTIAL["unconscious"]
        })
    if effective_facts.injured_count is None:
        sensitivity.append({
            "field": "injured_count",
            "status": "unknown",
            "points_if_confirmed": "+10 per additional victim (max +40)"
        })
    if effective_facts.type in ("fire", "road_accident") and len(effective_facts.hazards) == 0:
        sensitivity.append({
            "field": "hazards",
            "status": "unresolved",
            "points_if_confirmed": CEILING_POTENTIAL["hazards"]
        })
    
    needs_review = ceiling_level != floor_level or any(
        f.get("status") == "unknown" for f in sensitivity
    )
    
    explanation = generate_explanation(breakdown, floor_score, floor_level, ceiling_score, ceiling_level, sensitivity)
    
    return PriorityBreakdown(
        score=floor_score,
        ceiling=ceiling_score,
        level=floor_level,
        ceiling_level=ceiling_level,
        breakdown=breakdown,
        explanation=explanation,
        needs_review=needs_review,
        assumptions=["Prototype-only weights; not clinically validated"]
    )


def apply_confirmations(facts: ExtractedFacts, confirmations: Dict[str, Any]) -> ExtractedFacts:
    effective = facts.model_copy()
    for field, value in confirmations.items():
        if hasattr(effective, field):
            setattr(effective, field, value)
    return effective


def generate_explanation(
    breakdown: List[ScoreFactor],
    floor_score: int,
    floor_level: PriorityLevel,
    ceiling_score: int,
    ceiling_level: PriorityLevel,
    sensitivity: List[Dict]
) -> str:
    parts = []
    counted_factors = [f for f in breakdown if f.status == "counted" and f.points > 0]
    if counted_factors:
        factor_names = [f.factor.replace("_", " ") for f in counted_factors]
        parts.append(f"Score {floor_score} ({floor_level}) from: {', '.join(factor_names)}.")
    
    unknown_factors = [f for f in breakdown if f.status == "unknown"]
    if unknown_factors:
        unknown_names = [f.factor.replace("_", " ") for f in unknown_factors]
        parts.append(f"Unknown factors: {', '.join(unknown_names)}.")
    
    if ceiling_score > floor_score:
        parts.append(f"Could reach {ceiling_score} ({ceiling_level}) if unknowns are confirmed.")
    
    return " ".join(parts) if parts else f"Score {floor_score} ({floor_level}). No significant factors identified."