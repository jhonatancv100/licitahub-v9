#!/usr/bin/env python3
# Puente temporal para conservar la configuración actual del servicio Render.
# La aplicación de producción real se construye/ejecuta desde V10.
import runpy
from pathlib import Path
ROOT = Path(__file__).resolve().parent
runpy.run_path(str(ROOT / "v10_bootstrap.py"), run_name="__main__")
