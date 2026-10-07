"""Launch a fresh Studio session without changing the user's saved Blender settings."""
import json
import os
import sys
from pathlib import Path
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("ASSET_STUDIO_DATA_DIR", str(ROOT / "runtime/studio_data"))
sys.path.insert(0, str(ROOT))
addon_utils.enable("infinigen_asset_studio", default_set=True, persistent=True)
from infinigen_asset_studio import addon

prefs = bpy.context.preferences.addons["infinigen_asset_studio"].preferences
prefs.workspace = str(ROOT / "runtime")
addon.on_load(None)
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type == "VIEW_3D":
            space = area.spaces.active
            space.show_region_ui = True
            space.shading.type = "MATERIAL"
            space.shading.use_scene_world = False
            space.shading.use_scene_lights = False
            space.clip_end = 10000
            for region in area.regions:
                if region.type == "UI":
                    try:
                        region.active_panel_category = "Asset Studio"
                    except AttributeError:
                        pass

if bpy.context.scene.studio.assets:
    index = next((i for i, item in enumerate(bpy.context.scene.studio.assets) if item.generator.endswith("chairs.chair.ChairFactory")), 0)
    bpy.context.scene.studio.asset_index = index
    bpy.context.scene.studio.status = "Ready · select a generator and click Generate"

# The launcher passes --factory-startup and creates a separate new Blender process.
for obj in list(bpy.context.scene.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
