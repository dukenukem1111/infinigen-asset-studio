"""Run in Windows Blender 4.2 --background --factory-startup --python this_file."""
import hashlib
import json
import sys
import time
from pathlib import Path
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parent.parent
import os
os.environ.setdefault("ASSET_STUDIO_DATA_DIR", str(ROOT / "runtime/studio_data"))
sys.path.insert(0, str(ROOT))
addon_utils.enable("infinigen_asset_studio", default_set=True, persistent=True)
from infinigen_asset_studio import addon, scene_tools as tools
from infinigen_asset_studio.core import write_json

OUTPUT = ROOT / "test_output/blender" / ("run_" + str(time.time_ns()))
OUTPUT.mkdir(parents=True, exist_ok=True)
prefs = bpy.context.preferences.addons["infinigen_asset_studio"].preferences
prefs.workspace = str(OUTPUT / "studio")
state = bpy.context.scene.studio
catalog = json.loads((ROOT / "test_output/worker/discover/result.json").read_text())
addon.load_catalogue(bpy.context, catalog)
assert len(state.assets) > 100
chair_index = next(i for i, item in enumerate(state.assets) if item.generator.endswith("chairs.chair.ChairFactory"))
state.asset_index = chair_index
assert any(p.name == "width" for p in state.parameters)
state.parameters["width"].enabled = True
state.parameters["width"].number = 0.42
state.parameters["width"].locked = True
assert bpy.ops.studio.action(action="RANDOMIZE") == {"FINISHED"}
assert abs(state.parameters["width"].number - 0.42) < 1e-6
assert bpy.ops.studio.action(action="NEXT") == {"FINISHED"}
assert state.seed == 43


def fingerprint(collection, include_derived=True):
    digest = hashlib.sha256()
    graph = bpy.context.evaluated_depsgraph_get()
    for obj in collection.all_objects:
        if obj.type != "MESH":
            continue
        if obj.get("studio_derived") and not include_derived:
            continue
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        try:
            for v in mesh.vertices:
                digest.update(str(tuple(round(c, 6) for c in v.co)).encode())
            # Blender/BMesh face storage order is not part of seed reproducibility.
            topology = []
            for poly in mesh.polygons:
                vertices = tuple(poly.vertices)
                topology.append(min(vertices[i:] + vertices[:i] for i in range(len(vertices))))
            for vertices in sorted(topology):
                digest.update(str(vertices).encode())
        finally:
            evaluated.to_mesh_clear()
    return digest.hexdigest()


collections = {}
summary = {"blender": bpy.app.version_string, "catalogue_count": len(state.assets), "tests": {}, "assets": {}}
for name in ("chair_42", "chair_42_repeat", "chair_43", "chair_seed_only", "chair_width_only", "pan_12", "box_8", "cabinet_7"):
    file = ROOT / "test_output/worker" / name / "asset.blend"
    if not file.exists():
        continue
    start = time.perf_counter()
    collection = tools.append_asset(file)
    tools.select_collection(bpy.context, collection)
    collections[name] = collection
    summary["assets"][name] = {"fingerprint": fingerprint(collection), "statistics": tools.statistics(collection), "joints": len(tools.joints(collection)), "append_seconds": round(time.perf_counter() - start, 3)}
    assert summary["assets"][name]["statistics"]["triangles"] > 0
    print("ASSET", name, summary["assets"][name], flush=True)
assert summary["assets"]["chair_42"]["fingerprint"] == summary["assets"]["chair_42_repeat"]["fingerprint"], "Same seed/parameters must reproduce geometry"
for name in ("chair_seed_only", "chair_width_only"):
    if name in collections:
        assert summary["assets"][name]["fingerprint"] != summary["assets"]["chair_42"]["fingerprint"]
summary["tests"]["determinism"] = True

chair = collections["chair_42"]
tools.select_collection(bpy.context, chair)
addon.load_metadata(bpy.context, json.loads(chair["studio_metadata"]))
assert bpy.ops.studio.save(filepath=str(OUTPUT / "preset.json"), project=False) == {"FINISHED"}
state.seed = 99
assert bpy.ops.studio.load(filepath=str(OUTPUT / "preset.json")) == {"FINISHED"}
assert state.seed == 42
assert bpy.ops.studio.save(filepath=str(OUTPUT / "project.json"), project=True) == {"FINISHED"}
assert bpy.ops.studio.load(filepath=str(OUTPUT / "project.json")) == {"FINISHED"}
assert bpy.ops.studio.action(action="SAVE_LIBRARY") == {"FINISHED"}
assert len(state.library) == 1
assert bpy.ops.studio.action(action="LIBRARY_OPEN") == {"FINISHED"}
assert bpy.ops.studio.action(action="LIBRARY_FAVORITE") == {"FINISHED"}
summary["tests"]["presets_project_library"] = True

box = collections["box_8"]
tools.select_collection(bpy.context, box)
joint_list = tools.joints(box)
assert joint_list, "The articulated box should retain native joint groups"
before = fingerprint(box)
for _, _, node in joint_list:
    node["studio_rest"] = node.inputs["Value"].default_value
changed = tools.pose(box, "OPEN")
bpy.context.view_layer.update()
after = fingerprint(box)
assert changed > 0, "At least one joint must be controllable"
assert before != after, "Opening joints must visibly alter geometry"
edits = tools.snapshot(box)["native_edits"]
tools.pose(box, "RESET")
bpy.context.view_layer.update()
assert fingerprint(box) == before, "Reset must restore the original pose"
tools.restore_edits(box, edits)
assert fingerprint(box) == after, "Saved socket edits must reproduce the posed geometry"
tools.pose(box, "RESET")
bpy.context.view_layer.update()
slider_changed = False
for i, (_, _, node) in enumerate(joint_list):
    if node.inputs["Value"].is_linked or node.inputs["Min"].default_value == node.inputs["Max"].default_value:
        continue
    state.joint_index = i
    state.joint_position = 0.7
    bpy.context.view_layer.update()
    slider_changed = fingerprint(box) != before
    tools.pose(box, "RESET")
    bpy.context.view_layer.update()
    if slider_changed:
        break
assert slider_changed, "An active native joint must move through the normalized slider"
summary["tests"]["joint_pose_and_reset"] = True
summary["joint_changes"] = changed

tools.select_collection(bpy.context, chair)
before = fingerprint(chair)
tools.make_lods(chair)
assert len([o for o in chair.all_objects if o.get("studio_derived") == "LOD"]) >= 3
tools.make_collision(chair, "HULL")
assert any(o.get("studio_derived") == "COLLISION" for o in chair.all_objects)
state.statistics = json.dumps(tools.statistics(chair))
for fmt in ("GLB", "FBX", "OBJ", "USD", "BLEND"):
    if fmt not in [v[0] for v in addon.EXPORT_FORMATS]:
        summary["tests"]["export_" + fmt] = "Unavailable in this Blender installation"
        continue
    path = OUTPUT / ("export_" + fmt.lower())
    assert bpy.ops.studio.export(filepath=str(path), format=fmt, preset="GODOT" if fmt == "GLB" else "GENERIC", acknowledge=True) == {"FINISHED"}
    summary["tests"]["export_" + fmt] = True
assert fingerprint(chair) != before  # Derived copies are included in the fingerprint.
assert fingerprint(chair, include_derived=False) == before, "LOD, collision and export must preserve original geometry"
assert not any(c.name.startswith("Studio export temporary") for c in bpy.data.collections)
summary["tests"]["lod_collision_export_cleanup"] = True

# Verify mesh export can be reimported without touching originals.
objects_before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(OUTPUT / "export_glb.glb"))
imported = set(bpy.data.objects) - objects_before
assert any(o.type == "MESH" for o in imported)
summary["tests"]["reimport_glb"] = True

# Save whole-session state for a separate restart process.
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "session.blend"), check_existing=False)
write_json(OUTPUT / "summary.json", summary)
write_json(ROOT / "test_output/blender/latest.json", {"output": str(OUTPUT)})
print("STUDIO_SMOKE_TESTS_PASSED", flush=True)
