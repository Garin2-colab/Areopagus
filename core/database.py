"""
core/database.py — SQLite storage layer for Areopagus

Replaces the flat-file history.json read/write pattern with atomic
row-level operations. Each mutation touches only the rows it needs
instead of serializing/deserializing the entire dataset.

Usage on Modal:
    from core.database import get_db
    db = get_db()           # opens /data/areopagus.db (WAL mode)
    db.insert_brain_item(item)
    db.close()              # then call data_volume.commit()

Local / test usage:
    db = AreopagusDB(":memory:")
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from core.config import DATA_DIR

DB_PATH = DATA_DIR / "areopagus.db"

# ── Schema version — bump when adding migrations ──────────────────────────────
SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS turns (
    turn            INTEGER PRIMARY KEY,
    image_id        TEXT,
    image_url       TEXT,
    prompt_text     TEXT,
    keywords        TEXT,  -- JSON array
    agent_id        TEXT,
    agent_name      TEXT,
    action          TEXT,
    thread_id       TEXT,
    category        TEXT,
    parent_turn     INTEGER,
    parent_image_id TEXT,
    root_image_id   TEXT,
    interest_score  INTEGER,
    proposal        TEXT,
    critique        TEXT,
    prompt_json     TEXT,  -- full JSON blob
    image_webp      TEXT,  -- JSON blob
    extra           TEXT,  -- catch-all JSON for future fields
    created_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_turns_thread ON turns(thread_id);
CREATE INDEX IF NOT EXISTS idx_turns_image  ON turns(image_id);

CREATE TABLE IF NOT EXISTS threads (
    thread_id       TEXT PRIMARY KEY,
    root_image_id   TEXT,
    title           TEXT,
    agent_id        TEXT,
    action          TEXT,
    interest_score  INTEGER,
    active          INTEGER DEFAULT 1,
    category        TEXT,
    posts           TEXT,  -- JSON array of image_ids
    comments        TEXT,  -- JSON array of comment objects
    created_at      TEXT,
    updated_at      TEXT
);

CREATE TABLE IF NOT EXISTS brain_items (
    id              TEXT PRIMARY KEY,
    type            TEXT,
    source_file     TEXT,
    title           TEXT,
    keywords        TEXT,  -- JSON array
    summary         TEXT,
    mood            TEXT,
    color_palette   TEXT,  -- JSON array
    excerpt         TEXT,
    image_url       TEXT,
    full_text       TEXT,
    created_at      TEXT,
    updated_at      TEXT
);

CREATE TABLE IF NOT EXISTS briefs (
    brief_id        TEXT PRIMARY KEY,
    title           TEXT,
    thesis          TEXT,
    visual_rules    TEXT,  -- JSON array
    mood            TEXT,
    color_palette   TEXT,  -- JSON array
    source_items    TEXT,  -- JSON array
    keywords        TEXT,  -- JSON array
    active          INTEGER DEFAULT 1,
    auto_generated  INTEGER DEFAULT 1,
    created_at      TEXT,
    updated_at      TEXT
);

CREATE TABLE IF NOT EXISTS inspiration (
    id              TEXT PRIMARY KEY,
    image_url       TEXT,
    keywords        TEXT,  -- JSON array
    created_at      TEXT
);

CREATE TABLE IF NOT EXISTS graph_nodes (
    id    TEXT PRIMARY KEY,
    type  TEXT,
    label TEXT,
    url   TEXT
);

CREATE TABLE IF NOT EXISTS graph_edges (
    rowid_      INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT,
    target      TEXT,
    relation    TEXT
);
CREATE INDEX IF NOT EXISTS idx_edges_source ON graph_edges(source);
CREATE INDEX IF NOT EXISTS idx_edges_target ON graph_edges(target);

-- Full-text search on brain items (keywords + title + summary)
CREATE VIRTUAL TABLE IF NOT EXISTS brain_fts USING fts5(
    id UNINDEXED,
    title,
    summary,
    keywords,
    content='brain_items',
    content_rowid='rowid'
);

-- Triggers to keep FTS in sync with brain_items
CREATE TRIGGER IF NOT EXISTS brain_fts_insert AFTER INSERT ON brain_items BEGIN
    INSERT INTO brain_fts(rowid, id, title, summary, keywords)
    VALUES (new.rowid, new.id, new.title, new.summary, new.keywords);
END;

CREATE TRIGGER IF NOT EXISTS brain_fts_delete AFTER DELETE ON brain_items BEGIN
    INSERT INTO brain_fts(brain_fts, rowid, id, title, summary, keywords)
    VALUES ('delete', old.rowid, old.id, old.title, old.summary, old.keywords);
END;

CREATE TRIGGER IF NOT EXISTS brain_fts_update AFTER UPDATE ON brain_items BEGIN
    INSERT INTO brain_fts(brain_fts, rowid, id, title, summary, keywords)
    VALUES ('delete', old.rowid, old.id, old.title, old.summary, old.keywords);
    INSERT INTO brain_fts(rowid, id, title, summary, keywords)
    VALUES (new.rowid, new.id, new.title, new.summary, new.keywords);
END;
"""


def _json_dumps(obj: Any) -> str:
    """Compact JSON serialization for storage."""
    if obj is None:
        return "[]"
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _json_loads(text: str | None) -> Any:
    """Safe JSON deserialization."""
    if not text:
        return []
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []


class AreopagusDB:
    """Thin wrapper around SQLite for the Areopagus data layer."""

    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(_SCHEMA_SQL)
        self._ensure_version()

    def _ensure_version(self) -> None:
        cur = self.conn.execute("SELECT value FROM meta WHERE key='schema_version'")
        row = cur.fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO meta(key,value) VALUES('schema_version',?)",
                (str(SCHEMA_VERSION),),
            )
            self.conn.commit()

    def close(self) -> None:
        if self.conn:
            self.conn.close()

    # ── Brain Items ───────────────────────────────────────────────────────

    def upsert_brain_item(self, item: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO brain_items
               (id, type, source_file, title, keywords, summary, mood,
                color_palette, excerpt, image_url, full_text, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item["id"],
                item.get("type", "image"),
                item.get("source_file", ""),
                item.get("title", ""),
                _json_dumps(item.get("keywords", [])),
                item.get("summary", ""),
                item.get("mood", ""),
                _json_dumps(item.get("color_palette", [])),
                item.get("excerpt", ""),
                item.get("image_url", ""),
                item.get("full_text"),
                item.get("created_at", ""),
                item.get("updated_at", ""),
            ),
        )
        self.conn.commit()

    def delete_brain_item(self, brain_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM brain_items WHERE id=?", (brain_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def get_brain_item(self, brain_id: str) -> dict[str, Any] | None:
        cur = self.conn.execute("SELECT * FROM brain_items WHERE id=?", (brain_id,))
        row = cur.fetchone()
        return self._brain_row_to_dict(row) if row else None

    def list_brain_items(
        self,
        *,
        limit: int = 0,
        offset: int = 0,
        item_type: str = "",
        search: str = "",
    ) -> tuple[list[dict[str, Any]], int]:
        """Return (items, total_count) with optional filtering and pagination."""
        where_clauses: list[str] = []
        params: list[Any] = []

        if item_type:
            req_type = "document" if item_type == "note" else item_type
            where_clauses.append("type=?")
            params.append(req_type)

        if search:
            # Use FTS5 for fast keyword/title/summary search
            where_clauses.append(
                "id IN (SELECT id FROM brain_fts WHERE brain_fts MATCH ?)"
            )
            # Escape FTS special chars and add prefix matching
            safe_q = search.replace('"', '""')
            params.append(f'"{safe_q}"*')

        where = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        count_cur = self.conn.execute(
            f"SELECT COUNT(*) FROM brain_items{where}", params
        )
        total = count_cur.fetchone()[0]

        query = f"SELECT * FROM brain_items{where} ORDER BY created_at DESC"
        if limit > 0:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

        rows = self.conn.execute(query, params).fetchall()
        return [self._brain_row_to_dict(r) for r in rows], total

    def search_brain_keywords(self, keywords: list[str], limit: int = 5) -> list[dict[str, Any]]:
        """FTS5 keyword search for associative memory retrieval."""
        if not keywords:
            return []
        cleaned = [k.lower().lstrip("#") for k in keywords if k]
        if not cleaned:
            return []
        match_expr = " OR ".join(f'"{kw}"' for kw in cleaned)
        rows = self.conn.execute(
            "SELECT id FROM brain_fts WHERE brain_fts MATCH ? ORDER BY rank LIMIT ?",
            (match_expr, limit),
        ).fetchall()
        ids = [r["id"] for r in rows]
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        items = self.conn.execute(
            f"SELECT * FROM brain_items WHERE id IN ({placeholders})", ids
        ).fetchall()
        return [self._brain_row_to_dict(r) for r in items]

    def brain_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM brain_items").fetchone()[0]

    @staticmethod
    def _brain_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["keywords"] = _json_loads(d.get("keywords"))
        d["color_palette"] = _json_loads(d.get("color_palette"))
        return d

    # ── Turns ─────────────────────────────────────────────────────────────

    def insert_turn(self, turn: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO turns
               (turn, image_id, image_url, prompt_text, keywords, agent_id, agent_name,
                action, thread_id, category, parent_turn, parent_image_id, root_image_id,
                interest_score, proposal, critique, prompt_json, image_webp, extra, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                turn.get("turn"),
                turn.get("image_id"),
                turn.get("image_url"),
                turn.get("prompt_text", ""),
                _json_dumps(turn.get("keywords", [])),
                turn.get("agent_id"),
                turn.get("agent_name"),
                turn.get("action"),
                turn.get("thread_id"),
                turn.get("category"),
                turn.get("parent_turn"),
                turn.get("parent_image_id"),
                turn.get("root_image_id"),
                turn.get("interest_score"),
                turn.get("proposal"),
                turn.get("critique"),
                _json_dumps(turn.get("prompt_json")) if turn.get("prompt_json") else None,
                _json_dumps(turn.get("image_webp")) if turn.get("image_webp") else None,
                None,  # extra
                turn.get("created_at", ""),
            ),
        )
        self.conn.commit()

    def list_turns(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM turns ORDER BY turn ASC").fetchall()
        return [self._turn_row_to_dict(r) for r in rows]

    def turn_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0]

    @staticmethod
    def _turn_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["keywords"] = _json_loads(d.get("keywords"))
        d["prompt_json"] = _json_loads(d.get("prompt_json")) if d.get("prompt_json") else None
        d["image_webp"] = _json_loads(d.get("image_webp")) if d.get("image_webp") else None
        d.pop("extra", None)
        return d

    # ── Threads ───────────────────────────────────────────────────────────

    def upsert_thread(self, thread: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO threads
               (thread_id, root_image_id, title, agent_id, action, interest_score,
                active, category, posts, comments, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                thread["thread_id"],
                thread.get("root_image_id"),
                thread.get("title"),
                thread.get("agent_id"),
                thread.get("action"),
                thread.get("interest_score"),
                1 if thread.get("active", True) else 0,
                thread.get("category"),
                _json_dumps(thread.get("posts", [])),
                _json_dumps(thread.get("comments", [])),
                thread.get("created_at", ""),
                thread.get("updated_at", ""),
            ),
        )
        self.conn.commit()

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        cur = self.conn.execute("SELECT * FROM threads WHERE thread_id=?", (thread_id,))
        row = cur.fetchone()
        return self._thread_row_to_dict(row) if row else None

    def list_threads(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM threads ORDER BY updated_at DESC").fetchall()
        return [self._thread_row_to_dict(r) for r in rows]

    @staticmethod
    def _thread_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["posts"] = _json_loads(d.get("posts"))
        d["comments"] = _json_loads(d.get("comments"))
        d["active"] = bool(d.get("active", 1))
        return d

    # ── Briefs ────────────────────────────────────────────────────────────

    def upsert_brief(self, brief: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO briefs
               (brief_id, title, thesis, visual_rules, mood, color_palette,
                source_items, keywords, active, auto_generated, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                brief["brief_id"],
                brief.get("title", ""),
                brief.get("thesis", ""),
                _json_dumps(brief.get("visual_rules", [])),
                brief.get("mood", ""),
                _json_dumps(brief.get("color_palette", [])),
                _json_dumps(brief.get("source_items", [])),
                _json_dumps(brief.get("keywords", [])),
                1 if brief.get("active", True) else 0,
                1 if brief.get("auto_generated", True) else 0,
                brief.get("created_at", ""),
                brief.get("updated_at", ""),
            ),
        )
        self.conn.commit()

    def delete_brief(self, brief_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM briefs WHERE brief_id=?", (brief_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def list_briefs(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM briefs ORDER BY created_at DESC").fetchall()
        return [self._brief_row_to_dict(r) for r in rows]

    @staticmethod
    def _brief_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["visual_rules"] = _json_loads(d.get("visual_rules"))
        d["color_palette"] = _json_loads(d.get("color_palette"))
        d["source_items"] = _json_loads(d.get("source_items"))
        d["keywords"] = _json_loads(d.get("keywords"))
        d["active"] = bool(d.get("active", 1))
        d["auto_generated"] = bool(d.get("auto_generated", 1))
        return d

    # ── Inspiration ───────────────────────────────────────────────────────

    def upsert_inspiration(self, item: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO inspiration (id, image_url, keywords, created_at)
               VALUES (?,?,?,?)""",
            (
                item["id"],
                item.get("image_url", ""),
                _json_dumps(item.get("keywords", [])),
                item.get("created_at", ""),
            ),
        )
        self.conn.commit()

    def delete_inspiration(self, insp_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM inspiration WHERE id=?", (insp_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def list_inspiration(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM inspiration ORDER BY created_at DESC").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["keywords"] = _json_loads(d.get("keywords"))
            result.append(d)
        return result

    # ── Graph ─────────────────────────────────────────────────────────────

    def upsert_graph_node(self, node: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO graph_nodes (id, type, label, url) VALUES (?,?,?,?)",
            (node["id"], node.get("type", ""), node.get("label", ""), node.get("url", "")),
        )

    def add_graph_edge(self, source: str, target: str, relation: str) -> None:
        self.conn.execute(
            "INSERT INTO graph_edges (source, target, relation) VALUES (?,?,?)",
            (source, target, relation),
        )

    def clear_graph(self) -> None:
        self.conn.execute("DELETE FROM graph_nodes")
        self.conn.execute("DELETE FROM graph_edges")
        self.conn.commit()

    def get_graph(self) -> dict[str, Any]:
        nodes = [dict(r) for r in self.conn.execute("SELECT * FROM graph_nodes").fetchall()]
        edges_raw = self.conn.execute("SELECT source, target, relation FROM graph_edges").fetchall()
        edges = [{"from": r["source"], "to": r["target"], "relation": r["relation"]} for r in edges_raw]
        return {"nodes": nodes, "edges": edges}

    def graph_node_ids(self) -> set[str]:
        rows = self.conn.execute("SELECT id FROM graph_nodes").fetchall()
        return {r["id"] for r in rows}

    def batch_insert_graph(self, nodes: list[dict], edges: list[dict]) -> None:
        """Bulk insert graph nodes and edges in a single transaction."""
        with self.conn:
            self.conn.executemany(
                "INSERT OR IGNORE INTO graph_nodes (id, type, label, url) VALUES (?,?,?,?)",
                [(n["id"], n.get("type", ""), n.get("label", ""), n.get("url", "")) for n in nodes],
            )
            self.conn.executemany(
                "INSERT INTO graph_edges (source, target, relation) VALUES (?,?,?)",
                [(e.get("from", e.get("source", "")), e.get("to", e.get("target", "")), e.get("relation", "")) for e in edges],
            )

    # ── Meta ──────────────────────────────────────────────────────────────

    def get_meta(self, key: str, default: str = "") -> str:
        cur = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,))
        row = cur.fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, value)
        )
        self.conn.commit()

    # ── Full Export (for history_endpoint compatibility) ───────────────────

    def export_as_history_dict(self) -> dict[str, Any]:
        """Export the entire database as a history.json-compatible dict.
        Used by the history_endpoint for backwards compatibility with the frontend."""
        return {
            "project": self.get_meta("project", "Areopagus"),
            "created_at": self.get_meta("created_at", ""),
            "updated_at": self.get_meta("updated_at", ""),
            "turns": self.list_turns(),
            "threads": self.list_threads(),
            "inspiration": self.list_inspiration(),
            "brain": [],  # populated by caller with pagination
            "briefs": self.list_briefs(),
            "graph": self.get_graph(),
        }


# ── Migration: history.json → SQLite ─────────────────────────────────────────


def migrate_json_to_sqlite(json_path: str | Path, db_path: str | Path = DB_PATH) -> AreopagusDB:
    """One-time migration: read history.json and insert all data into SQLite."""
    json_path = Path(json_path)
    if not json_path.exists():
        print(f"[migrate] No history.json found at {json_path}. Creating empty DB.")
        return AreopagusDB(db_path)

    with json_path.open("r", encoding="utf-8") as f:
        history = json.load(f)

    db = AreopagusDB(db_path)

    # Meta
    db.set_meta("project", history.get("project", "Areopagus"))
    db.set_meta("created_at", history.get("created_at", ""))
    db.set_meta("updated_at", history.get("updated_at", ""))

    # Turns
    for turn in history.get("turns", []):
        if isinstance(turn, dict):
            db.insert_turn(turn)
    print(f"[migrate] Imported {db.turn_count()} turns.")

    # Threads
    for thread in history.get("threads", []):
        if isinstance(thread, dict) and "thread_id" in thread:
            db.upsert_thread(thread)
    print(f"[migrate] Imported {len(history.get('threads', []))} threads.")

    # Brain items
    for item in history.get("brain", []):
        if isinstance(item, dict) and "id" in item:
            db.upsert_brain_item(item)
    print(f"[migrate] Imported {db.brain_count()} brain items.")

    # Briefs
    for brief in history.get("briefs", []):
        if isinstance(brief, dict) and "brief_id" in brief:
            db.upsert_brief(brief)
    print(f"[migrate] Imported {len(history.get('briefs', []))} briefs.")

    # Inspiration
    for item in history.get("inspiration", []):
        if isinstance(item, dict) and "id" in item:
            db.upsert_inspiration(item)
    print(f"[migrate] Imported {len(history.get('inspiration', []))} inspiration items.")

    # Graph
    graph = history.get("graph", {})
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    db.batch_insert_graph(nodes, edges)
    print(f"[migrate] Imported {len(nodes)} graph nodes, {len(edges)} graph edges.")

    print(f"[migrate] Migration complete -> {db_path}")
    return db


# ── Singleton accessor ────────────────────────────────────────────────────────

_db_instance: AreopagusDB | None = None


def get_db(db_path: str | Path = DB_PATH) -> AreopagusDB:
    """Get or create the singleton DB connection."""
    global _db_instance
    if _db_instance is None:
        _db_instance = AreopagusDB(db_path)
    return _db_instance
