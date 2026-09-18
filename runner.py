#!/usr/bin/env python3
import base64, pathlib, runpy
ROOT=pathlib.Path(__file__).resolve().parent

def materialize(prefix,out):
    parts=sorted((ROOT/'bundle').glob(prefix+'.*'))
    if not parts: raise RuntimeError('No se encontraron partes para '+prefix)
    raw=''.join(p.read_text(encoding='utf-8').strip() for p in parts)
    (ROOT/out).write_bytes(base64.b64decode(raw))

materialize('server.b64','server_runtime.py')
materialize('index.b64','index.html')
runpy.run_path(str(ROOT/'server_runtime.py'),run_name='__main__')
