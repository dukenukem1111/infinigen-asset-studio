"""Run with the installed Infinigen Python; results are in test_output/worker."""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from infinigen_asset_studio.core import write_json

SOURCE = Path(sys.argv[1])
OUTPUT = ROOT / "test_output/worker"
OUTPUT.mkdir(parents=True, exist_ok=True)


def run(name, action, **parameters):
    folder = OUTPUT / name
    folder.mkdir(exist_ok=True)
    result_path = folder / "result.json"
    if result_path.exists():
        result_path.unlink()
    write_json(folder / "request.json", dict(action=action, source=str(SOURCE), **parameters))
    start = time.perf_counter()
    with (folder / "worker.log").open("w") as log:
        p = subprocess.run([sys.executable, str(ROOT / "infinigen_asset_studio/worker.py"), str(folder)], stdout=log, stderr=subprocess.STDOUT, timeout=240)
    result = json.loads((folder / "result.json").read_text())
    print(name, p.returncode, result.get("message", "OK"), f"{time.perf_counter() - start:.2f}s", flush=True)
    return result


catalog = run("discover", "discover")
assert catalog["ok"], catalog
items = catalog["catalogue"]
chair = next(i for i in items if i["id"].endswith("chairs.chair.ChairFactory"))
pan = next(i for i in items if i["id"].endswith("tableware.pan.PanFactory"))
box = next(i for i in items if i["id"].endswith("sim_objects.box.BoxFactory"))
cabinet = next(i for i in items if i["id"].endswith("sim_objects.cabinet.CabinetFactory"))
summary = {"catalogue_count": len(items), "runtime": catalog["version"], "tests": {}}
for name, item, seed, params in (("chair_42", chair, 42, {"width": 0.42, "leg_height": 0.46, "has_arm": True}),
    ("chair_42_repeat", chair, 42, {"width": 0.42, "leg_height": 0.46, "has_arm": True}),
    ("chair_seed_only", chair, 43, {"width": 0.42, "leg_height": 0.46, "has_arm": True}),
    ("chair_width_only", chair, 42, {"width": 0.48, "leg_height": 0.46, "has_arm": True}),
    ("chair_43", chair, 43, {"width": 0.48, "leg_height": 0.49, "has_arm": False}),
    ("pan_12", pan, 12, {"depth": 0.5, "x_handle": 1.5}), ("box_8", box, 8, {}), ("cabinet_7", cabinet, 7, {})):
    result = run(name, "generate", generator=item["id"], seed=seed, parameters=params, quality="PREVIEW")
    summary["tests"][name] = result
    write_json(OUTPUT / "summary.json", summary)
bad = run("invalid", "generate", generator=chair["id"], seed=42, parameters={"width": -5})
assert not bad["ok"] and bad["category"] == "Invalid parameter"
summary["invalid_parameter_handled"] = True
write_json(OUTPUT / "summary.json", summary)
assert all(r["ok"] for r in summary["tests"].values()), "Some factories failed; inspect summary/logs"
