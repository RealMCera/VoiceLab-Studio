from __future__ import annotations
import json, sqlite3, threading, os
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path(os.getenv("VOICELAB_DATA_DIR", str(Path(__file__).resolve().parent)))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "voice_lab.sqlite3"
_lock = threading.Lock()

def _now():
    return datetime.now(timezone.utc).isoformat()

def _cols(con, table: str):
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}

def _ensure_column(con, table: str, column: str, ddl: str):
    if column not in _cols(con, table):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

def init_db():
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS history (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          tool TEXT NOT NULL,
          title TEXT NOT NULL,
          output_path TEXT,
          metadata TEXT NOT NULL
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS custom_voices (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          category TEXT NOT NULL,
          provider TEXT NOT NULL,
          provider_voice_id TEXT NOT NULL,
          gender TEXT,
          description TEXT,
          authorized INTEGER NOT NULL DEFAULT 0
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
          item_type TEXT NOT NULL,
          item_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY(item_type, item_id)
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          kind TEXT NOT NULL,
          title TEXT NOT NULL,
          status TEXT NOT NULL,
          progress INTEGER NOT NULL DEFAULT 0,
          phase TEXT NOT NULL DEFAULT '',
          output_url TEXT,
          error TEXT,
          metadata TEXT NOT NULL DEFAULT '{}'
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS users (
          id TEXT PRIMARY KEY,
          email TEXT NOT NULL UNIQUE,
          display_name TEXT NOT NULL,
          password_hash TEXT NOT NULL,
          salt TEXT NOT NULL,
          created_at TEXT NOT NULL,
          is_admin INTEGER NOT NULL DEFAULT 0
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
          token TEXT PRIMARY KEY,
          user_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS shares (
          token TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          title TEXT NOT NULL,
          filename TEXT NOT NULL,
          user_id TEXT,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS catalog_overrides (
          item_id TEXT PRIMARY KEY,
          enabled INTEGER NOT NULL DEFAULT 1,
          note TEXT NOT NULL DEFAULT '',
          updated_at TEXT NOT NULL
        )
        """)
        _ensure_column(con, "history", "user_id", "TEXT")
        _ensure_column(con, "jobs", "user_id", "TEXT")
        con.commit()

def add_history(tool: str, title: str, output_path: str | None, metadata: dict, user_id: str | None = None):
    with _lock, sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            "INSERT INTO history(created_at,tool,title,output_path,metadata,user_id) VALUES(?,?,?,?,?,?)",
            (_now(), tool, title, output_path, json.dumps(metadata), user_id),
        )
        con.commit()
        return cur.lastrowid

def list_history(limit: int = 50, user_id: str | None = None):
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        if user_id:
            rows = con.execute("SELECT * FROM history WHERE user_id=? OR user_id IS NULL ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
        else:
            rows = con.execute("SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out=[]
    for r in rows:
        x=dict(r); x["metadata"]=json.loads(x["metadata"] or "{}")
        out.append(x)
    return out

def upsert_voice(v: dict):
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.execute("""
        INSERT INTO custom_voices(id,name,category,provider,provider_voice_id,gender,description,authorized)
        VALUES(:id,:name,:category,:provider,:provider_voice_id,:gender,:description,:authorized)
        ON CONFLICT(id) DO UPDATE SET
          name=excluded.name, category=excluded.category, provider=excluded.provider,
          provider_voice_id=excluded.provider_voice_id, gender=excluded.gender,
          description=excluded.description, authorized=excluded.authorized
        """, v)
        con.commit()

def delete_voice(voice_id: str):
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.execute("DELETE FROM custom_voices WHERE id=?", (voice_id,))
        con.commit()

def list_custom_voices():
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute("SELECT * FROM custom_voices ORDER BY name")]

def set_favorite(item_type: str, item_id: str, favorite: bool):
    with _lock, sqlite3.connect(DB_PATH) as con:
        if favorite:
            con.execute("INSERT OR IGNORE INTO favorites(item_type,item_id,created_at) VALUES(?,?,?)", (item_type, item_id, _now()))
        else:
            con.execute("DELETE FROM favorites WHERE item_type=? AND item_id=?", (item_type, item_id))
        con.commit()

def list_favorites(item_type: str | None = None):
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        if item_type:
            rows = con.execute("SELECT * FROM favorites WHERE item_type=? ORDER BY created_at DESC", (item_type,)).fetchall()
        else:
            rows = con.execute("SELECT * FROM favorites ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]

def create_job(job_id: str, kind: str, title: str, metadata: dict | None = None, user_id: str | None = None):
    now = _now()
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO jobs(id,created_at,updated_at,kind,title,status,progress,phase,metadata,user_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (job_id, now, now, kind, title, "queued", 0, "Queued", json.dumps(metadata or {}), user_id),
        )
        con.commit()

def update_job(job_id: str, *, status: str | None = None, progress: int | None = None,
               phase: str | None = None, output_url: str | None = None,
               error: str | None = None, metadata: dict | None = None):
    fields, values = ["updated_at=?"], [_now()]
    for name, value in (("status", status), ("progress", progress), ("phase", phase), ("output_url", output_url), ("error", error)):
        if value is not None:
            fields.append(f"{name}=?"); values.append(value)
    if metadata is not None:
        fields.append("metadata=?"); values.append(json.dumps(metadata))
    values.append(job_id)
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id=?", values); con.commit()

def get_job(job_id: str):
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row: return None
    x=dict(row); x["metadata"]=json.loads(x["metadata"] or "{}")
    return x

def list_jobs(limit: int = 25, user_id: str | None = None):
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        if user_id:
            rows=con.execute("SELECT * FROM jobs WHERE user_id=? OR user_id IS NULL ORDER BY created_at DESC LIMIT ?",(user_id,limit)).fetchall()
        else:
            rows=con.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",(limit,)).fetchall()
    out=[]
    for r in rows:
        x=dict(r); x["metadata"]=json.loads(x["metadata"] or "{}"); out.append(x)
    return out

# --- Accounts / sessions ---
def user_count():
    with _lock, sqlite3.connect(DB_PATH) as con:
        return con.execute("SELECT COUNT(*) FROM users").fetchone()[0]

def create_user(user_id: str, email: str, display_name: str, password_hash: str, salt: str, is_admin: bool = False):
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.execute("INSERT INTO users(id,email,display_name,password_hash,salt,created_at,is_admin) VALUES(?,?,?,?,?,?,?)",
                    (user_id,email.lower().strip(),display_name.strip(),password_hash,salt,_now(),1 if is_admin else 0)); con.commit()

def get_user_by_email(email: str):
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.row_factory=sqlite3.Row; r=con.execute("SELECT * FROM users WHERE email=?",(email.lower().strip(),)).fetchone()
    return dict(r) if r else None

def get_user(user_id: str):
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.row_factory=sqlite3.Row; r=con.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone()
    return dict(r) if r else None

def update_user_profile(user_id: str, display_name: str):
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.execute("UPDATE users SET display_name=? WHERE id=?",(display_name.strip(),user_id)); con.commit()

def create_session(token: str, user_id: str, expires_at: str):
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.execute("INSERT INTO sessions(token,user_id,created_at,expires_at) VALUES(?,?,?,?)",(token,user_id,_now(),expires_at)); con.commit()

def get_session(token: str):
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.row_factory=sqlite3.Row; r=con.execute("SELECT * FROM sessions WHERE token=?",(token,)).fetchone()
    return dict(r) if r else None

def delete_session(token: str):
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.execute("DELETE FROM sessions WHERE token=?",(token,)); con.commit()

# --- Share links ---
def create_share(token: str, title: str, filename: str, user_id: str | None = None):
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.execute("INSERT INTO shares(token,created_at,title,filename,user_id) VALUES(?,?,?,?,?)",(token,_now(),title,filename,user_id)); con.commit()

def get_share(token: str):
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.row_factory=sqlite3.Row; r=con.execute("SELECT * FROM shares WHERE token=?",(token,)).fetchone()
    return dict(r) if r else None

def list_shares(limit: int = 50):
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.row_factory=sqlite3.Row; rows=con.execute("SELECT * FROM shares ORDER BY created_at DESC LIMIT ?",(limit,)).fetchall()
    return [dict(r) for r in rows]

# --- Admin catalog overrides ---
def set_catalog_override(item_id: str, enabled: bool, note: str = ""):
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.execute("""INSERT INTO catalog_overrides(item_id,enabled,note,updated_at) VALUES(?,?,?,?)
        ON CONFLICT(item_id) DO UPDATE SET enabled=excluded.enabled,note=excluded.note,updated_at=excluded.updated_at""",
        (item_id,1 if enabled else 0,note,_now())); con.commit()

def list_catalog_overrides():
    with _lock, sqlite3.connect(DB_PATH) as con:
        con.row_factory=sqlite3.Row; rows=con.execute("SELECT * FROM catalog_overrides").fetchall()
    return {r["item_id"]:dict(r) for r in rows}

def admin_counts():
    with _lock, sqlite3.connect(DB_PATH) as con:
        return {
            "users": con.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "jobs": con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
            "history": con.execute("SELECT COUNT(*) FROM history").fetchone()[0],
            "custom_voices": con.execute("SELECT COUNT(*) FROM custom_voices").fetchone()[0],
            "shares": con.execute("SELECT COUNT(*) FROM shares").fetchone()[0],
        }
