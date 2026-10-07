"""Cancel a real scene worker and assert its whole WSL process group is gone."""
import json
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infinigen_asset_studio.bridge import Job
from infinigen_asset_studio.scenes import build_request
root = Path(__file__).resolve().parent.parent
settings = json.loads((root / "runtime/development.json").read_text())
job = Job(settings, root / "test_output/cancel_scene", build_request("ROOM", 999, "living-room"))
deadline = time.monotonic() + 60
while True:
    status = job.status()
    if status.get("pid") and (job.folder / "scene-task.json").is_file():
        break
    assert time.monotonic() < deadline
    time.sleep(.1)
time.sleep(1)
pid = job.status()["pid"]
job.cancel()
assert job.process.poll() is not None and (job.folder / "cancel.json").is_file()
if settings["backend"] == "WSL":
    probe = subprocess.run(["wsl.exe", "-d", settings["distribution"], "--", "kill", "-0", "--", "-" + str(pid)], capture_output=True)
    assert probe.returncode != 0, "Scene process group survived cancellation"
print("SCENE_CANCELLATION_PASSED", flush=True)
