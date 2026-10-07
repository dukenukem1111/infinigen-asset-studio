"""Exercise the UI generation queue with TIMER events in background Blender."""
import json
import sys
import time
import types
from pathlib import Path
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parent.parent
import os
os.environ.setdefault("ASSET_STUDIO_DATA_DIR", str(ROOT / "runtime/studio_data"))
sys.path.insert(0, str(ROOT))
addon_utils.enable("infinigen_asset_studio", default_set=True, persistent=True)
from infinigen_asset_studio import addon
from infinigen_asset_studio.core import write_json
folder = ROOT / "test_output/batch" / str(time.time_ns())
folder.mkdir(parents=True)
bpy.context.preferences.addons["infinigen_asset_studio"].preferences.workspace = str(folder)
addon.load_catalogue(bpy.context, json.loads((ROOT / "test_output/worker/discover/result.json").read_text()))
state = bpy.context.scene.studio
state.asset_index = next(i for i, a in enumerate(state.assets) if a.generator.endswith("tableware.pan.PanFactory"))
state.seed, state.batch_count = 30, 2


class WindowManagerProxy:
    """Only replace event scheduling; use real bpy scene data and real worker jobs."""
    windows = []
    def event_timer_add(self, *args, **kwargs):
        return "background test timer"
    def event_timer_remove(self, timer):
        pass
    def modal_handler_add(self, operator):
        pass


class ContextProxy:
    window_manager = WindowManagerProxy()
    def __getattr__(self, name):
        return getattr(bpy.context, name)


context = ContextProxy()
operator = types.SimpleNamespace(action="batch", _job=None, _timer=None, _remaining=0, _request=None)
operator.finish = lambda ctx: addon.STUDIO_OT_Job.finish(operator, ctx)
operator.cancel = lambda ctx: addon.STUDIO_OT_Job.cancel(operator, ctx)
assert addon.STUDIO_OT_Job.execute(operator, context) == {"RUNNING_MODAL"}
deadline = time.monotonic() + 120
while state.busy:
    result = addon.STUDIO_OT_Job.modal(operator, context, types.SimpleNamespace(type="TIMER"))
    assert time.monotonic() < deadline
    if result == {"CANCELLED"}:
        raise RuntimeError(state.details)
    time.sleep(0.2)
collections = [c for c in bpy.context.scene.collection.children if "studio_metadata" in c]
assert len(collections) == 2
seeds = [json.loads(c["studio_metadata"])["seed"] for c in collections]
assert seeds == [30, 31], seeds
assert state.active_collection == collections[-1].name
assert all(o.hide_get() for o in collections[0].all_objects)
assert any(not o.hide_get() for o in collections[1].all_objects)
assert len(addon.variation_items(state, bpy.context)) == 2
state.variation = collections[0].name
assert state.active_collection == collections[0].name
assert state.seed == 30
assert not state.error
write_json(ROOT / "test_output/batch/summary.json", {"modal_queue": True, "seeds": seeds, "thumbnail_selection": True, "preview_visibility": True})
print("STUDIO_BATCH_TEST_PASSED", flush=True)
