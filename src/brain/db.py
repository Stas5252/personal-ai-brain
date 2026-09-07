"""
Database and Persistence Layer for Personal AI Brain.
Provides SQLite storage for profiles, memories, knowledge, style exemplars, clients, projects, and traces.
"""
import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from src.brain.config import DB_PATH

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    c = conn.cursor()
    
    # 1. User Profile table
    c.execute("""
    CREATE TABLE IF NOT EXISTS user_profile (
        id TEXT PRIMARY KEY,
        data_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    
    # 2. Memories table
    c.execute("""
    CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        content TEXT NOT NULL,
        importance REAL NOT NULL,
        confidence REAL NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        source TEXT,
        project_id TEXT,
        client_id TEXT,
        expires_at TEXT,
        status TEXT NOT NULL,
        superseded_by TEXT,
        tags_json TEXT
    )
    """)
    
    # 3. Knowledge Sources & Chunks
    c.execute("""
    CREATE TABLE IF NOT EXISTS knowledge_sources (
        source_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        author TEXT,
        date TEXT,
        type TEXT,
        category TEXT NOT NULL,
        subcategory TEXT,
        tags_json TEXT,
        project TEXT,
        client TEXT,
        language TEXT,
        source_path TEXT,
        timestamp TEXT,
        confidence REAL,
        visual_description TEXT,
        ocr_text TEXT,
        original_filename TEXT,
        mime_type TEXT,
        file_size INTEGER DEFAULT 0,
        sha256 TEXT,
        p_hash TEXT,
        storage_path TEXT,
        derived_dir TEXT,
        ingestion_status TEXT DEFAULT 'COMPLETED',
        processing_version TEXT DEFAULT 'v1.0',
        classification_method TEXT DEFAULT 'rules',
        seen_count INTEGER DEFAULT 1,
        checkpoint_stage TEXT,
        error_message TEXT,
        metadata_json TEXT DEFAULT '{}'
    )
    """)
    
    # Safe schema migration for knowledge_sources if created earlier
    c.execute("PRAGMA table_info(knowledge_sources)")
    existing_cols = {r["name"] for r in c.fetchall()}
    for col_name, col_type in [
        ("original_filename", "TEXT"), ("mime_type", "TEXT"), ("file_size", "INTEGER DEFAULT 0"),
        ("sha256", "TEXT"), ("p_hash", "TEXT"), ("storage_path", "TEXT"), ("derived_dir", "TEXT"),
        ("ingestion_status", "TEXT DEFAULT 'COMPLETED'"), ("processing_version", "TEXT DEFAULT 'v1.0'"),
        ("classification_method", "TEXT DEFAULT 'rules'"), ("seen_count", "INTEGER DEFAULT 1"),
        ("checkpoint_stage", "TEXT"), ("error_message", "TEXT"), ("metadata_json", "TEXT DEFAULT '{}'")
    ]:
        if col_name not in existing_cols:
            c.execute(f"ALTER TABLE knowledge_sources ADD COLUMN {col_name} {col_type}")
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS knowledge_chunks (
        id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL,
        layer TEXT NOT NULL,
        content TEXT NOT NULL,
        metadata_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        content_type TEXT DEFAULT 'text',
        page_number INTEGER,
        slide_number INTEGER,
        sheet_name TEXT,
        start_time REAL,
        end_time REAL,
        heading_path TEXT,
        language TEXT DEFAULT 'ru',
        token_count INTEGER DEFAULT 0,
        FOREIGN KEY(source_id) REFERENCES knowledge_sources(source_id) ON DELETE CASCADE
    )
    """)

    c.execute("PRAGMA table_info(knowledge_chunks)")
    existing_chunk_cols = {r["name"] for r in c.fetchall()}
    for col_name, col_type in [
        ("content_type", "TEXT DEFAULT 'text'"), ("page_number", "INTEGER"),
        ("slide_number", "INTEGER"), ("sheet_name", "TEXT"), ("start_time", "REAL"),
        ("end_time", "REAL"), ("heading_path", "TEXT"), ("language", "TEXT DEFAULT 'ru'"),
        ("token_count", "INTEGER DEFAULT 0")
    ]:
        if col_name not in existing_chunk_cols:
            c.execute(f"ALTER TABLE knowledge_chunks ADD COLUMN {col_name} {col_type}")

    # 3.1 Ingestion Jobs Queue
    c.execute("""
    CREATE TABLE IF NOT EXISTS ingestion_jobs (
        job_id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL,
        status TEXT NOT NULL,
        priority INTEGER NOT NULL DEFAULT 10,
        stage TEXT NOT NULL DEFAULT 'DISCOVERED',
        attempts INTEGER NOT NULL DEFAULT 0,
        max_attempts INTEGER NOT NULL DEFAULT 3,
        next_retry_at TEXT,
        progress REAL NOT NULL DEFAULT 0.0,
        checkpoint_stage TEXT,
        error_message TEXT,
        worker_id TEXT,
        lease_until TEXT,
        heartbeat_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(source_id) REFERENCES knowledge_sources(source_id) ON DELETE CASCADE
    )
    """)

    # Migration for leasing columns in ingestion_jobs
    c.execute("PRAGMA table_info(ingestion_jobs)")
    existing_job_cols = {r["name"] for r in c.fetchall()}
    for col_name, col_type in [
        ("worker_id", "TEXT"), ("lease_until", "TEXT"), ("heartbeat_at", "TEXT")
    ]:
        if col_name not in existing_job_cols:
            c.execute(f"ALTER TABLE ingestion_jobs ADD COLUMN {col_name} {col_type}")

    c.execute("CREATE INDEX IF NOT EXISTS idx_ij_lease ON ingestion_jobs(status, lease_until, priority DESC)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ij_worker ON ingestion_jobs(worker_id)")

    # 3.2 FTS5 Full-Text Search Table
    c.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts USING fts5(
        chunk_id UNINDEXED,
        source_id UNINDEXED,
        content,
        heading_path,
        sheet_name,
        layer UNINDEXED
    )
    """)
    
    # 4. Style Exemplars table
    c.execute("""
    CREATE TABLE IF NOT EXISTS style_exemplars (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        exemplar_type TEXT NOT NULL,
        category TEXT NOT NULL,
        tags_json TEXT,
        notes TEXT,
        created_at TEXT NOT NULL
    )
    """)
    
    # 5. Clients table
    c.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        contact TEXT,
        status TEXT NOT NULL,
        source TEXT,
        budget TEXT,
        service TEXT,
        preferences TEXT,
        objections TEXT,
        history_json TEXT,
        projects_json TEXT,
        notes_json TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    
    # 6. Projects table
    c.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        status TEXT NOT NULL,
        start_date TEXT,
        deadline TEXT,
        client_id TEXT,
        files_json TEXT,
        conversations_json TEXT,
        tasks_json TEXT,
        decisions_json TEXT,
        outputs_json TEXT,
        memory_ids_json TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    
    # Safe migrations for clients
    c.execute("PRAGMA table_info(clients)")
    existing_client_cols = {r["name"] for r in c.fetchall()}
    for col_name, col_type in [
        ("source_channel", "TEXT"), ("preferred_style", "TEXT"),
        ("objections_history_json", "TEXT DEFAULT '[]'"), ("last_contact_at", "TEXT")
    ]:
        if col_name not in existing_client_cols:
            c.execute(f"ALTER TABLE clients ADD COLUMN {col_name} {col_type}")

    # Safe migrations for projects
    c.execute("PRAGMA table_info(projects)")
    existing_project_cols = {r["name"] for r in c.fetchall()}
    for col_name, col_type in [
        ("concept", "TEXT DEFAULT ''"), ("location", "TEXT"),
        ("shot_list_json", "TEXT DEFAULT '[]'"), ("moodboard_refs_json", "TEXT DEFAULT '[]'"),
        ("deliverables_json", "TEXT DEFAULT '[]'")
    ]:
        if col_name not in existing_project_cols:
            c.execute(f"ALTER TABLE projects ADD COLUMN {col_name} {col_type}")

    # 7. Tasks table
    c.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        task_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        type TEXT NOT NULL,
        status TEXT NOT NULL,
        priority TEXT NOT NULL,
        created_at TEXT NOT NULL,
        due_at TEXT,
        project_id TEXT,
        client_id TEXT,
        inputs_json TEXT NOT NULL DEFAULT '{}',
        outputs_json TEXT NOT NULL DEFAULT '{}',
        approval_state TEXT NOT NULL DEFAULT 'NONE'
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, priority, due_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tasks_client ON tasks(client_id)")

    # 8. Workflows table
    c.execute("""
    CREATE TABLE IF NOT EXISTS workflows (
        workflow_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        workflow_type TEXT NOT NULL,
        status TEXT NOT NULL,
        current_step INTEGER NOT NULL DEFAULT 0,
        steps_json TEXT NOT NULL DEFAULT '[]',
        context_json TEXT NOT NULL DEFAULT '{}',
        results_json TEXT NOT NULL DEFAULT '{}',
        approval_state TEXT NOT NULL DEFAULT 'NONE',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_wf_status ON workflows(status, updated_at)")

    # 9. Request Traces table
    c.execute("""
    CREATE TABLE IF NOT EXISTS request_traces (
        request_id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        query TEXT NOT NULL,
        intent TEXT NOT NULL,
        data_json TEXT NOT NULL
    )
    """)
    
    # 10. Onboarding Sessions table
    c.execute("""
    CREATE TABLE IF NOT EXISTS onboarding_sessions (
        session_id TEXT PRIMARY KEY,
        step INTEGER NOT NULL,
        answers_json TEXT NOT NULL,
        completed INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    
    conn.commit()
    conn.close()

# Initialize immediately on import
init_db()
