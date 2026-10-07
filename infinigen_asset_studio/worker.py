"""Isolated Infinigen worker. Launched by the host with a shared job directory."""
import importlib
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

# Supports direct script invocation without importing Blender UI code.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infinigen_asset_studio.core import SCHEMA_VERSION, validate_parameters, write_json
from infinigen_asset_studio.discovery import discover


def status(folder, stage, progress):
    write_json(folder / "status.json", {"pid": os.getpid(), "stage": stage, "progress": progress})


def version_info(source):
    def git(*args):
        import shutil
        record = source / ".studio-source.json"
        if not shutil.which("git") or not (source / ".git").exists():
            return json.loads(record.read_text())["commit"] if args == ("rev-parse", "HEAD") and record.is_file() else "archive"
        p = subprocess.run(["git", "-C", str(source), *args], capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else "unknown"
    import bpy
    import infinigen
    return {"infinigen": infinigen.__version__, "commit": git("rev-parse", "HEAD"),
            "branch": git("branch", "--show-current") or "detached HEAD", "blender": bpy.app.version_string,
            "python": sys.version.split()[0], "source": str(source)}


def initialize(source):
    os.chdir(source)
    sys.path.insert(0, str(source))
    import gin
    gin.clear_config()
    gin.enter_interactive_mode()
    from infinigen.core import init
    init.apply_gin_configs(["infinigen_examples/configs_indoor", "infinigen_examples/configs_nature"], skip_unknown=True)
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)


def thumbnail(folder, collection):
    """Small CPU Cycles render; avoids headless WSL Workbench/OpenGL context crashes."""
    import bpy
    from mathutils import Vector
    graph = bpy.context.evaluated_depsgraph_get()
    points = [obj.matrix_world @ Vector(c) for obj in collection.all_objects if obj.type == "MESH"
              for c in obj.evaluated_get(graph).bound_box]
    if not points:
        return False
    low = Vector(tuple(min(v[i] for v in points) for i in range(3)))
    high = Vector(tuple(max(v[i] for v in points) for i in range(3)))
    center, span = (low + high) * 0.5, max((high - low).length, 0.1)
    camera_data = bpy.data.cameras.new("Studio thumbnail")
    camera = bpy.data.objects.new("Studio thumbnail", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = center + Vector((1.2, -1.6, 1.1)).normalized() * span * 1.6
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = span * 1.15
    scene = bpy.context.scene
    scene.camera = camera
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 8
    scene.cycles.use_denoising = False
    scene.render.resolution_x = scene.render.resolution_y = 256
    scene.render.resolution_percentage = 100
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.background_type = "WORLD"
    scene.world = scene.world or bpy.data.worlds.new("Studio World")
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.65, 0.65, 0.65, 1)
    background.inputs["Strength"].default_value = 0.8
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(folder / "thumbnail.png")
    try:
        bpy.ops.render.render(write_still=True)
        return True
    finally:
        bpy.data.objects.remove(camera, do_unlink=True)
        bpy.data.cameras.remove(camera_data)


def generate(folder, request, source, catalogue):
    import bpy
    from infinigen.core.util.math import FixedSeed
    from infinigen_asset_studio.scene_tools import statistics, restore_edits, snapshot
    item = next((v for v in catalogue if v["id"] == request["generator"]), None)
    if item is None:
        raise LookupError("The selected generator no longer exists in this source installation. Discover again.")
    seed = request["seed"]
    if type(seed) is not int or not 0 <= seed <= 2147483646:
        raise ValueError("Seed must be an integer between 0 and 2147483646.")
    values = validate_parameters(item["parameters"], request.get("parameters", {}))
    status(folder, "Importing " + item["name"], 0.12)
    cls = getattr(importlib.import_module(item["module"]), item["name"])
    start = time.perf_counter()
    status(folder, "Initializing generator and procedural materials", 0.2)
    with FixedSeed(seed):
        factory = cls(seed)
        for name, value in values.items():
            if not hasattr(factory, name):
                raise ValueError(f"The installed factory does not expose {name}.")
            setattr(factory, name, value)
        if values:
            factory.post_init()
    status(folder, "Building geometry (native generator)", 0.35)
    with FixedSeed(seed):
        asset = factory.spawn_asset(0)
    if isinstance(asset, tuple):
        raise TypeError("This generator returns a specialized export payload and needs a dedicated adapter.")
    status(folder, "Finalizing materials and components", 0.65)
    with FixedSeed(seed):
        factory.finalize_assets(asset)
    collection = bpy.data.collections.new("Studio Asset")
    bpy.context.scene.collection.children.link(collection)
    # Capture all native objects: generators can produce unparented supporting objects.
    for obj in list(bpy.context.scene.objects):
        collection.objects.link(obj)
        for old in list(obj.users_collection):
            if old != collection:
                old.objects.unlink(obj)
    quality = request.get("quality", "PREVIEW")
    for obj in collection.all_objects:
        for mod in obj.modifiers:
            if mod.type == "SUBSURF" and quality != "PRODUCTION":
                mod.levels = min(mod.levels, 0 if quality == "DRAFT" else 1)
    metadata = {"schema_version": SCHEMA_VERSION, "generator": item["id"], "seed": seed,
                "parameters": values, "quality": quality, "source_version": version_info(source),
                "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "generation_seconds": round(time.perf_counter() - start, 3), "name": item["name"] + " " + str(seed)}
    from infinigen_asset_studio.installation import MANIFEST
    metadata.update(studio_version=MANIFEST["studio_version"], mode="ASSET")
    metadata["statistics"] = statistics(collection)
    try:
        import resource
        metadata["peak_worker_memory_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except ImportError:
        pass
    collection["studio_metadata"] = json.dumps(metadata)
    metadata = snapshot(collection)
    metadata["generation_baseline"] = {"native_inputs": metadata["native_inputs"], "joints": metadata["joints"]}
    collection["studio_metadata"] = json.dumps(metadata)
    if request.get("native_edits"):
        restore_edits(collection, request["native_edits"])
        metadata = snapshot(collection)
        collection["studio_metadata"] = json.dumps(metadata)
    status(folder, "Saving procedural asset", 0.8)
    bpy.ops.wm.save_as_mainfile(filepath=str(folder / "asset.blend"), check_existing=False)
    write_json(folder / "metadata.json", metadata)
    warning = ""
    status(folder, "Rendering thumbnail", 0.9)
    try:
        # Native renderer failures cannot be caught as Python exceptions. Isolate them.
        child = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--thumbnail", str(folder)], timeout=60)
        if child.returncode != 0 or not (folder / "thumbnail.png").is_file():
            warning = "Asset generated; thumbnail rendering failed. The native asset is available."
    except Exception as error:
        warning = "Asset generated; thumbnail could not be rendered: " + str(error)
    return {"ok": True, "metadata": metadata, "warning": warning, "collection": collection.name}


def main():
    if os.name != "nt" and "--thumbnail" not in sys.argv and os.getpgrp() != os.getpid():
        os.setsid()
    folder = Path(sys.argv[-1]).resolve()
    request = json.loads((folder / "request.json").read_text(encoding="utf8"))
    if (folder / "cancel.json").exists():
        return
    if "--thumbnail" in sys.argv:
        import bpy
        bpy.ops.wm.open_mainfile(filepath=str(folder / "asset.blend"))
        thumbnail(folder, bpy.data.collections["Studio Asset"])
        return
    try:
        source = Path(request["source"]).resolve()
        from infinigen_asset_studio.adapters import Infinigen1Adapter
        adapter = Infinigen1Adapter(source)
        status(folder, "Inspecting installed source", 0.05)
        if request["action"] == "scene":
            os.chdir(source)
            sys.path.insert(0, str(source))
            result = adapter.generate_room(folder, request) if request["mode"] == "ROOM" else adapter.generate_world(folder, request)
            write_json(folder / "result.json", result)
            status(folder, "Complete", 1.0)
            return
        catalogue = adapter.discover_assets()
        initialize(source)
        if (folder / "cancel.json").exists():
            return
        if request["action"] == "discover":
            from infinigen_asset_studio.scenes import discover_configs
            result = {"ok": True, "catalogue": catalogue, "version": version_info(source), "configs": discover_configs(source)}
        elif request["action"] == "generate":
            result = adapter.generate_asset(folder, request, catalogue)
        else:
            raise ValueError("Unknown Studio worker operation")
        write_json(folder / "result.json", result)
        status(folder, "Complete", 1.0)
    except Exception as error:
        category = "Missing dependency" if isinstance(error, ImportError) else "Invalid parameter" if isinstance(error, ValueError) else "File permission" if isinstance(error, PermissionError) else "Infinigen error"
        write_json(folder / "result.json", {"ok": False, "category": category,
            "message": category + ": " + str(error), "traceback": traceback.format_exc()})
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
