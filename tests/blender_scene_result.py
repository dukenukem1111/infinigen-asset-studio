"""Open real Linux-generated scenes in Windows Blender and verify safe scene tools."""
import json
import os
import sys
import time
from pathlib import Path
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("ASSET_STUDIO_DATA_DIR", str(ROOT / "runtime/studio_data"))
sys.path.insert(0, str(ROOT))
addon_utils.enable("infinigen_asset_studio", default_set=True, persistent=True)
from infinigen_asset_studio import addon
mode = bpy.context.scene.get("studio_mode")
assert mode in {"ROOM", "WORLD"}
assert bpy.context.scene.get("studio_seed") == 0
assert len(bpy.data.meshes) > 10
assert any(obj.type == "CAMERA" for obj in bpy.data.objects)
if mode == "ROOM":
    assert any("Sofa" in obj.name or "Table" in obj.name or "Chair" in obj.name for obj in bpy.data.objects), "Furnished output must contain native furniture"
state = bpy.context.scene.studio
state.creation_mode = mode
output = ROOT / "test_output/scene_open" / (mode + "_" + str(time.time_ns()))
output.mkdir(parents=True)
original_count = len(bpy.data.objects)
original_meshes = {obj.name: (obj.data.as_pointer(), len(obj.modifiers), tuple(obj.matrix_world)) for obj in bpy.context.scene.objects if obj.type == "MESH"}
assert bpy.ops.studio.scene_export(filepath=str(output / "native"), format="BLEND") == {"FINISHED"}, state.details
assert (output / "native.blend").is_file()
assert bpy.ops.studio.scene_export(filepath=str(output / "native"), format="BLEND") == {"CANCELLED"}
assert "new filename" in state.error
# Explicit selection makes preparation bounded even for huge worlds.
for obj in bpy.context.selected_objects:
    obj.select_set(False)
candidate = next(obj for obj in bpy.context.scene.objects if obj.type == "MESH" and len(obj.data.vertices) >= 4 and obj.visible_get())
candidate.hide_set(False)
candidate.hide_viewport = False
candidate.select_set(True)
bpy.context.view_layer.objects.active = candidate
assert bpy.ops.studio.scene_tools(action="lod") == {"FINISHED"}, state.details
assert bpy.ops.studio.scene_tools(action="collision") == {"FINISHED"}, state.details
assert len(bpy.data.objects) > original_count
assert all((bpy.data.objects[name].data.as_pointer(), len(bpy.data.objects[name].modifiers), tuple(bpy.data.objects[name].matrix_world)) == value for name, value in original_meshes.items())
for obj in list(bpy.data.objects):
    if obj.get("studio_derived"):
        bpy.data.objects.remove(obj, do_unlink=True)
assert bpy.ops.studio.scene_export(filepath=str(output / "static"), format="GLB", acknowledge=False) == {"CANCELLED"}
assert "Acknowledge" in state.error
# Full room glTF proves the scene exporter uses the real complete output.
if mode == "ROOM":
    assert bpy.ops.studio.scene_export(filepath=str(output / "static"), format="GLB", acknowledge=True) == {"FINISHED"}, state.details
    assert (output / "static.glb").stat().st_size > 1000
print("STUDIO_SCENE_OPEN_TEST_PASSED", mode, flush=True)
