"""Validate Blender checks by success markers: Blender can exit 0 on script errors."""
import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
machine = json.loads((root / "runtime/development.json").read_text())
output = root / "test_output/validation"
output.mkdir(parents=True, exist_ok=True)
checks = (("blender_smoke.py", "STUDIO_SMOKE_TESTS_PASSED"), ("blender_restart.py", "STUDIO_RESTART_TEST_PASSED"))
if "--batch-only" in sys.argv:
    checks = (("blender_batch.py", "STUDIO_BATCH_TEST_PASSED"),)
if "--package-only" in sys.argv:
    checks = (("blender_package.py", "STUDIO_PACKAGE_TEST_PASSED"),)
if "--setup-only" in sys.argv:
    checks = (("blender_setup.py", "STUDIO_SETUP_TEST_PASSED"),)
for script, marker in checks:
    result = subprocess.run([machine["blender"], "--background", "--factory-startup", "--python", str(root / "tests" / script)],
        capture_output=True, text=True, errors="replace", timeout=180)
    log = result.stdout + result.stderr
    (output / (script + ".log")).write_text(log, encoding="utf8")
    if result.returncode or marker not in log:
        print(log[-6000:])
        sys.exit(1)
    print(marker, flush=True)
