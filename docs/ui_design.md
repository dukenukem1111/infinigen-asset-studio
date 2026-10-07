# Native sidebar design

Viewport > N sidebar > Asset Studio. Blender's existing dark theme, native controls,
material viewport and Outliner provide the visual system and interactive 3D preview.

1. Connection: source/runtime Preferences and Discover. Status and cancel appear
   prominently while jobs run.
2. Asset Browser: searchable, category filtered list with articulated icons and
   favorite filter. Candidate/module details are available in Advanced mode.
3. Generation: seed, previous/next/copy/random, quality, Generate/Update. Existing
   variations survive updates. Controls never automatically start generation.
4. Shape: conservative inferred factory controls, grouped basic/advanced. An
   override checkbox preserves native sampling until selected. Locks affect
   Studio randomization. After generation native modifier sockets are editable.
5. Articulation: recursive node joint list, native axis/origin/limits, test slider,
   reset/open/close/random; linked values are explicitly read-only. Show Joint
   enables Infinigen's native axis visualization where its socket is unlinked.
6. Materials: active material's unlinked Principled color/roughness/metallic inputs;
   linked procedural inputs remain in Shader Editor. Optional independent material
   preset creates a new material without modifying shared source materials.
7. Game Ready: evaluated polygon counts, units/scale, ground pivot, non-destructive
   LODs and per-component convex hulls/bounding box collision.
8. Library: named variations, rendered thumbnails, favorites/tags/search, open,
   export and presets/project save/load. Technical details are collapsed.

Draft/Preview limit viewport subdivision on generated output only. Production
keeps native modifiers. These settings cannot accelerate geometry a factory already
applies during construction. Unsupported baking/semantic component selection/
simulation formats are documented, not presented as working buttons.

## 0.2.0 setup and scene modes

The top selector switches Asset, Room and World. Setup & Diagnostics appears
for every mode and explains the Windows WSL requirement. A fresh install exposes
Find Existing and Install Automatically; discovered source/version/capability
reports replace assumptions about personal paths. Room/World use a separate Scene
Generation panel, with seeds, quality, verified controls, preset save/load and native
config search in Advanced mode. Native stage names, Cancel and logs remain visible.
Generated scenes open separately; Scene Export & Preparation appears inside them.
History supports regeneration, open/folder/favorite and saving each entry as a preset.
Unsupported partial regeneration and unmapped controls are stated plainly.
