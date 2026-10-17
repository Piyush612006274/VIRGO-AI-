"""Repeat critical static/runtime-contract checks 50 times.

This is deliberately deterministic and does not claim a real trained model exists.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY_FILES = [p for p in ROOT.rglob("*.py") if ".venv" not in p.parts and "__pycache__" not in p.parts]


def run_once() -> list[str]:
    failures: list[str] = []
    for path in PY_FILES:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            failures.append(f"syntax:{path}:{exc}")
    identity = (ROOT / "virgo-ai-core/virgo/application/conversation/identity.py").read_text(encoding="utf-8")
    for required in ("Piyush", "creator", "owner", "master"):
        if required not in identity:
            failures.append(f"identity-missing:{required}")
    provider = (ROOT / "virgo-ai-core/apps/desktop/controller.py").read_text(encoding="utf-8")
    if 'ModelRouter((ollama, slm))' not in provider:
        failures.append("router-provider-order")
    router = (ROOT / "virgo-ai-core/virgo/intelligence/routing/model_router.py").read_text(encoding="utf-8")
    if "mapping.setdefault" not in router:
        failures.append("router-registration")
    preset = (ROOT / "virgo_slm/configs/presets.py").read_text(encoding="utf-8")
    if '"virgo-slm-main"' not in preset:
        failures.append("main-preset")
    return failures


def main() -> int:
    all_failures: list[str] = []
    for i in range(1, 51):
        failures = run_once()
        if failures:
            all_failures.extend([f"loop={i}:{x}" for x in failures])
    if all_failures:
        print("FAIL")
        print("\n".join(all_failures))
        return 1
    print(f"PASS: 50/50 loops; {len(PY_FILES)} Python files parsed on every loop")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
