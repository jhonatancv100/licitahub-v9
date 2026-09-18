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

runpy.run_path(str(ROOT / "server_v10.py"), run_name="__main__")
