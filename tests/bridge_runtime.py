"""Windows-side tests of the exact WSL subprocess bridge used by the sidebar."""
import json
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from infinigen_asset_studio.bridge import Job
from infinigen_asset_studio.core import write_json
settings = json.loads((ROOT / "runtime/development.json").read_text())
folder = ROOT / "test_output/bridge"
summary = {}

job = Job(settings, folder, {"action": "generate", "generator": "infinigen.assets.objects.tableware.pan.PanFactory", "seed": 121, "quality": "DRAFT", "parameters": {"depth": 0.5}})
started = time.monotonic()
while True:
    result = job.poll()
    if result is not None:
        assert result["ok"] and (job.folder / "asset.blend").is_file()
        break
    assert time.monotonic() - started < 120
    time.sleep(0.2)
summary["generation_via_bridge"] = True
print("BRIDGE_GENERATION_PASSED", flush=True)

job = Job(settings, folder, {"action": "generate", "generator": "infinigen.assets.sim_objects.box.BoxFactory", "seed": 1, "quality": "PREVIEW", "parameters": {}})
started = time.monotonic()
while not job.status().get("pid"):
    assert time.monotonic() - started < 60
    time.sleep(0.1)
job.cancel()
assert job.process.poll() is not None
summary["cancel_worker_process_group"] = True
print("BRIDGE_CANCEL_PASSED", flush=True)
job = Job(settings, folder, {"action": "generate", "generator": "infinigen.assets.sim_objects.box.BoxFactory", "seed": 2, "quality": "PREVIEW", "parameters": {}})
job.cancel()
assert job.process.poll() is not None and (job.folder / "cancel.json").is_file()
summary["cancel_before_worker_pid"] = True
print("BRIDGE_EARLY_CANCEL_PASSED", flush=True)
write_json(folder / "summary.json", summary)
