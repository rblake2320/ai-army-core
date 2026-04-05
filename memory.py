"""
AGI Core — Episodic Memory
Logs every agent action + outcome. Queryable by any agent before acting.
Prevents repeating failures. Compounds successes.
"""
import sqlite3
import json
import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path.home() / "ai-business/agi-core/episodic.db"

def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    c.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT DEFAULT (datetime('now')),
            agent TEXT NOT NULL,
            goal TEXT NOT NULL,
            action TEXT NOT NULL,
            outcome TEXT,
            success INTEGER DEFAULT 0,
            tags TEXT DEFAULT '[]',
            meta TEXT DEFAULT '{}'
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS nlf_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT DEFAULT (datetime('now')),
            source TEXT,
            original TEXT,
            correction TEXT,
            applied INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT DEFAULT (datetime('now')),
            priority INTEGER DEFAULT 5,
            goal TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            assigned_agent TEXT,
            outcome TEXT,
            approved_by TEXT
        )
    """)
    c.commit()
    return c

def log_episode(agent: str, goal: str, action: str,
                outcome: str = "", success: bool = False,
                tags: list = None, meta: dict = None) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO episodes (agent,goal,action,outcome,success,tags,meta) VALUES (?,?,?,?,?,?,?)",
            (agent, goal, action, outcome, int(success),
             json.dumps(tags or []), json.dumps(meta or {}))
        )
        return cur.lastrowid

def log_nlf_correction(source: str, original: str, correction: str) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO nlf_corrections (source,original,correction) VALUES (?,?,?)",
            (source, original, correction)
        )
        return cur.lastrowid

def get_correction_count(applied: bool = False) -> int:
    with _conn() as c:
        row = c.execute(
            "SELECT COUNT(*) as n FROM nlf_corrections WHERE applied=?",
            (int(applied),)
        ).fetchone()
        return row["n"]

def mark_corrections_applied():
    with _conn() as c:
        c.execute("UPDATE nlf_corrections SET applied=1 WHERE applied=0")

def add_goal(goal: str, priority: int = 5, assigned_agent: str = "") -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO goals (goal,priority,assigned_agent) VALUES (?,?,?)",
            (goal, priority, assigned_agent)
        )
        return cur.lastrowid

def get_pending_goals(limit: int = 10) -> list:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM goals WHERE status='pending' ORDER BY priority ASC, ts ASC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

def complete_goal(goal_id: int, outcome: str, success: bool):
    with _conn() as c:
        c.execute(
            "UPDATE goals SET status=?,outcome=? WHERE id=?",
            ('completed' if success else 'failed', outcome, goal_id)
        )

def get_success_patterns(limit: int = 20) -> list:
    with _conn() as c:
        rows = c.execute(
            "SELECT agent, goal, action, outcome FROM episodes WHERE success=1 ORDER BY ts DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

def get_failure_patterns(limit: int = 20) -> list:
    with _conn() as c:
        rows = c.execute(
            "SELECT agent, goal, action, outcome FROM episodes WHERE success=0 ORDER BY ts DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

def get_stats() -> dict:
    with _conn() as c:
        total = c.execute("SELECT COUNT(*) as n FROM episodes").fetchone()["n"]
        wins  = c.execute("SELECT COUNT(*) as n FROM episodes WHERE success=1").fetchone()["n"]
        corrections = c.execute("SELECT COUNT(*) as n FROM nlf_corrections").fetchone()["n"]
        pending_goals = c.execute("SELECT COUNT(*) as n FROM goals WHERE status='pending'").fetchone()["n"]
        return {
            "total_episodes": total,
            "successes": wins,
            "failures": total - wins,
            "win_rate": round(wins/total*100, 1) if total else 0,
            "nlf_corrections": corrections,
            "pending_goals": pending_goals,
        }

if __name__ == "__main__":
    import sys
    if "--stats" in sys.argv:
        import pprint; pprint.pprint(get_stats())
    elif "--patterns" in sys.argv:
        print("SUCCESS PATTERNS:"); [print(" ", p) for p in get_success_patterns(5)]
        print("FAILURE PATTERNS:"); [print(" ", p) for p in get_failure_patterns(5)]
    else:
        print("memory.py -- AGI episodic memory store")
        print("  --stats     show memory statistics")
        print("  --patterns  show success/failure patterns")
