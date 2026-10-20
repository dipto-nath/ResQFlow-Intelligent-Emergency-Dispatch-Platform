"""Database connection and session management."""
import sqlite3
import os
from contextlib import contextmanager
from typing import Generator
from backend.config import get_settings
from backend.schemas import generate_id, now_iso, parse_json_safe


def get_db_path() -> str:
    """Get the database path, creating directories if needed."""
    settings = get_settings()
    db_path = settings.database_path
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return db_path


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """Get a database connection with proper configuration."""
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    try:
        yield conn
    finally:
        conn.close()


def init_database() -> None:
    """Initialize the database schema."""
    settings = get_settings()
    os.makedirs(os.path.dirname(settings.database_path), exist_ok=True)

    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL CHECK (type IN ('road_accident', 'fire', 'medical_emergency', 'other')),
                description TEXT NOT NULL,
                latitude REAL NOT NULL CHECK (latitude >= -90 AND latitude <= 90),
                longitude REAL NOT NULL CHECK (longitude >= -180 AND longitude <= 180),
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'under_review', 'dispatched', 'resolved', 'cancelled')),
                extracted_facts_json TEXT,
                evidence_json TEXT,
                extraction_source TEXT CHECK (extraction_source IN ('llm', 'keyword_fallback')),
                uncertainty_flags_json TEXT,
                priority_score INTEGER DEFAULT 0 CHECK (priority_score >= 0 AND priority_score <= 100),
                priority_ceiling INTEGER DEFAULT 0 CHECK (priority_ceiling >= 0 AND priority_ceiling <= 100),
                priority_level TEXT CHECK (priority_level IN ('LOW', 'MODERATE', 'HIGH', 'CRITICAL')),
                ceiling_level TEXT CHECK (ceiling_level IN ('LOW', 'MODERATE', 'HIGH', 'CRITICAL')),
                score_breakdown_json TEXT,
                priority_explanation TEXT,
                needs_review BOOLEAN DEFAULT FALSE,
                last_analyzed_at TEXT,
                analysis_status TEXT DEFAULT 'pending' CHECK (analysis_status IN ('pending', 'completed', 'failed'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS responders (
                id TEXT PRIMARY KEY,
                unit_type TEXT NOT NULL CHECK (unit_type IN ('ambulance', 'fire', 'police')),
                latitude REAL NOT NULL CHECK (latitude >= -90 AND latitude <= 90),
                longitude REAL NOT NULL CHECK (longitude >= -180 AND longitude <= 180),
                status TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'busy', 'offline')),
                capabilities_json TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL
            )
        """)

        # Dispatches table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dispatches (
                id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL REFERENCES incidents(id),
                responder_id TEXT NOT NULL REFERENCES responders(id),
                status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'cancelled')),
                approved_at TEXT NOT NULL,
                completed_at TEXT,
                cancelled_at TEXT,
                eta_seconds INTEGER,
                route_source TEXT CHECK (route_source IN ('osrm_live', 'osrm_cached', 'approximate_straight_line', 'unavailable')),
                route_geometry_json TEXT,
                UNIQUE (incident_id, responder_id)
            )
        """)

        # Partial unique index: one active dispatch per responder
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_dispatches_one_active_per_responder
            ON dispatches(responder_id)
            WHERE status = 'active'
        """)

        # Fact confirmations (dispatcher clarifications)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fact_confirmations (
                id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL REFERENCES incidents(id),
                field TEXT NOT NULL,
                value_json TEXT NOT NULL,
                actor_label TEXT NOT NULL DEFAULT 'DISPATCHER-DEMO',
                created_at TEXT NOT NULL,
                UNIQUE (incident_id, field)
            )
        """)

        # Incident events (audit log)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS incident_events (
                id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL REFERENCES incidents(id),
                event_type TEXT NOT NULL,
                old_value_json TEXT,
                new_value_json TEXT,
                created_at TEXT NOT NULL,
                actor_label TEXT NOT NULL CHECK (actor_label IN ('CITIZEN-DEMO', 'DISPATCHER-DEMO', 'SYSTEM-DEMO', 'AI-DEMO'))
            )
        """)

        # Evaluation runs
        conn.execute("""
            CREATE TABLE IF NOT EXISTS evaluation_runs (
                id TEXT PRIMARY KEY,
                ran_at TEXT NOT NULL,
                scenario_count INTEGER NOT NULL,
                metrics_json TEXT NOT NULL
            )
        """)

        # Route cache table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS route_cache (
                id TEXT PRIMARY KEY,
                origin_lat REAL NOT NULL,
                origin_lng REAL NOT NULL,
                dest_lat REAL NOT NULL,
                dest_lng REAL NOT NULL,
                route_json TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)

        # Indexes for common queries
        conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_type ON incidents(type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_created_at ON incidents(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_responders_status ON responders(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_responders_type ON responders(unit_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dispatches_incident ON dispatches(incident_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dispatches_responder ON dispatches(responder_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_incident ON incident_events(incident_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fact_confirmations_incident ON fact_confirmations(incident_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_route_cache_expires ON route_cache(expires_at)")

        conn.commit()


def reset_database() -> None:
    """Reset the database by dropping and recreating all tables."""
    settings = get_settings()
    if os.path.exists(settings.database_path):
        os.remove(settings.database_path)
    init_database()


@contextmanager
def get_db_transaction() -> Generator[sqlite3.Connection, None, None]:
    """Get a database connection with immediate transaction for write operations."""
    conn = sqlite3.connect(get_db_path(), check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()