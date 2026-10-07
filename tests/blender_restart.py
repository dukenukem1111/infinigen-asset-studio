"""Separate Blender launch: verify saved session and library survive restart."""
import json
import sys
from pathlib import Path
import bpy
import addon_utils
ROOT = Path(__file__).resolve().parent.parent
import os
os.environ.setdefault("ASSET_STUDIO_DATA_DIR", str(ROOT / "runtime/studio_data"))
sys.path.insert(0, str(ROOT))
addon_utils.enable("infinigen_asset_studio", default_set=True, persistent=True)
from infinigen_asset_studio import addon, scene_tools as tools
OUTPUT = Path(json.loads((ROOT / "test_output/blender/latest.json").read_text())["output"])
prefs = bpy.context.preferences.addons["infinigen_asset_studio"].preferences
prefs.workspace = str(OUTPUT / "studio")
bpy.ops.wm.open_mainfile(filepath=str(OUTPUT / "session.blend"))
state = bpy.context.scene.studio
assert len(state.assets) > 100
assert len(state.library) == 1
assert not state.busy
assert addon.CATALOGUE
collection = tools.asset_collection(bpy.context)
assert tools.statistics(collection)["triangles"] > 0
print("STUDIO_RESTART_TEST_PASSED", flush=True)
