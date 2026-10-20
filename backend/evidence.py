"""Evidence verification - the key differentiator ensuring hallucination is visibly impossible."""
import re
from typing import Optional, List, Dict, Any
from backend.schemas import ExtractedFacts, EvidenceSpan, ExtractionResult, HazardType


def normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, collapse whitespace."""
    return re.sub(r'\s+', ' ', text.lower().strip())


def find_quote_span(original_text: str, quote: str) -> Optional[tuple[int, int]]:
    """
    Find the actual span of a quote in the original text.
    Returns (start, end) character positions or None if not found.
    """
    if not quote or not quote.strip():
        return None
        
    # 1. Exact case-insensitive match
    low_orig = original_text.lower()
    low_quote = quote.lower().strip()
    idx = low_orig.find(low_quote)
    if idx >= 0:
        return (idx, idx + len(low_quote))
    
    # 2. Match with flexible whitespace
    pattern = r'\s+'.join(re.escape(w) for w in quote.split())
    m = re.search(pattern, original_text, re.IGNORECASE)
    if m:
        return (m.start(), m.end())
        
    return None


def verify_evidence(original_text: str, extraction: ExtractionResult) -> ExtractionResult:
    """
    Verify all evidence quotes against the original text.
    Demotes unverifiable facts to null and adds uncertainty flags.
    """
    verified_facts = extraction.facts.model_copy()
    verified_evidence = {}
    uncertainty_flags = list(extraction.uncertainty_flags)
    
    # Check each fact that has evidence
    fact_fields = [
        ("type", "type"),
        ("injured_count", "injured_count"),
        ("unconscious", "unconscious"),
        ("hazards", "hazards"),
        ("required_units", "required_units"),
    ]
    
    for fact_key, evidence_key in fact_fields:
        fact_value = getattr(extraction.facts, fact_key)
        if fact_value is None or (isinstance(fact_value, list) and len(fact_value) == 0):
            continue
            
        evidence = extraction.evidence.get(evidence_key)
        if not evidence:
            # No evidence provided for a non-null fact
            setattr(verified_facts, fact_key, None if fact_key != "hazards" and fact_key != "required_units" else [])
            uncertainty_flags.append(f"evidence_not_found:{evidence_key}")
            continue
        
        # Verify the quote exists in original text
        span = find_quote_span(original_text, evidence.quote)
        if span is None:
            # Quote not found - demote fact
            setattr(verified_facts, fact_key, None if fact_key != "hazards" and fact_key != "required_units" else [])
            uncertainty_flags.append(f"evidence_not_found:{evidence_key}")
        else:
            # Quote verified - update with correct span
            verified_evidence[evidence_key] = EvidenceSpan(
                quote=evidence.quote,
                start=span[0],
                end=span[1]
            )
    
    return ExtractionResult(
        facts=verified_facts,
        evidence=verified_evidence,
        uncertainty_flags=uncertainty_flags,
        source=extraction.source
    )


def verify_and_merge_evidence(original_text: str, extraction: ExtractionResult) -> ExtractionResult:
    """
    Main entry point: verify evidence and return cleaned extraction.
    This is called after LLM or keyword fallback extraction.
    """
    return verify_evidence(original_text, extraction)