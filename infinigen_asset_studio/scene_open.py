"""Enable the installed interface in a separate process without clearing the scene."""
import sys
from pathlib import Path
import bpy
import addon_utils
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
addon_utils.enable("infinigen_asset_studio", default_set=False, persistent=True)
from infinigen_asset_studio import addon
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
