# Baseline audit — 7 October 2026

This audit records the 0.1.0 baseline before the 0.2.0 setup and scene changes.
See [the architecture overview](architecture.md) for the current module layout.

The working 0.1.0 add-on targeted Infinigen **1.19.0** at detached commit
`01c39c7f7adcf7363ccbcc57c64410c69f4a4e7c`, Python 3.11 and bpy 4.2.0.
The interactive host tested here was Blender 4.2.0 on Windows; generation ran
in an existing Ubuntu 22.04 WSL installation. No upstream modifications were
required. The upstream checkout had three local nature configs that were not
part of our supported release. This repository initially had no commits or remote.

## Existing modules and contracts

* `core.py`: atomic JSON, metadata schema, validated controls, seeded randomization.
* `discovery.py`: AST inspection of factory classes; does not execute source.
* `schemas/`: small, original mappings for verified Chair/Pan controls.
* `bridge.py`: independent jobs, shared request/status/result files, process polling,
  cancellation marker and WSL process-group termination.
* `worker.py`: source initialization, gin base config, FixedSeed, factory
  `spawn_asset` / `finalize_assets`, .blend output, isolated CPU thumbnails.
* `scene_tools.py`: append collections, live sockets, native joints, snapshots,
  disposable evaluated exports, derived collision and LOD copies.
* `addon.py`: native RNA and modal operators, generator library, variation browser,
  articulation, materials, presets and five host-dependent export formats.
* Launchers and `tools/`: local developer launcher, archive builder, validation.
* `tests/`: real workers and Blender smoke/restart/batch/package checks plus pure
  validation and discovery tests. Generated test assets remain ignored.

## Fragile assumptions found

In the baseline, `machine.json` contained personal absolute Windows/WSL source,
environment and Blender executable paths and was included by the old archive builder.
Preferences copied those defaults, while launch and test tools read the same file separately.
There was no first-run setup or installation validation. Worker version reporting
assumed Git was available, even when the source could be an archive. There was no scene
adapter or dependency capability report. Only factory generation was implemented.
Developer tools assumed Git, WSL, source paths and an existing environment were available.
These baseline issues were addressed in 0.2.0; personal configuration is no longer bundled.

## Verified upstream interfaces

Indoor: `infinigen_examples.generate_indoors.main(args)` and its CLI. `coarse`
already solves architecture and populates real furniture. Native selectors include
`restrict_solving.restrict_parent_rooms`, `solve_max_rooms`, solver step counts,
`RoomConstants.wall_params.wall_height`, overhead camera and decoration stages.
Furniture constraints explicitly support Bedroom, LivingRoom, Kitchen, Bathroom
and DiningRoom; Office/Hallway furniture presets must not be promised.

Nature: `infinigen_examples.generate_nature.main(args)` and its CLI. A complete output
requires `coarse` followed by `populate` and `fine_terrain`, as in the pinned HelloWorld
documentation. Scene types and performance presets are discoverable gin files.
Full tasks require **exactly bpy 4.2.0**, not merely any Blender 4.x version.

## Dependencies and risks

The upstream Python requirement is `==3.11.*`; `bpy==4.2.0`, `numpy<2`, gin-config,
scipy, shapely, scikit-image, scikit-learn, OpenEXR and collision libraries are
required. Nature adds landlab 2.6.0 and pyrender, CPU C++ terrain libraries,
Cython marching cubes, GLM headers and OcMesher. Archive downloads omit Git
submodules: their commits must be downloaded explicitly. Upstream's default
setup hook calls Git to initialize every submodule; minimal pip installation
followed by explicit native terrain builds avoids that assumption.

The pinned Installation.md marks native Windows terrain as unsupported and WSL as
experimental. Linux CPU generation does not require CUDA. CUDA driver presence
does not imply working CUDA terrain or Cycles devices. Scene reproducibility has
a limitation documented upstream; record the exact configs, overrides and seed.
Existing asset behavior and saved metadata must remain compatible.

The upstream root license is BSD-3-Clause, copyright Princeton University 2023;
`infinigen_gpl` is GPL version 3. Preserve licenses in downloaded source. Our
release must contain only original integration code, not upstream installations.
