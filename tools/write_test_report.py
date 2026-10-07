"""Create a source-backed verification report from completed test outputs."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
worker = json.loads((root / "test_output/worker/summary.json").read_text())
latest = Path(json.loads((root / "test_output/blender/latest.json").read_text())["output"])
blender = json.loads((latest / "summary.json").read_text())
bridge = json.loads((root / "test_output/bridge/summary.json").read_text())
batch = json.loads((root / "test_output/batch/summary.json").read_text())
assert all(v["ok"] for v in worker["tests"].values())
assert all(v is True for v in blender["tests"].values())
assert all(bridge.values()) and batch["modal_queue"]
rows = []
for name in ("chair_42", "pan_12", "box_8", "cabinet_7"):
    meta = worker["tests"][name]["metadata"]
    item = blender["assets"][name]
    rows.append(f'| {name} | {meta["generation_seconds"]:.3f}s | {item["append_seconds"]:.3f}s | {meta.get("peak_worker_memory_mb", 0):.1f} MB | {item["statistics"]["triangles"]:,} | {item["joints"]} |')
report = """# Verification — 2026-10-06

Tested on the user's Infinigen 1.19.0 commit 01c39c7f7adcf7363ccbcc57c64410c69f4a4e7c,
WSL Ubuntu-22.04 Python 3.11.16/bpy 4.2.0, Windows Blender 4.2.0.
The catalog contains 276 AST-discovered generator candidates. Four representative
families are verified; the full catalog is not certified.

## Passed workflows

- Add-on registration/unregistration and real native sidebar rendering.
- Source discovery, generator selection, schema controls, parameter locks/randomization.
- Chair generation, same-seed geometry reproduction, seed-only and parameter-only changes.
- Pan, articulated box and articulated cabinet generation; CPU rendered thumbnails.
- Box joints change evaluated geometry, reset restores it, normalized slider moves
  an active joint, and saved edited sockets restore the pose. Box: 16 native joint
  groups; cabinet: 2. Some box joint groups belong to inactive generator branches.
- Preset save/load, native project save/reopen, favorite library save/open/toggle.
- Two sequential pan variations through the actual UI generation queue with simulated
  TIMER events in background Blender, then thumbnail selection and preview visibility.
- Non-destructive LOD/collision copies; original geometry remains unchanged.
- .blend, GLB, FBX, OBJ and USD export; temporary export copies are removed.
- GLB reimport and a separate Blender process reopening saved Studio session/library.
- Invalid parameter handling with categorized error and technical details.
- Windows-to-WSL bridge generation and process-group cancellation.
- Cancellation before worker startup is protected by a persisted cancellation marker.
- The installable ZIP registers and generates from an isolated extracted package,
  without installing into or saving user Blender preferences.
- Live sidebar Generate button produced a chair and preview thumbnail. Mouse/keyboard
  testing stopped when the user pressed Escape; final queue verification used background
  tests so ordinary computer use remained available.

## Approximate measured performance

| Asset / seed | Native generation | Append + inspect + hash | Peak worker RSS | Triangles | Native joint groups |
|---|---:|---:|---:|---:|---:|
""" + "\n".join(rows) + """

Generation time covers native factory construction, geometry and materials, not process
startup, source imports, thumbnail rendering or host import. Complete jobs in this run
took roughly 6–10 seconds. Append timings include statistics and reproducibility hashing;
they are not pure UI frame timings. Peak RSS is for the worker process, not combined
Blender/WSL/GPU usage. Results are representative samples, not a performance guarantee.

Chair geometry is already heavily subdivided by the native factory. Reducing remaining
modifiers cannot remove subdivision applied during construction. LOD copies address
export complexity without pretending the Draft switch accelerates that construction.

## Test commands and evidence

- `python -m unittest discover -s tests -p test_core.py` — four pure-Python tests.
- Installed Infinigen Python: `tests/run_worker_tests.py <existing-infinigen-source>`.
- `python tools/run_validation.py` — background Blender smoke and restart tests.
- `python tools/run_validation.py --batch-only` — actual batch queue, no UI input.
- `python tests/test_bridge_runtime.py` — host bridge and safe cancellation.
- `python tools/run_validation.py --package-only` — ZIP registration/generation.

Local evidence is under test_output/worker, test_output/blender, test_output/validation,
test_output/batch and test_output/bridge. Generated assets, logs and exports are excluded
from Git and from the installable ZIP. Test runner checks explicit success markers,
because Blender can return exit code zero even when its Python script raises an error.

See TODO.md for unsupported areas, including procedural shader baking, simulation
export, linked-joint editing, semantic single-mesh component selection and other versions.
"""
(root / "docs/testing.md").write_text(report, encoding="utf8")
print(root / "docs/testing.md")
