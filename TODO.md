# Remaining work beyond the functional MVP

- Verify more of the discovered generator candidates and define version-specific
  capability adapters. Discovery is not a guarantee every candidate imports/generates.
- Add explicit dictionary/distribution schemas, vectors/colors/files and richer
  constructor dependency handling. Current factory overrides support float/int/bool/enum;
  live node widgets handle native vectors/colors/strings.
- Add texture baking through a validated Infinigen exporter adapter. Existing upstream
  exporter mutates hierarchy and references older Cycles settings; do not silently use it.
- Add URDF/MJCF/semantic USD export via native simulation adapters with tested sampling
  and clear engine compatibility. Static mesh export is deliberately labelled.
- Resolve linked joint controls to editable ancestor sockets, add semantic component
  selection inside single-mesh node graphs, joint type conversion and articulation playback.
- Add independent shape/material/detail seed domains only where the generator can support
  them. Native joint/modifier edits are preserved; factory partial regeneration is not generic.
- Add rerendered thumbnails for edited materials/poses, generator preview thumbnails,
  side-by-side comparison and bulk library management. Generation history now exists.
- Add texture resolution/baking, UV validation/unwrapping, robust engine pivot/naming
  profiles and collider splitting by articulated semantic parts.
- Add thumbnail/library lifecycle cleanup with user confirmation; jobs are retained for logs.
- Detect/offer validated GPU/CUDA thumbnail acceleration. CPU generation/rendering works
  without assuming a particular GPU, and Blender's own material viewport uses its devices.
- Test macOS/local backends and Blender versions beyond the installed 4.2 runtime.
- Metadata contains native transforms; .blend is authoritative for arbitrary scene edits,
  materials, added/deleted objects and derived meshes. JSON reconstruction currently
  reapplies supported factory controls and edited native sockets/joints.

## Scene and distribution follow-ups

- Managed setup for macOS and native Windows assets; Windows full terrain currently uses WSL2.
- Native single-room floor plan dimensions and supported style schemas, beyond height/type restriction.
- Generic partial scene solver regeneration remains unsupported.
- Shader baking and verified full-scene Geometry Nodes instance conversion per export format.
- Official Blender Extensions manifest/distribution, beyond the working legacy installable ZIP.
- More engine versions, room/environment configs and GPU render modes need separate real tests.
