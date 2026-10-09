"""Install a real extension in a disposable repository and exercise real workers.

Run in Blender 4.2 with BLENDER_USER_CONFIG set to a disposable directory and
--factory-startup --offline-mode --background. No user preferences are overwritten.
An ignored runtime/development.json supplies the external engine paths.
"""
import importlib
import json
import os
from pathlib import Path
import subprocess
import time
from zipfile import ZipFile

import bpy
import addon_utils

ROOT = Path(__file__).resolve().parent.parent
folder = ROOT / "test_output/extension" / str(time.time_ns())
folder.mkdir(parents=True)
config_path = Path(os.environ["BLENDER_USER_CONFIG"]).resolve()
assert config_path.is_relative_to((ROOT / "test_output/extension").resolve())
assert Path(bpy.utils.user_resource("CONFIG")).resolve() == config_path, "Blender did not honor the isolated test profile"
os.environ["ASSET_STUDIO_DATA_DIR"] = str(folder / "data")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
archive_path = ROOT / "dist/infinigen_asset_studio-0.2.1.zip"
skip_room = "--skip-room" in __import__("sys").argv
with ZipFile(archive_path) as archive:
    names = archive.namelist()
    assert "blender_manifest.toml" in names and "__init__.py" in names
    assert "COPYING" in names and "LICENSE-BSD" in names
    assert b"def install(" not in archive.read("setup_worker.py")
    assert b"urllib" not in archive.read("setup_worker.py")
    assert not any(name.endswith((".so", ".exe", ".blend", ".whl")) for name in names)

repo_path = folder / "repository"
repo_path.mkdir()
bpy.ops.preferences.extension_repo_add(
    name="Studio extension validation", type="LOCAL", use_custom_directory=True,
    custom_directory=str(repo_path))
repo = next(r for r in bpy.context.preferences.extensions.repos if Path(r.directory) == repo_path)
result = bpy.ops.extensions.package_install_files(
    filepath=str(archive_path), repo=repo.module,
    enable_on_install=True)
assert result == {"FINISHED"}, result
module_name = "bl_ext." + repo.module + ".infinigen_asset_studio"
addon = importlib.import_module(module_name + ".addon")
bridge = importlib.import_module(module_name + ".bridge")
manager_type = importlib.import_module(module_name + ".installation").InfinigenInstallationManager
assert module_name in bpy.context.preferences.addons
assert "infinigen_asset_studio" not in __import__("sys").modules
assert not bpy.app.online_access
prefs = addon.preferences(bpy.context)
prefs.workspace = str(folder / "data")
assert bpy.context.scene.objects.get("Cube")
cube = bpy.context.scene.objects["Cube"]
before = set(repo_path.rglob("*"))

# Public operator requests cannot bypass the extension's installer restriction.
for action in ("install", "repair", "update", "remove"):
    assert bpy.ops.studio.setup(action=action) == {"CANCELLED"}
    assert "outside Blender" in bpy.context.scene.studio.error
assert set(repo_path.rglob("*")) == before

settings = json.loads((ROOT / "runtime/development.json").read_text(encoding="utf8"))
settings = {key: settings[key] for key in ("backend", "distribution", "source", "python")}
settings["managed"] = False


def wait(job, seconds=180):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = job.poll()
        if result is not None:
            return result
        time.sleep(.2)
    job.cancel()
    raise TimeoutError("Extension worker exceeded timeout")


validation = wait(bridge.Job(settings, folder / "data", {"action": "validate", "smoke": True}, "setup_worker.py"))
assert validation["report"]["healthy"] and validation["report"]["compatible"]
manager_type().activate(settings, validation["report"])
discovery = wait(bridge.Job(settings, folder / "data", {"action": "discover"}))
addon.load_catalogue(bpy.context, discovery)
assert len(bpy.context.scene.studio.assets) > 200
job = bridge.Job(settings, folder / "data", {"action": "generate",
    "generator": "infinigen.assets.objects.tableware.pan.PanFactory", "seed": 212,
    "quality": "DRAFT", "parameters": {"depth": .5}})
asset = wait(job)
assert asset["ok"] and (job.folder / "asset.blend").is_file()
collection = addon.tools.append_asset(job.folder / "asset.blend", asset["collection"])
assert collection.all_objects and cube in list(bpy.context.scene.objects)
assert bpy.ops.studio.scene_export(filepath=str(folder / "scene_copy.blend"), format="BLEND") == {"FINISHED"}
assert (folder / "scene_copy.blend").is_file()

# Preserve custom repository preferences for the separate scene process only.
bpy.ops.wm.save_userpref()
child = subprocess.run([bpy.app.binary_path, "--background", "--offline-mode",
    str(folder / "scene_copy.blend"), "--addons", module_name, "--python",
    str(repo_path / "infinigen_asset_studio/scene_open.py"), "--python-expr",
    "import bpy; assert hasattr(bpy.context.scene, 'studio'); print('EXTENSION_SCENE_OPEN_PASSED')",
    "--", module_name], capture_output=True, text=True, timeout=60)
assert child.returncode == 0 and "EXTENSION_SCENE_OPEN_PASSED" in child.stdout, child.stdout + child.stderr

# Exercise the staged scene-task bootstrap with a furnished native room.
room = None
if not skip_room:
    request = addon.scenes.build_request("ROOM", 0, "living-room", "DRAFT",
        height=2.8, clutter=False, camera="OVERHEAD", render_device="CPU")
    room_job = bridge.Job(settings, folder / "data", request)
    room = wait(room_job, seconds=360)
    assert room["ok"] and (room_job.folder / room["scene"]).is_file()
    assert room["metadata"]["statistics"]["objects"] > 20

addon_utils.disable(module_name, default_set=False)
assert not hasattr(bpy.types.Scene, "studio")
addon_utils.enable(module_name, default_set=False)
assert addon.preferences(bpy.context).workspace == str(folder / "data")
assert manager_type().active()["validation"]["compatible"]
addon_utils.disable(module_name, default_set=False)
assert set(repo_path.rglob("*")) == before, "Extension wrote into its installed directory"
summary = {"module": module_name, "archive": str(archive_path),
    "validation": True, "generated_pan": True, "scene_export": True,
    "separate_scene_open": True, "furnished_room": room["metadata"] if room else "skipped",
    "installer_refused": True, "disable_reenable": True}
(folder / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf8")
print("STUDIO_EXTENSION_TEST_PASSED", flush=True)
