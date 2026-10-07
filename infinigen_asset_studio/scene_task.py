"""Invoke native scene main with actual stage reporting in its own process."""
import argparse
import importlib
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infinigen_asset_studio.core import write_json


def main():
    folder = Path(sys.argv[-1]).resolve()
    request = json.loads((folder / "scene-task.json").read_text())
    os.chdir(request["source"])
    sys.path.insert(0, request["source"])
    logging.basicConfig(level=logging.INFO)
    from infinigen.core.util.pipeline import RandomStageExecutor
    original = RandomStageExecutor.run_stage

    def stage(self, name, fn, *args, **kwargs):
        if (folder / "cancel.json").exists():
            raise InterruptedError("Scene generation cancelled")
        milestones = {"solve_rooms": .15, "solve_large": .3, "solve_medium": .45, "solve_small": .55,
                      "populate_assets": .65, "populate_doors": .75, "populate_windows": .8} if request["mode"] == "ROOM" else {}
        write_json(folder / "status.json", {"stage": name.replace("_", " ").title(),
                   "progress": milestones.get(name, request["progress"]), "pid": os.getpgid(0) if os.name != "nt" else os.getpid()})
        return original(self, name, fn, *args, **kwargs)

    RandomStageExecutor.run_stage = stage
    module = importlib.import_module("infinigen_examples.generate_indoors" if request["mode"] == "ROOM" else "infinigen_examples.generate_nature")
    selected_device = json.loads((folder / "request.json").read_text()).get("settings", {}).get("render_device", "AUTO")
    native_devices = module.init.configure_cycles_devices
    def configure_devices(use_gpu=True):
        import bpy
        if selected_device == "AUTO":
            return native_devices(use_gpu=use_gpu)
        if selected_device == "CPU":
            bpy.context.scene.cycles.device = "CPU"
            return
        prefs = bpy.context.preferences.addons["cycles"].preferences
        devices = prefs.get_devices_for_type(selected_device)
        if not any(d.type == selected_device for d in devices):
            raise ValueError("Selected Cycles device is unavailable in the worker: " + selected_device)
        prefs.compute_device_type = selected_device
        for device in prefs.devices:
            device.use = device.type == selected_device
        bpy.context.scene.cycles.device = "GPU"
    module.init.configure_cycles_devices = configure_devices
    if request["mode"] == "WORLD":
        original_fine = module.Terrain.fine_terrain
        def fine(self, *args, **kwargs):
            write_json(folder / "status.json", {"stage": "Refining terrain geometry and materials", "progress": .75,
                       "pid": os.getpgid(0) if os.name != "nt" else os.getpid()})
            return original_fine(self, *args, **kwargs)
        module.Terrain.fine_terrain = fine
    module.main(argparse.Namespace(seed=format(request["seed"], "x"), configs=request["configs"], overrides=request["overrides"],
                task=request["task"], task_uniqname=None, input_folder=Path(request["input"]) if request["input"] else None,
                output_folder=Path(request["output"])))
    import bpy
    write_json(folder / "status.json", {"stage": "Packing and saving Blender scene", "progress": .95 if request["mode"] == "ROOM" or "fine_terrain" in request["task"] else .5,
               "pid": os.getpgid(0) if os.name != "nt" else os.getpid()})
    bpy.context.scene["studio_mode"] = request["mode"]
    bpy.context.scene["studio_seed"] = request["seed"]
    bpy.context.scene["studio_configs"] = json.dumps(request["configs"])
    bpy.context.scene["studio_overrides"] = json.dumps(request["overrides"])
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(request["output"]) / "scene.blend"), check_existing=False)
    write_json(folder / "scene-summary.json", {"objects": len(bpy.data.objects), "meshes": len(bpy.data.meshes),
               "materials": len(bpy.data.materials), "cameras": sum(o.type == "CAMERA" for o in bpy.data.objects)})


if __name__ == "__main__":
    main()
