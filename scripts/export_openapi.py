#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate reference OpenAPI from the composed application (no database mutation)."""

import importlib
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "apps/api"))
app = importlib.import_module("app.main").app

output = root / "docs/api/openapi.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(
    json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(f"OpenAPI: {len(app.openapi()['paths'])} paths → docs/api/openapi.json")
