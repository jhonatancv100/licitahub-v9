#!/usr/bin/env python3
from __future__ import annotations
import base64, io, pathlib, runpy, tarfile

ROOT = pathlib.Path(__file__).resolve().parent
PARTS = sorted((ROOT / "v10_payload").glob("payload.part.*"))
if not PARTS:
    raise RuntimeError("No se encontró el payload V10")

raw = "".join(p.read_text(encoding="utf-8").strip() for p in PARTS)
archive = base64.b64decode(raw)

allowed = {"server_v10.py","index_v10.html","styles_v10.css","app_v10.js"}
with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tf:
    names = set(tf.getnames())
    if not names.issubset(allowed):
        raise RuntimeError("Payload V10 contiene rutas no permitidas")
    for member in tf.getmembers():
        if not member.isfile() or member.name not in allowed:
            raise RuntimeError("Entrada V10 no permitida: " + member.name)
        data = tf.extractfile(member).read()
        (ROOT / member.name).write_bytes(data)

# El backend espera index.html, app.js y styles.css.
(ROOT / "index.html").write_bytes((ROOT / "index_v10.html").read_bytes())
(ROOT / "app.js").write_bytes((ROOT / "app_v10.js").read_bytes())
(ROOT / "styles.css").write_bytes((ROOT / "styles_v10.css").read_bytes())

# Migra únicamente la caché de fuentes de versiones anteriores. No toca usuarios,
# sesiones, seguimiento ni alertas. La V9 tuvo una tabla source_cache con columnas
# distintas; al ser solo caché pública, es seguro recrearla si su esquema no coincide.
try:
    import os, psycopg
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        with psycopg.connect(url) as c:
            rows = c.execute("""SELECT column_name FROM information_schema.columns
                                WHERE table_schema='public' AND table_name='source_cache'""").fetchall()
            cols = {r[0] for r in rows}
            if cols and not {"cache_key","payload_json","updated_at"}.issubset(cols):
                c.execute("DROP TABLE source_cache")
                c.commit()
except Exception as exc:
    print("[v10 migration cache]", exc, flush=True)

runpy.run_path(str(ROOT / "server_v10.py"), run_name="__main__")
