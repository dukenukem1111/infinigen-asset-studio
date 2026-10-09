"""Build a GPL extension variant with no dependency installation code.

External workers run in the user's existing interpreter. Their namespace bootstrap
does not change the interactive Blender process's module search path.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "infinigen_asset_studio"
EXTENSION_VERSION = re.search(
    r'^version = "([0-9]+\.[0-9]+\.[0-9]+)"$',
    (ROOT / "extension/blender_manifest.toml").read_text(encoding="utf8"), re.MULTILINE).group(1)
BOOTSTRAP = '''import importlib.util
sys.dont_write_bytecode = True
_package_dir = Path(__file__).resolve().parent
if "_infinigen_asset_worker" not in sys.modules:
    def _deny_network(event, args):
        if event in {"socket.connect", "socket.getaddrinfo"}:
            raise PermissionError("Prepare missing Infinigen resources outside Blender; extension workers run offline")
    sys.addaudithook(_deny_network)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    _spec = importlib.util.spec_from_file_location(
        "_infinigen_asset_worker", _package_dir / "__init__.py",
        submodule_search_locations=[str(_package_dir)])
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = _module
    _spec.loader.exec_module(_module)
'''


def worker_source(text):
    old = "sys.path.insert(0, str(Path(__file__).resolve().parent.parent))"
    if text.count(old) != 1:
        raise ValueError("Worker bootstrap changed; update the extension builder")
    result = text.replace(old, BOOTSTRAP).replace(
        "from infinigen_asset_studio.", "from _infinigen_asset_worker.")
    return offline_bpy(result)


def offline_bpy(text):
    return re.sub(r"^( +)import bpy\n", lambda m: m.group(0) + m.group(1) +
                  "bpy.context.preferences.system.use_online_access = False\n", text, flags=re.MULTILINE)


def validation_worker():
    original = (PACKAGE / "setup_worker.py").read_text(encoding="utf8")
    tree = ast.parse(original)
    validation = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "validation")
    function = ast.get_source_segment(original, validation)
    function = function.replace("from infinigen_asset_studio.", "from _infinigen_asset_worker.")
    function = offline_bpy(function)
    function = function.replace("Repair a managed installation", "Repair Infinigen outside Blender")
    return '''"""Read-only external runtime validation; no installer or network downloads."""
import json
import os
import platform
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
''' + BOOTSTRAP + '''
from _infinigen_asset_worker.core import write_json
from _infinigen_asset_worker.installation import MANIFEST

''' + function + '''

def main():
    if os.name != "nt" and os.getpgrp() != os.getpid():
        os.setsid()
    folder = Path(sys.argv[-1]).resolve()
    request = json.loads((folder / "request.json").read_text(encoding="utf8"))
    if (folder / "cancel.json").exists():
        return
    try:
        if request["action"] != "validate":
            raise ValueError("Install and repair Infinigen outside Blender")
        write_json(folder / "status.json", {"stage": "Validating installation", "progress": .02, "pid": os.getpid()})
        report = validation(Path(request["source"]), request.get("smoke", False))
        write_json(folder / "result.json", {"ok": True, "report": report})
        write_json(folder / "status.json", {"stage": "Complete", "progress": 1, "pid": os.getpid()})
    except Exception as error:
        traceback.print_exc()
        write_json(folder / "result.json", {"ok": False, "message": str(error), "traceback": traceback.format_exc()})
        sys.exit(1)

if __name__ == "__main__":
    main()
'''


def stage(destination):
    for path in sorted(PACKAGE.rglob("*")):
        if not path.is_file() or path.suffix not in {".py", ".json", ".txt"} or path.name == "machine.json":
            continue
        target = destination / path.relative_to(PACKAGE)
        target.parent.mkdir(parents=True, exist_ok=True)
        text = path.read_text(encoding="utf8")
        if path.name == "setup_worker.py":
            text = validation_worker()
        elif path.name in {"worker.py", "scene_task.py"}:
            text = worker_source(text)
            if path.name == "worker.py":
                text = text.replace("from . import scenes", "from _infinigen_asset_worker import scenes")
        elif path.name == "__init__.py":
            tree = ast.parse(text)
            tree.body = [n for n in tree.body if not (
                isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "bl_info" for t in n.targets))]
            text = ast.unparse(tree) + "\n"
            text = text.replace("def register():\n", "def register():\n    import bpy\n    if hasattr(bpy.types.Scene, 'studio'):\n        raise RuntimeError('Disable the legacy Infinigen Asset Studio add-on before enabling this extension')\n")
        elif path.name == "scene_open.py":
            text = '''"""Initialize the extension enabled by Blender's --addons argument."""
import importlib
import sys
import bpy
package = sys.argv[sys.argv.index("--") + 1]
addon = importlib.import_module(package + ".addon")
addon.on_load(None)
state = bpy.context.scene.studio
state.creation_mode = bpy.context.scene.get("studio_mode", "ASSET")
state.scene_output = bpy.data.filepath
state.seed = bpy.context.scene.get("studio_seed", 0)
state.status = "Generated scene · edit, save and export using Blender"
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type == "VIEW_3D":
            area.spaces.active.show_region_ui = True
'''
        elif path.name == "compatibility.json":
            value = json.loads(text)
            value["studio_version"] = EXTENSION_VERSION
            text = json.dumps(value, indent=2) + "\n"
        if path.suffix == ".py":
            ast.parse(text)
        target.write_text(text, encoding="utf8")
    shutil.copyfile(ROOT / "extension/blender_manifest.toml", destination / "blender_manifest.toml")
    shutil.copyfile(ROOT / "extension/COPYING", destination / "COPYING")
    shutil.copyfile(ROOT / "LICENSE", destination / "LICENSE-BSD")
    shutil.copyfile(ROOT / "THIRD_PARTY_LICENSES.md", destination / "THIRD_PARTY_LICENSES.md")
    shutil.copyfile(ROOT / "docs/extension_setup.md", destination / "README.md")
    (destination / "LICENSE").write_text(
        "This extension distribution is licensed under GPL-3.0-or-later; see COPYING.\n"
        "Original BSD-3-Clause notices are retained in LICENSE-BSD.\n", encoding="utf8")


def build(blender):
    output = ROOT / "dist" / ("infinigen_asset_studio-" + EXTENSION_VERSION + ".zip")
    output.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="studio-extension-") as folder:
        source = Path(folder)
        stage(source)
        subprocess.run([blender, "--command", "extension", "build", "--source-dir", str(source),
                        "--output-filepath", str(output)], check=True)
    subprocess.run([blender, "--command", "extension", "validate", str(output)], check=True)
    output.with_suffix(".zip.sha256").write_text(
        hashlib.sha256(output.read_bytes()).hexdigest() + "  " + output.name + "\n", encoding="utf8")
    print(output)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", required=True, help="Blender 4.2 executable")
    build(parser.parse_args().blender)
