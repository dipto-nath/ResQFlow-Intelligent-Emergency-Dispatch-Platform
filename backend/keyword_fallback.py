"""Deterministic keyword-based extraction fallback with negation handling and evidence spans."""
import re
from typing import List, Dict, Optional, Tuple
from difflib import get_close_matches
from backend.schemas import (
    ExtractedFacts, EvidenceSpan, ExtractionResult, ExtractionSource,
    HazardType, ResponderType, CapabilityType
)


# Keyword patterns for each field
INJURED_PATTERNS = [
    (r'(\d+)\s*(?:people|peple|person|victim|victims|injured|hurt|casualties?)', 1),
    (r'(one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:people|peple|person|victim|victims|injured|hurt|casualties?)', 1),
    (r'(\d+)\s+injured', 1),
    (r'(one|two|three|four|five|six|seven|eight|nine|ten)\s+injured', 1),
    (r'(\d+)\s+peple\s+coughing', 1),
    (r'one\s+person\s+is\s+unconscious', 1),
]

INJURED_NEGATION_PATTERNS = [
    r'no\s+one\s+(?:is\s+)?(?:hurt|injured)',
    r'no\s+(?:injuries|casualties|victims)',
    r'nobody\s+(?:is\s+)?(?:hurt|injured)',
]

UNCONSCIOUS_POSITIVE = [
    r'unconscious',
    r'not\s+responding',
    r'not\s+conscious',
    r'passed\s+out',
    r'knocked\s+out',
    r'out\s+cold',
    r'not\s+moving',
]

UNCONSCIOUS_NEGATIVE = [
    r'conscious',
    r'awake',
    r'responding',
    r'alert',
]

HAZARD_PATTERNS: Dict[HazardType, List[str]] = {
    "fuel_leak": [
        r'fuel\s+leak',
        r'petrol\s+leak',
        r'gasoline\s+leak',
        r'leaking\s+fuel',
        r'leaking\s+petrol',
        r'petrol\s+leaking',
        r'fuel\s+spill',
        r'petrol\s+spill',
        r'petrol\s+on\s+(?:the\s+)?road',
    ],
    "smoke": [
        r'smoke',
        r'smoky',
    ],
    "fire": [
        r'\bfire\b',
        r'flames?',
        r'burning',
    ],
    "electrical_hazard": [
        r'electrical\s+(?:hazard|short|fire)',
        r'power\s+line',
        r'live\s+wire',
        r'electrocution',
    ],
    "gas_leak": [
        r'gas\s+leak',
        r'leaking\s+gas',
        r'smell\s+of\s+gas',
        r'gas\s+smell',
    ],
}

REQUIRED_UNIT_PATTERNS: Dict[ResponderType, List[str]] = {
    "ambulance": [
        r'ambulance',
        r'medic',
        r'ems',
        r'paramedic',
    ],
    "fire": [
        r'fire\s+(?:engine|truck|brigade|department)',
        r'firefighter',
    ],
    "police": [
        r'police',
        r'cop',
        r'law\s+enforcement',
    ],
}

TYPE_KEYWORDS = {
    "road_accident": [r'\baccident\b', r'\bcollision\b', r'\bcrash\b', r'\brider\b', r'\bbike\b', r'\bvehicle\b', r'\bcar\b'],
    "fire": [r'\bfire\b', r'\bflames?\b', r'\bburning\b', r'\bblaze\b'],
    "medical_emergency": [r'\bcollapsed\b', r'\bmedical\b', r'\bheart\b', r'\bfainted\b', r'\bseizure\b'],
    "other": [r'\bincident\b', r'\bemergency\b', r'\bhappened\b'],
}

NUMBER_WORDS = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
}


def extract_facts_keyword(text: str, incident_type: Optional[str] = None) -> ExtractionResult:
    """Extract facts using deterministic keyword and regex matching."""
    lower_text = text.lower()
    evidence: Dict[str, EvidenceSpan] = {}
    uncertainty_flags: List[str] = []

    # 1. Type extraction
    extracted_type = None
    target_type = incident_type or "other"
    keywords = TYPE_KEYWORDS.get(target_type, [])
    for kw in keywords:
        match = re.search(kw, text, re.IGNORECASE)
        if match:
            extracted_type = target_type
            evidence["type"] = EvidenceSpan(
                quote=match.group(0),
                start=match.start(),
                end=match.end()
            )
            break
    
    if not extracted_type:
        # Fallback to incident_type if present in text or if specified
        match = re.search(re.escape(target_type.replace('_', ' ')), text, re.IGNORECASE)
        if match:
            extracted_type = target_type
            evidence["type"] = EvidenceSpan(
                quote=match.group(0),
                start=match.start(),
                end=match.end()
            )
        elif incident_type:
            extracted_type = incident_type

    # 2. Injured count extraction
    injured_count = None
    # Check negation first
    for pattern in INJURED_NEGATION_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            injured_count = 0
            evidence["injured_count"] = EvidenceSpan(
                quote=match.group(0),
                start=match.start(),
                end=match.end()
            )
            break

    if injured_count is None:
        for pattern, group_idx in INJURED_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                raw_val = match.group(group_idx).lower()
                if raw_val in NUMBER_WORDS:
                    injured_count = NUMBER_WORDS[raw_val]
                elif raw_val.isdigit():
                    injured_count = int(raw_val)
                elif "one" in match.group(0).lower():
                    injured_count = 1
                
                if injured_count is not None:
                    evidence["injured_count"] = EvidenceSpan(
                        quote=match.group(0),
                        start=match.start(),
                        end=match.end()
                    )
                    break

    # 3. Consciousness extraction
    pos_match = None
    for pattern in UNCONSCIOUS_POSITIVE:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            pos_match = m
            break

    neg_match = None
    for pattern in UNCONSCIOUS_NEGATIVE:
        # Avoid matching 'conscious' inside 'unconscious'
        m = re.search(r'(?<!un)' + pattern, text, re.IGNORECASE)
        if m:
            neg_match = m
            break

    unconscious = None
    if pos_match and neg_match:
        # Conflicting statement
        unconscious = None
        uncertainty_flags.append("conflicting_consciousness")
    elif pos_match:
        unconscious = True
        evidence["unconscious"] = EvidenceSpan(
            quote=pos_match.group(0),
            start=pos_match.start(),
            end=pos_match.end()
        )
    elif neg_match:
        unconscious = False
        evidence["unconscious"] = EvidenceSpan(
            quote=neg_match.group(0),
            start=neg_match.start(),
            end=neg_match.end()
        )

    # 4. Hazard extraction
    hazards: List[HazardType] = []
    first_hazard_span = None
    for hazard, patterns in HAZARD_PATTERNS.items():
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                if hazard not in hazards:
                    hazards.append(hazard)
                if not first_hazard_span:
                    first_hazard_span = EvidenceSpan(
                        quote=m.group(0),
                        start=m.start(),
                        end=m.end()
                    )
                break
    if first_hazard_span:
        evidence["hazards"] = first_hazard_span

    # 5. Required units extraction
    required_units: List[ResponderType] = []
    first_unit_span = None
    for unit, patterns in REQUIRED_UNIT_PATTERNS.items():
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                if unit not in required_units:
                    required_units.append(unit)
                if not first_unit_span:
                    first_unit_span = EvidenceSpan(
                        quote=m.group(0),
                        start=m.start(),
                        end=m.end()
                    )
                break
    if first_unit_span:
        evidence["required_units"] = first_unit_span

    facts = ExtractedFacts(
        type=extracted_type,
        injured_count=injured_count,
        unconscious=unconscious,
        hazards=hazards,
        required_units=required_units
    )

    return ExtractionResult(
        facts=facts,
        evidence=evidence,
        uncertainty_flags=uncertainty_flags,
        source="keyword_fallback"
    )