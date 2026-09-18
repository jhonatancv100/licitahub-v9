#!/usr/bin/env python3
"""Migra cuentas y estado de la V8/V9 SQLite a PostgreSQL.

Uso:
  set DATABASE_URL=postgresql://...
  python migrate_sqlite_to_postgres.py

No migra sesiones activas: todos vuelven a iniciar sesión después de la migración.
"""
from __future__ import annotations
import json, os, sqlite3, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCE=Path(os.environ.get("SQLITE_SOURCE", ROOT/"data"/"portal.db"))
URL=os.environ.get("DATABASE_URL","").strip()
if not URL.startswith(("postgres://","postgresql://")):
    raise SystemExit("Define DATABASE_URL con una cadena PostgreSQL/Supabase.")
if not SOURCE.exists():
    raise SystemExit(f"No existe la base SQLite: {SOURCE}")
try:
    import psycopg
    from psycopg.rows import dict_row
except Exception as exc:
    raise SystemExit("Falta psycopg. Ejecuta: pip install -r requirements.txt") from exc

schema=[
"""CREATE TABLE IF NOT EXISTS users (id BIGSERIAL PRIMARY KEY,email TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,name TEXT NOT NULL DEFAULT '',created_at BIGINT NOT NULL,updated_at BIGINT NOT NULL)""",
"""CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY,user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,csrf_token TEXT NOT NULL,created_at BIGINT NOT NULL,expires_at BIGINT NOT NULL)""",
"CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)",
"""CREATE TABLE IF NOT EXISTS user_state (user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,key TEXT NOT NULL,value_json TEXT NOT NULL,updated_at BIGINT NOT NULL,PRIMARY KEY(user_id,key))""",
"""CREATE TABLE IF NOT EXISTS source_cache (cache_key TEXT PRIMARY KEY,payload_json TEXT NOT NULL,updated_at BIGINT NOT NULL)""",
"""CREATE TABLE IF NOT EXISTS job_locks (name TEXT PRIMARY KEY,owner TEXT NOT NULL,locked_until BIGINT NOT NULL,updated_at BIGINT NOT NULL)""",
"""CREATE TABLE IF NOT EXISTS email_log (id BIGSERIAL PRIMARY KEY,user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,alert_id TEXT,recipient TEXT NOT NULL,subject TEXT NOT NULL,sent_at BIGINT NOT NULL,status TEXT NOT NULL,detail TEXT NOT NULL DEFAULT '')""",
]

src=sqlite3.connect(SOURCE); src.row_factory=sqlite3.Row
with psycopg.connect(URL,row_factory=dict_row) as dst:
    for stmt in schema: dst.execute(stmt)
    users=list(src.execute("SELECT id,email,password_hash,name,created_at,updated_at FROM users ORDER BY id"))
    id_map={}
    for r in users:
        cur=dst.execute("""INSERT INTO users(email,password_hash,name,created_at,updated_at) VALUES(%s,%s,%s,%s,%s)
                    ON CONFLICT(email) DO UPDATE SET password_hash=excluded.password_hash,name=excluded.name,updated_at=excluded.updated_at
                    RETURNING id""",
                    (r['email'],r['password_hash'],r['name'],r['created_at'],r['updated_at']))
        id_map[int(r['id'])]=int(cur.fetchone()['id'])
    states=list(src.execute("SELECT user_id,key,value_json,updated_at FROM user_state"))
    for r in states:
        target_uid=id_map.get(int(r['user_id']))
        if target_uid is None: continue
        dst.execute("""INSERT INTO user_state(user_id,key,value_json,updated_at) VALUES(%s,%s,%s,%s)
                    ON CONFLICT(user_id,key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at""",
                    (target_uid,r['key'],r['value_json'],r['updated_at']))
    try: caches=list(src.execute("SELECT cache_key,payload_json,updated_at FROM source_cache"))
    except sqlite3.OperationalError: caches=[]
    for r in caches:
        dst.execute("""INSERT INTO source_cache(cache_key,payload_json,updated_at) VALUES(%s,%s,%s)
                    ON CONFLICT(cache_key) DO UPDATE SET payload_json=excluded.payload_json,updated_at=excluded.updated_at""",
                    (r['cache_key'],r['payload_json'],r['updated_at']))
    dst.execute("DELETE FROM sessions")
    dst.commit()
src.close()
print(json.dumps({"ok":True,"users":len(users),"stateRows":len(states),"cacheRows":len(caches),"source":str(SOURCE),"migratedAt":int(time.time())},ensure_ascii=False,indent=2))
