#!/usr/bin/env python3
"""
Verify that compiled app.js is up-to-date with app.ts source.

Run this after frontend changes to catch missing compilation steps.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_TS = PROJECT_ROOT / "src" / "quantflow" / "web" / "static" / "app.ts"
APP_JS = PROJECT_ROOT / "src" / "quantflow" / "web" / "static" / "app.js"


def main() -> int:
    errors = 0

    # Check both files exist
    if not APP_TS.exists():
        print(f"MISSING: {APP_TS}")
        return 1
    if not APP_JS.exists():
        print(f"MISSING: {APP_JS}")
        return 1

    ts_mtime = APP_TS.stat().st_mtime
    js_mtime = APP_JS.stat().st_mtime

    if js_mtime < ts_mtime:
        print(f"STALE: app.js is older than app.ts")
        print(f"  app.ts: {APP_TS}")
        print(f"  app.js: {APP_JS}")
        print(f"  Run: tsc --target ES2020 --removeComments --noEmitHelpers \\")
        print(f"       --lib ES2020,DOM --outFile src/quantflow/web/static/app.js \\")
        print(f"       --module none --strict false \\")
        print(f"       --ignoreDeprecations \"6.0\" \\")
        print(f"       src/quantflow/web/static/app.ts")
        errors += 1
    else:
        print(f"OK: app.js ({js_mtime:.0f}) >= app.ts ({ts_mtime:.0f})")

    # Quick content check: app.js should contain key symbols from app.ts
    js_content = APP_JS.read_text()
    required_symbols = ["switchTab", "loadLibraryStrategies", "switchLibrarySubTab", "renderLibraryStrategies"]
    for sym in required_symbols:
        if sym not in js_content:
            print(f"MISSING in app.js: {sym}")
            errors += 1

    if errors == 0:
        print("All checks passed.")
    return errors


if __name__ == "__main__":
    sys.exit(main())
