#!/usr/bin/env python3
import runpy
from pathlib import Path
ROOT=Path(__file__).resolve().parent
runpy.run_path(str(ROOT/"server_v10_1.py"),run_name="__main__")
