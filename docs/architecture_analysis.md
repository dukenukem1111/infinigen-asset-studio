# Installation analysis — 2026-10-06

The requested workspace initially contained only an empty Git repository (master,
no commits or local changes). The actual source is in WSL Ubuntu-22.04:
`<existing-infinigen-source>`. It is an editable installation of Infinigen **1.19.0**, at
detached HEAD **01c39c7** (Merge v1.19 — Infinigen Articulated update). Three existing
forest configuration files are untracked; Studio does not change them.

The working runtime is `<existing-worker-python>`, Python
3.11.16, with bpy 4.2.0. Linux Blender 4.2 is in `<existing-linux-blender>`.
Windows Blender 4.2 is in the earlier ChatGPT/Infinigen project's tools directory.
Windows Blender 5.2 is also installed. Use Windows 4.2 for matching node compatibility.

## Verified integration points

* `infinigen/core/placement/factory.py`: AssetFactory(factory_seed, coarse=False),
  spawn_asset(i=0), post_init(), finalize_assets(asset). coarse=True explicitly
  rejects spawn_asset, so it is NOT a preview quality switch.
* `infinigen_examples/generate_asset_parameters.py`: sets factory attributes before
  post_init(), then generates with FixedSeed and calls finalize_assets(asset).
  Studio follows this sequence for attribute schemas.
* `infinigen/core/init.py`: apply_gin_configs config folders, configs, overrides;
  includes base.gin automatically. `gin.enter_interactive_mode()` permits repeated
  imports. Every Studio generation uses a fresh isolated process.
* `infinigen/assets/objects`: factories across seating, tableware, shelves, plants,
  fruits and other categories; `infinigen/assets/sim_objects`: articulated assets.
  Studio scans Python AST and resolves inheritance without importing every asset.
* `infinigen/assets/objects/seating/chairs/chair.py`: scalar sampled attributes,
  enums and booleans; post_init recomputes derived leg/back data.
* `infinigen/assets/objects/tableware/pan.py`: attributes depth, scale, handle,
  thickness; finalize_assets in TablewareFactory assigns procedural materials.
* Some factories accept dictionaries, others ignore create_asset keyword overrides.
  `BoxFactory.create_asset(asset_params=...)` ignores asset_params and samples its
  own dictionary. Studio does not pretend this argument works. Live Geometry Nodes
  modifier inputs are editable after generation instead.
* `infinigen/assets/utils/joints.py`: hinge/sliding/ball joint node groups, Parent,
  Child, Position, Axis, Value, Min, Max, Show Joint sockets. Geometry Nodes preserve
  their own procedural hierarchy, often inside a single mesh object.
* `infinigen/core/sim/kinematic_compiler.py`: compile(obj) builds kinematic graph
  and labels but also sets IDs/default states. It is not a read-only inspector.
  Studio reads group sockets locally without compiling or converting assets.
* `infinigen/core/sim/sim_factory.py`: spawn_simready exports MJCF/USD/URDF through
  native exporters. Simulation export requires factory-specific sampling and is
  reserved for later support rather than represented as ordinary mesh export.
* `infinigen/tools/export.py`: texture baking, scene conversion and FBX/OBJ/USD/
  STL/PLY exporters. export_curr_scene removes hierarchy and modifies the scene,
  and contains old Cycles tile settings. Studio uses available Blender exporters
  on evaluated disposable copies for mesh exports; .blend preserves live nodes.
  Procedural texture baking is not claimed for ordinary mesh export.
* Materials: `infinigen/assets/materials`, composition/material_assignments;
  nodes: core/nodes, surface.add_geomod and butil.modify_mesh.
* Reproducibility: core/util/math.FixedSeed and int_hash(factory_seed, i).
  Studio saves seed, explicit overrides, generator/module and source commit.
* Existing UI helper: tools/blendscript_import_infinigen.py initializes sys.path
  and gin in Blender's scripting window. No artist-facing Studio add-on found.
* Tests: tests/assets, core, integration, sim, tools, solver, datagen. Examples:
  generate_individual_assets.py, generate_asset_parameters.py, asset_parameters.py.

## Architecture decision

A Windows Blender sidebar with a WSL worker reuses the real existing runtime.
Synchronous generation inside Windows Blender would need Linux native dependencies
ported and would block the UI. A subprocess also permits safe cancellation without
threaded bpy calls. Worker requests/results and .blend files are in a shared Windows
directory. No changes to Infinigen core or the existing forest .blend are required.

Discovery identifies candidates, not guaranteed compatibility. Import/generation
errors remain visible per generator. Attribute controls are inferred conservatively
from literal constructor values and literal sampling ranges; cross-dependent and
untyped procedural values require explicit schemas. Advanced mode identifies these
as inferred controls. Unlinked Geometry Nodes sockets use native Blender widgets.
