"""Verify the ZIP as an isolated add-on, without installing into user preferences."""
import json
import sys
import time
from pathlib import Path
from zipfile import ZipFile
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parent.parent
import os
os.environ.setdefault("ASSET_STUDIO_DATA_DIR", str(ROOT / "runtime/studio_data"))
folder = ROOT / "test_output/package" / str(time.time_ns())
with ZipFile(ROOT / "dist/Infinigen_Asset_Studio.zip") as archive:
    for name in archive.namelist():
        assert name.startswith("infinigen_asset_studio/") and ".." not in Path(name).parts
    archive.extractall(folder)
sys.path.insert(0, str(folder))
addon_utils.enable("infinigen_asset_studio", default_set=True, persistent=True)
from infinigen_asset_studio import addon, bridge
assert str(folder) in addon.__file__
bpy.context.preferences.addons["infinigen_asset_studio"].preferences.workspace = str(folder / "runtime")
addon.load_catalogue(bpy.context, json.loads((ROOT / "test_output/worker/discover/result.json").read_text()))
state = bpy.context.scene.studio
state.asset_index = next(i for i, a in enumerate(state.assets) if a.generator.endswith("chairs.chair.ChairFactory"))
assert state.parameters["back_type"].choice == "whole"
assert state.parameters["width"].label == "Seat Width"
assert bpy.ops.studio.parameter_help.get_rna_type()
assert len(addon.EXPORT_FORMATS) == 5
job = bridge.Job(addon.settings(bpy.context), folder / "runtime", {"action": "generate", "generator": "infinigen.assets.objects.tableware.pan.PanFactory", "seed": 212, "quality": "DRAFT", "parameters": {"depth": 0.5}})
deadline = time.monotonic() + 120
while True:
    result = job.poll()
    if result:
        assert result["ok"] and (job.folder / "asset.blend").is_file()
        break
    assert time.monotonic() < deadline
    time.sleep(0.2)
addon_utils.disable("infinigen_asset_studio", default_set=True)
print("STUDIO_PACKAGE_TEST_PASSED", flush=True)
