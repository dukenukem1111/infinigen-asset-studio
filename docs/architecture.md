# Architecture

`infinigen_asset_studio` is a Blender add-on. `core.py` owns versioned metadata,
validation and deterministic randomization. `discovery.py` owns AST catalog/schema
inspection. `bridge.py` starts and polls subprocesses. `worker.py` runs in the
installed Infinigen environment. `scene_tools.py` owns local evaluated geometry,
joint/socket inspection, materials, collision, LOD and export. `addon.py` owns RNA,
operators and panels. `installation.py` owns the persistent external configuration;
source and runtime fields in Preferences are staging inputs until validation activates them. `setup_worker.py`
installs a pinned isolated engine. `scenes.py` wraps native indoor/nature tasks,
`scene_task.py` reports their real stages, and `setup_ui.py` / `scene_ui.py` add
setup, history, scene export and selected-mesh preparation without rewriting asset code.

Each operation gets a unique job folder containing `request.json`, `status.json`,
`result.json` and `worker.log`. Status and result writes use atomic replacement. bpy is
used only on the main thread of each process. The host uses a modal timer to poll
the worker and keeps existing assets intact. Cancel terminates the WSL worker by
its recorded PID; no partially generated object enters the host scene.

Successful assets are appended as separate named collections. Each collection
stores reconstruction JSON and stays in the scene as a variation. Saving a project
writes a .blend file plus readable JSON; saved library entries contain a .blend file,
a thumbnail, source version, parameters, tags and favorite state. The metadata schema is versioned.
Unknown future versions are rejected. JSON writes are atomic.

Exports use temporary evaluated mesh copies and delete them in `finally` blocks.
Mesh exports retain a static posed result, not Infinigen articulation; the export
dialog explicitly requires acknowledgement. Native .blend files retain procedural nodes,
hierarchy and metadata. Engine presets configure axes/units supported by the format.
LOD and collision objects are derived copies tagged separately from original assets.
