"""Pydantic schemas for API validation and serialization."""
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator
import json


# Enums
IncidentType = Literal["road_accident", "fire", "medical_emergency", "other"]
IncidentStatus = Literal["pending", "under_review", "dispatched", "resolved", "cancelled"]
ResponderType = Literal["ambulance", "fire", "police"]
ResponderStatus = Literal["available", "busy", "offline"]
DispatchStatus = Literal["active", "completed", "cancelled"]
ExtractionSource = Literal["llm", "keyword_fallback"]
RouteSource = Literal["osrm_live", "osrm_cached", "approximate_straight_line", "unavailable"]
PriorityLevel = Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]
ActorLabel = Literal["CITIZEN-DEMO", "DISPATCHER-DEMO", "SYSTEM-DEMO", "AI-DEMO"]


# Hazard and Capability types
HazardType = Literal["fuel_leak", "smoke", "fire", "electrical_hazard", "gas_leak", "unknown"]
CapabilityType = Literal["BLS", "ALS", "water_tender", "rescue", "hazmat", "traffic_control", "trauma_care"]


# Extraction schemas
class EvidenceSpan(BaseModel):
    """Evidence span linking a fact to the original report text."""
    quote: str = Field(..., min_length=1, max_length=500)
    start: int = Field(..., ge=0)
    end: int = Field(..., ge=0)


class ExtractedFacts(BaseModel):
    """Structured facts extracted from the incident report."""
    type: Optional[IncidentType] = None
    injured_count: Optional[int] = Field(None, ge=0)
    unconscious: Optional[bool] = None
    hazards: List[HazardType] = Field(default_factory=list)
    required_units: List[ResponderType] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """Complete extraction result with evidence and provenance."""
    facts: ExtractedFacts
    evidence: Dict[str, EvidenceSpan] = Field(default_factory=dict)
    uncertainty_flags: List[str] = Field(default_factory=list)
    source: ExtractionSource


# Priority Engine schemas
class ScoreFactor(BaseModel):
    """Individual factor in the priority score breakdown."""
    factor: str
    points: int
    evidence_quote: Optional[str] = None
    status: Literal["counted", "unknown", "not_applicable"]
    origin: Literal["rules", "dispatcher"]


class PriorityBreakdown(BaseModel):
    """Complete priority score breakdown with floor/ceiling."""
    score: int = Field(..., ge=0, le=100)
    ceiling: int = Field(..., ge=0, le=100)
    level: PriorityLevel
    ceiling_level: PriorityLevel
    breakdown: List[ScoreFactor]
    explanation: str
    needs_review: bool
    assumptions: List[str] = Field(default_factory=list)


# Responder Matching schemas
class ResponderRecommendation(BaseModel):
    """A recommended responder with reasoning."""
    responder_id: str
    unit_type: ResponderType
    status: ResponderStatus
    matched_capabilities: List[CapabilityType]
    eta_seconds: Optional[int] = None
    distance_m: Optional[int] = None
    route_source: RouteSource
    route_geometry: Optional[Dict[str, Any]] = None
    why: List[str]
    recommended_at: str
    stale_after_seconds: int = 60


class RankedOutResponder(BaseModel):
    """A responder that was considered but not recommended."""
    responder_id: str
    reason_code: Literal[
        "SELECTED", "AVAILABLE_NOT_CHOSEN", "BUSY", "OFFLINE",
        "MISSING_CAPABILITY", "NOT_SHORTLISTED", "ROUTE_UNAVAILABLE"
    ]
    detail: str


class RecommendationResponse(BaseModel):
    """Full recommendation response with ranked-out ledger."""
    incident_id: str
    recommended_at: str
    stale_after_seconds: int
    required: List[Dict[str, Any]]
    recommendations: List[ResponderRecommendation]
    ranked_out: List[RankedOutResponder]
    uncovered_requirements: List[str]


# Incident schemas
class IncidentCreate(BaseModel):
    """Request to create a new incident."""
    type: IncidentType
    description: str = Field(..., min_length=10, max_length=2000)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        if "<script" in v.lower():
            raise ValueError("Description contains invalid content")
        return v.strip()


class IncidentSummary(BaseModel):
    """Summary view for queue listing."""
    id: str
    type: IncidentType
    description: str
    latitude: float
    longitude: float
    created_at: str
    status: IncidentStatus
    priority_score: int
    priority_ceiling: int
    priority_level: PriorityLevel
    ceiling_level: PriorityLevel
    needs_review: bool
    age_seconds: int


class IncidentDetail(BaseModel):
    """Full incident detail for dispatcher review."""
    id: str
    type: IncidentType
    description: str
    latitude: float
    longitude: float
    created_at: str
    status: IncidentStatus
    extracted_facts: ExtractedFacts
    evidence: Dict[str, EvidenceSpan]
    extraction_source: ExtractionSource
    uncertainty_flags: List[str]
    priority_score: int
    priority_ceiling: int
    priority_level: PriorityLevel
    ceiling_level: PriorityLevel
    score_breakdown: List[ScoreFactor]
    priority_explanation: str
    needs_review: bool
    last_analyzed_at: Optional[str] = None
    analysis_status: str
    events: List[Dict[str, Any]] = Field(default_factory=list)


# Responder schemas
class ResponderCreate(BaseModel):
    """Request to create a responder (seed data)."""
    id: str
    unit_type: ResponderType
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    status: ResponderStatus = "available"
    capabilities: List[CapabilityType] = Field(default_factory=list)


class ResponderSummary(BaseModel):
    """Responder summary for listing."""
    id: str
    unit_type: ResponderType
    latitude: float
    longitude: float
    status: ResponderStatus
    capabilities: List[CapabilityType]
    updated_at: str
    distance_straight: Optional[float] = None
    eta_seconds: Optional[float] = None
    distance_m: Optional[int] = None
    route_source: Optional[str] = None
    route_geometry: Optional[str] = None

    class Config:
        extra = "allow"


# Dispatch schemas
class DispatchCreate(BaseModel):
    """Request to create a dispatch assignment."""
    incident_id: str
    responder_ids: List[str]
    dispatcher_id: str = "DISPATCHER-DEMO"


class DispatchResponse(BaseModel):
    """Response after dispatch creation."""
    id: str
    incident_id: str
    responder_id: str
    status: DispatchStatus
    approved_at: str
    eta_seconds: Optional[int] = None
    route_source: RouteSource


class DispatchConflictResponse(BaseModel):
    """Structured 409 conflict response."""
    error: Literal["responder_unavailable"]
    responder_id: str
    taken_by: str
    taken_at: str
    next_best: List[ResponderRecommendation] = Field(default_factory=list)


# Demo/Control schemas
class FaultFlags(BaseModel):
    """Active fault injection flags."""
    llm_down: bool = False
    llm_malformed: bool = False
    routing_down: bool = False
    routing_slow: bool = False


class ScenarioPlayRequest(BaseModel):
    """Request to play a scenario."""
    scenario_id: str


class ConcurrencyTestResult(BaseModel):
    """Result of concurrency test."""
    attempts: int
    successes: int
    conflicts: int
    final_active_count: int
    details: List[Dict[str, Any]]


# Health and Summary
class HealthResponse(BaseModel):
    """Health check response."""
    status: Literal["ok"]
    version: str
    demo_mode: bool


class SummaryResponse(BaseModel):
    """Dashboard summary counts."""
    open_incidents: int
    available_responders: int
    active_dispatches: int
    last_updated: str


# Evaluation
class EvaluationMetrics(BaseModel):
    """Benchmark evaluation metrics."""
    timestamp: str
    git_commit: Optional[str] = None
    llm_mode: str
    scenario_count: int
    repetitions: int
    submission_to_recommendation_ms: Dict[str, float]
    eligible_units_accuracy_pct: float
    extraction_schema_failure_rate: float
    extraction_fallback_rate: float
    evidence_demotion_count: int
    concurrency_attempts: int
    concurrency_rejected: int
    routing_live_count: int
    routing_cached_count: int
    routing_approximate_count: int
    routing_unavailable_count: int


# Utility functions
def generate_id(prefix: str) -> str:
    """Generate a prefixed ID with timestamp."""
    import time
    return f"{prefix}-{int(time.time() * 1000)}"


def now_iso() -> str:
    """Current UTC time in ISO format."""
    return datetime.utcnow().isoformat() + "Z"


def parse_json_safe(text: Optional[str], default: Any = None) -> Any:
    """Safely parse JSON, returning default on failure."""
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default