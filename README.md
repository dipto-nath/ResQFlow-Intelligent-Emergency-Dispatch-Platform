# Sahayak Dispatch — Intelligent Emergency Dispatch Platform

> **A decision-support prototype that shows its work.** Every extracted fact cites evidence. Every score shows what could change it. Every recommendation explains why other units weren't chosen. A human always decides.

[![Demo](https://img.shields.io/badge/Status-Demo_Prototype-orange)]()
[![Python](https://img.shields.io/badge/Python-3.11+-blue)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green)]()
[![React](https://img.shields.io/badge/React-18+-blue)]()
[![License](https://img.shields.io/badge/License-MIT-green)]()

---

## 🎯 Mission

Build a **demonstration prototype** of an intelligent emergency dispatch decision-support system that wins on **trust, craft, and proof** — not flashy UI or invented metrics.

### The Core Loop (End-to-End)

1. **Citizen submits** a simulated incident (type, free-text description, map location)
2. **Backend saves** the original report unchanged
3. **AI extracts** structured facts — each backed by a verifiable quote from the report
4. **Deterministic engine** computes a priority score with floor/ceiling, breakdown, and sensitivity
5. **Matcher** filters responders by availability + capability, ranks by road ETA, builds "Why Not" ledger
6. **Dispatcher reviews** evidence, unknowns, score, candidates — optionally records clarifications
7. **Human approves** — backend revalidates atomically, creates assignment, marks units busy
8. **Dashboard updates** live (3–5s polling) — queue reorders, units flip status
9. **Second incident arrives** — higher priority reorders queue, busy unit cannot be double-assigned
10. **System stays useful** when LLM or routing is down — honest fallbacks with visible labels

---

## 🏆 Six Signature Features (What Makes This Different)

| # | Feature | One-Line Pitch |
|---|---------|----------------|
| **S1** | **Evidence-Grounded Extraction** | Every fact cites an exact quote. Server verifies quote exists. If not, fact → `unknown`. AI cannot invent. |
| **S2** | **Unknown Stays Unknown** | Missing facts shown as first-class "Unknown" with follow-up questions. Dispatcher answers → score updates live with visible delta. |
| **S3** | **Score Sensitivity** | "Could reach 95 if unconscious confirmed (+40)". Missing data never silently lowers urgency. |
| **S4** | **Why Not the Others** | Candidate cards explain eligibility. "Ranked Out" list explains every exclusion: BUSY, MISSING_CAPABILITY, SLOWER_ROUTE, OFFLINE. |
| **S5** | **Provenance Everywhere** | Every datum wears a chip: `LLM`, `RULES`, `DISPATCHER`, `UNKNOWN`. Every route wears its source. |
| **S6** | **Self-Verifying Demo Tools** | One-click fault injection (LLM down, routing down), concurrency proof (1×201, 4×409), measured benchmark on synthetic scenarios. |

---

## ⚠️ Safety & Honesty Boundaries (Non-Negotiable)

- **Synthetic data only** — Never contacts real emergency services, never integrates with India's **112**
- **Persistent badges** — `DEMO / SIMULATED` in top bar + "DEMO — SIMULATED DATA ONLY. Not connected to emergency services. In a real emergency in India, call 112." on every screen
- **No PII** — No names, phone numbers, medical IDs, real addresses
- **AI extracts only** — Deterministic rules score. Human approves. AI never decides.
- **Prototype heuristic** — Not clinically validated. Label: *"Prototype priority score — not clinically validated; dispatcher review required."*
- **No invented routes** — Never draw straight line as road route. Never call straight-line distance an ETA.
- **Untrusted input** — Report text rendered as text (never HTML). Instructions inside reports ignored.
- **Secrets on backend** — No keys in frontend, Git history, logs, or screenshots.
- **Measured, not claimed** — Only metrics from `scripts/benchmark.py` shown, labelled "synthetic scenarios"