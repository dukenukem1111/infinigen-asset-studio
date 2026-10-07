"""Version-specific adapter to Infinigen 1.19's original scene entry points."""
import json
import subprocess
import sys
import time
from pathlib import Path
from .core import write_json
from .installation import MANIFEST

ROOMS = [("random", "Random Interior"), ("living-room", "Living Room"), ("bedroom", "Bedroom"),
         ("kitchen", "Kitchen"), ("dining-room", "Dining Room"), ("bathroom", "Bathroom")]


def discover_configs(source):
    source = Path(source)
    result = {}
    for mode, folder in (("ROOM", "configs_indoor"), ("WORLD", "configs_nature"), ("PIPELINE", "configs")):
        root = source / "infinigen_examples" / folder
        if mode == "PIPELINE":
            root = source / "infinigen/datagen/configs"
        result[mode] = [{"id": str(path.relative_to(source)).replace("\\", "/"),
                         "name": path.stem.replace("_", " ").title()} for path in sorted(root.rglob("*.gin"))]
    result["world_presets"] = [v for v in result["WORLD"] if "/scene_types/" in v["id"]]
    return result


def build_request(mode, seed, preset, quality="DRAFT", **settings):
    if mode not in {"ROOM", "WORLD"} or type(seed) is not int or not 0 <= seed <= 2147483646:
        raise ValueError("Invalid scene mode or seed")
    if quality not in {"DRAFT", "PREVIEW", "FINAL"}:
        raise ValueError("Invalid scene quality")
    return {"action": "scene", "mode": mode, "seed": seed, "preset": preset,
            "quality": quality, "settings": settings}


def configuration(request, source):
    mode, quality = request["mode"], request["quality"]
    settings = request.get("settings", {})
    available = discover_configs(source)
    if mode == "ROOM":
        if request["preset"] not in dict(ROOMS):
            raise ValueError("Unsupported furnished room type")
        configs = ["singleroom.gin", "overhead.gin"]
        if quality != "FINAL":
            configs.append("fast_solve.gin")
        overrides = ["compose_indoors.terrain_enabled=False", "compose_indoors.nature_backdrop_enabled=False"]
        if quality == "DRAFT":
            overrides += ["compose_indoors.solve_steps_large=25", "compose_indoors.solve_steps_medium=10", "compose_indoors.solve_steps_small=2"]
        if request["preset"] != "random":
            tag = {"living-room": "LivingRoom", "bedroom": "Bedroom", "kitchen": "Kitchen", "dining-room": "DiningRoom", "bathroom": "Bathroom"}[request["preset"]]
            overrides.append("restrict_solving.restrict_parent_rooms=" + repr([tag]))
        overrides.append("RoomConstants.global_params.wall_height=" + repr(float(settings.get("height", 3))))
        if not settings.get("clutter", True):
            overrides.append("compose_indoors.solve_small_enabled=False")
        if settings.get("camera", "OVERHEAD") == "INTERIOR":
            overrides += ["compose_indoors.overhead_cam_enabled=False", "compose_indoors.pose_cameras_enabled=True"]
    else:
        preset = request["preset"]
        names = {v["id"] for v in available["world_presets"]}
        if preset not in names:
            raise ValueError("Selected nature config does not exist in the active source")
        configs = [preset]
        if quality == "DRAFT":
            configs.append("simple.gin")
        elif quality == "PREVIEW":
            configs.append("dev.gin")
        else:
            configs.append("high_quality_terrain.gin")
        overrides = []
        if settings.get("override_trees", False):
            overrides.append("compose_nature.tree_density=" + repr(float(settings["tree_density"])))
        if settings.get("override_sun", False):
            overrides.append("nishita_lighting.sun_elevation=" + repr(float(settings["sun_elevation"])))
    all_ids = {v["id"] for key in ("ROOM", "WORLD") for v in available[key]}
    for item in settings.get("extra_configs", []):
        if item not in all_ids:
            raise ValueError("Advanced config must be a discovered file in the active source: " + item)
        configs.append(item)
    for item in settings.get("overrides", []):
        if "=" not in item or "\n" in item:
            raise ValueError("Each advanced override must be one selector=value binding")
        overrides.append(item)
    return configs, overrides


def generate(folder, request, source):
    from .worker import status, version_info
    configs, overrides = configuration(request, source)
    stage_root = folder / "scene"
    stage_root.mkdir()
    start = time.monotonic()
    tasks = [("coarse", None, stage_root / "coarse")]
    if request["mode"] == "WORLD":
        tasks.append(("populate,fine_terrain", stage_root / "coarse", stage_root / "fine"))
    script = Path(__file__).with_name("scene_task.py")
    for index, (task, input_path, output_path) in enumerate(tasks):
        status(folder, "Creating architecture and furniture" if request["mode"] == "ROOM" else "Generating terrain" if index == 0 else "Populating assets and refining terrain", .1 if index == 0 else .55)
        write_json(folder / "scene-task.json", {"source": str(source), "mode": request["mode"], "seed": request["seed"],
                   "task": task.split(","), "input": str(input_path) if input_path else None, "output": str(output_path),
                   "configs": configs, "overrides": overrides, "progress": .1 if index == 0 else .55})
        subprocess.run([sys.executable, str(script), str(folder)], cwd=source, check=True)
        if (folder / "cancel.json").exists():
            raise InterruptedError("Scene generation cancelled")
    target = tasks[-1][2] / "scene.blend"
    if not target.is_file():
        raise RuntimeError("Upstream scene task did not produce scene.blend")
    metadata = {"schema_version": 1, "studio_version": MANIFEST["studio_version"], "mode": request["mode"],
                "seed": request["seed"], "preset": request["preset"], "quality": request["quality"],
                "settings": request.get("settings", {}), "configs": configs, "overrides": overrides,
                "source_version": version_info(source), "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "generation_seconds": round(time.monotonic() - start, 2), "output_files": [str(target.relative_to(folder))],
                "reproducibility": "Upstream scene reproducibility varies by platform; exact seed and bindings are recorded."}
    summary = folder / "scene-summary.json"
    if summary.is_file():
        metadata["statistics"] = json.loads(summary.read_text())
    write_json(folder / "generation.json", metadata)
    return {"ok": True, "metadata": metadata, "scene": str(target.relative_to(folder))}
