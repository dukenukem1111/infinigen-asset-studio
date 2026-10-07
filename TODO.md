# Remaining work beyond the functional MVP

- Verify more of the discovered generator candidates and define version-specific
  capability adapters. Discovery does not guarantee that every candidate can be imported or generated.
- Add explicit dictionary/distribution schemas, vectors/colors/files and richer
  constructor dependency handling. Current factory overrides support float/int/bool/enum;
  live node widgets handle native vectors/colors/strings.
- Add texture baking through a validated Infinigen exporter adapter. The existing upstream
  exporter changes the hierarchy and references older Cycles settings; do not silently use it.
- Add URDF/MJCF/semantic USD export via native simulation adapters with tested sampling
  and clear engine compatibility. Static mesh export is explicitly labeled.
- Resolve linked joint controls to editable ancestor sockets, add semantic component
  selection inside single-mesh node graphs, conversion between joint types and articulation playback.
- Add independent shape/material/detail seed domains only where the generator can support
  them. Native joint/modifier edits are preserved; factory partial regeneration is not generic.
- Add rerendered thumbnails for edited materials/poses, generator preview thumbnails,
  side-by-side comparison and bulk library management. Generation history now exists.
- Add texture resolution/baking, UV validation/unwrapping, robust engine pivot/naming
  profiles and collider splitting by articulated semantic parts.
- Add thumbnail and library lifecycle cleanup with user confirmation; jobs are retained for their logs.
- Detect and offer validated GPU/CUDA thumbnail acceleration. CPU generation and rendering work
  without assuming a particular GPU, and Blender's own material viewport uses its devices.
- Test macOS and local backends, and Blender versions beyond the installed 4.2 runtime.
- Metadata contains native transforms; .blend files are authoritative for arbitrary scene edits,
  materials, added or deleted objects and derived meshes. JSON reconstruction currently
  reapplies supported factory controls and edited native sockets/joints.

## Scene and distribution follow-ups

- Add managed setup for macOS and native Windows asset generation; full terrain generation on Windows currently uses WSL2.
- Add controls for native single-room floor plan dimensions and supported styles, beyond wall height and room type restrictions.
- Add support for partial scene regeneration through the native solver.
- Add shader baking and verify full-scene Geometry Nodes instance conversion for each export format.
- Add an official Blender Extensions manifest and distribution, beyond the working legacy installable ZIP.
- Test more engine versions, room and environment configs, and GPU render modes with real generation jobs.
