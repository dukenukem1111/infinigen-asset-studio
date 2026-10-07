# Verification — 2026-10-06

Tests used Infinigen 1.19.0 at commit
`01c39c7f7adcf7363ccbcc57c64410c69f4a4e7c`, Python 3.11.16 and bpy 4.2.0
in WSL Ubuntu 22.04, and Windows Blender 4.2.0 as the interactive host.
The catalog contains 276 AST-discovered generator candidates. Four representative
families are verified; the full catalog is not certified.

## Passed workflows

- Add-on registration/unregistration and real native sidebar rendering.
- Source discovery, generator selection, schema controls, parameter locks/randomization.
- Chair generation, same-seed geometry reproduction, seed-only and parameter-only changes.
- Pan, articulated box and articulated cabinet generation; CPU-rendered thumbnails.
- Box joints change evaluated geometry, reset restores it, a normalized slider moves
  an active joint, and saved edited sockets restore the pose. Box: 16 native joint
  groups; cabinet: 2. Some box joint groups belong to inactive generator branches.
- Preset save/load, native project save/reopen, favorite library save/open/toggle.
- Two sequential pan variations through the actual UI generation queue with simulated
  TIMER events in background Blender, then thumbnail selection and preview visibility.
- Non-destructive LOD/collision copies; original geometry remains unchanged.
- .blend, GLB, FBX, OBJ and USD export; temporary export copies are removed.
- GLB reimport and a separate Blender process reopening a saved Studio session or library entry.
- Invalid parameter handling with a categorized error and technical details.
- Windows-to-WSL bridge generation and process-group cancellation.
- Cancellation before worker startup is protected by a persisted cancellation marker.
- The installable ZIP registers and generates from an isolated extracted package,
  without installing the add-on through Preferences or saving the user's Blender preferences.
- The live sidebar Generate button produced a chair and preview thumbnail. Mouse and keyboard
  testing stopped when the user pressed Escape; final queue verification used background
  tests so ordinary computer use remained available.

## Approximate measured performance

| Asset / seed | Native generation | Append + inspect + hash | Peak worker RSS | Triangles | Native joint groups |
|---|---:|---:|---:|---:|---:|
| chair_42 | 0.388 s | 0.701 s | 581.2 MB | 220,952 | 0 |
| pan_12 | 0.425 s | 0.389 s | 670.3 MB | 127,110 | 0 |
| box_8 | 3.807 s | 0.948 s | 619.7 MB | 1,028 | 16 |
| cabinet_7 | 0.549 s | 0.205 s | 548.7 MB | 4,484 | 2 |

Generation time covers native factory construction, geometry and materials, not process
startup, source imports, thumbnail rendering or host import. Complete single-asset
jobs in this run took roughly 6–10 seconds, including those steps. This timing applies
to individual chairs, pans, boxes and cabinets; room and world timings are reported
separately below. Append timings include statistics and reproducibility hashing;
they are not pure UI frame timings. Peak RSS measures the worker process alone;
it excludes combined Blender, WSL and GPU usage. Results are representative samples,
not a performance guarantee.

Chair geometry is already heavily subdivided by the native factory. Reducing remaining
modifiers cannot remove subdivision applied during construction. LOD copies address
export complexity; the Draft switch does not accelerate that construction.

## Test commands and evidence

- `python -m unittest discover -s tests -p test_core.py` — four pure-Python tests.
- Installed Infinigen Python: `tests/run_worker_tests.py <existing-infinigen-source>`.
- `python tools/run_validation.py` — background Blender smoke and restart tests.
- `python tools/run_validation.py --batch-only` — actual batch queue, no UI input.
- `python tests/bridge_runtime.py` — host bridge and safe cancellation.
- `python tools/run_validation.py --package-only` — ZIP registration and generation.

Local evidence is under `test_output/worker`, `test_output/blender`, `test_output/validation`,
`test_output/batch` and `test_output/bridge`. Generated assets, logs and exports are excluded
from Git and from the installable ZIP. The test runner checks explicit success markers,
because Blender can return exit code zero even when its Python script raises an error.

See [TODO.md](../TODO.md) for unsupported areas, including procedural shader baking, simulation
export, linked-joint editing, semantic single-mesh component selection and other versions.


## 0.2.0 distribution and scene validation — 7 October 2026

Installation of the external source and environment began in an empty, separate
Linux user data directory managed by the installer. The host machine already had
WSL2 Ubuntu 22.04, Python 3, g++ and make. This is a fresh dependency test, not a
claim that a new Windows machine can run Linux terrain without first installing
WSL prerequisites.
The new isolated environment reports Python 3.11.11, bpy 4.2.0, Infinigen 1.19.0,
commit 01c39c7f7adcf7363ccbcc57c64410c69f4a4e7c and 276 candidate factories.
Official source and submodule archives and the Python bootstrap passed the recorded
SHA-256 checks. No existing environment or interactive Blender Python installation was modified.

| Check | Result |
| --- | --- |
| Fresh archive-based managed install + native CPU terrain | Passed |
| Factory, indoor and nature imports + Pan .blend smoke test (seed 212) | Passed |
| Managed Chair generation: seed 42, width 0.4; seed 43, width 0.5 | Passed; metadata matches requests |
| Managed Box native joint metadata (seed 8) | Passed |
| Complete furnished Living Room, seed 0, Draft, CPU | Passed: 142 objects, 120 meshes, 335 materials, 2 cameras; 88.91 s including worker startup |
| Complete Desert, seed 0, coarse + populate + fine terrain, CPU | Passed: 786 objects, 782 meshes, 43 materials, 2 cameras; 318.58 s on this hardware |
| Windows Blender opens both Linux-generated packed .blend outputs | Passed |
| Native full-scene copy save + overwrite protection | Passed for Room and World |
| Full-room native glTF export + loss acknowledgement | Passed |
| Selected original mesh LOD/collision copies | Passed for both scenes; source data/modifiers/transforms preserved |
| Real scene cancellation and WSL process-group exit | Passed; no surviving worker group |
| Automatic detection and validated activation of an existing installation | Passed through the native Setup operator |
| Invalid source folder leaves active configuration intact | Passed |
| External installation repair is refused | Passed |
| Self Test, scene JSON round-trip, marking a history entry as a favorite | Passed through native operators |
| Disabling and re-enabling the add-on preserves the registry and an unsaved cube | Passed |
| Actual mismatching source commit is detected/rejected | Passed |
| Remove gin-config from the owned test environment | Unhealthy runtime detected as expected |
| Repair source, dependencies and native compilation + Pan generation (seed 212) | Passed |
| Owned dependency removal fixture preserves outputs/downloads/logs | Passed |
| Pure tests | 10 passed |
| Existing asset smoke/restart/batch regression | Passed |
| Extracted release ZIP with real generated asset | Passed |
| Release structure / version / no bundled machine data | Passed |

Native pipeline timings are measurements of these requests, not predictions for
other hardware or presets. Mesh counts are datablock counts and do not claim
fully realized scatter-instance counts. Draft scene previews in `docs/images` are
real rendered outputs; the room preview uses a temporary fill light, without
changing its saved generated scene.

The expected invalid-path, overwrite and acknowledgement tests deliberately log
errors while verifying safe refusal. A damaged dependency can return a diagnostic
result with `healthy=false` rather than raising an exception; activation must reject that report.

Run pure tests with `python -m unittest discover -s tests -p "test_*.py"`.
Real engine tests are opt-in and require an ignored local `runtime/development.json` file:
`tools/run_validation.py` (smoke/restart), `--batch-only`, `--package-only`,
`--setup-only`; `tests/bridge_cancel_scene.py`; and
`tests/managed_end_to_end.py --managed-root <owned-test-root> --distribution <WSL-name>`
with explicit `--install`, `--assets`, `--room`, `--world` or `--repair` flags.
Only use the repair test against an owned disposable test environment: it intentionally
uninstalls gin-config before testing recovery. Real logs/results and generated
assets remain under the ignored `test_output` directory. No generated scene or installed engine
is committed or included in the release ZIP.

Not yet validated: managed macOS/native Windows installation, every factory or
environment config, newer host/worker Blender releases, fluid simulation,
annotation pipelines, arbitrary scene solver bindings, and CUDA/OptiX scene renders.
Device availability is reported, but only CPU scene rendering was exercised here.
