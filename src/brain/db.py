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
        ocr_text TEXT
    )
    """)
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS knowledge_chunks (
        id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL,
        layer TEXT NOT NULL,
        content TEXT NOT NULL,
        metadata_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(source_id) REFERENCES knowledge_sources(source_id) ON DELETE CASCADE
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
    
    # 7. Request Traces table
    c.execute("""
    CREATE TABLE IF NOT EXISTS request_traces (
        request_id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        query TEXT NOT NULL,
        intent TEXT NOT NULL,
        data_json TEXT NOT NULL
    )
    """)
    
    # 8. Onboarding Sessions table
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
