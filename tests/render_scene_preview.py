"""Optional real generated-output preview, run in the external runtime."""
import sys
from pathlib import Path
import bpy
scene_path, target = map(Path, sys.argv[-2:])
bpy.ops.wm.open_mainfile(filepath=str(scene_path))
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 64
scene.cycles.use_denoising = True
scene.cycles.denoiser = "OPENIMAGEDENOISE"
scene.render.resolution_x = 640
scene.render.resolution_y = 480
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(target)
if scene.get("studio_mode") == "ROOM":
    # Preview-only fill light; the generated .blend is not modified or resaved.
    data = bpy.data.lights.new("Documentation fill", "AREA")
    data.energy = 2500
    data.shape = "DISK"
    data.size = 12
    light = bpy.data.objects.new("Documentation fill", data)
    scene.collection.objects.link(light)
    light.location = (scene.camera.location.x, scene.camera.location.y, 2.65)
    scene.render.film_transparent = False
target.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.render.render(write_still=True)
assert target.is_file()
print("SCENE_PREVIEW_SAVED", flush=True)
