"""Real first-run/existing-install UI operations in a separate Blender process."""
import json
import os
import sys
import time
import types
from pathlib import Path
import bpy
import addon_utils

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "test_output/setup_ui" / str(time.time_ns())
os.environ["ASSET_STUDIO_DATA_DIR"] = str(DATA)
sys.path.insert(0, str(ROOT))
addon_utils.enable("infinigen_asset_studio", default_set=True, persistent=True)
from infinigen_asset_studio import addon, setup_ui, history
from infinigen_asset_studio.installation import InfinigenInstallationManager
manager = InfinigenInstallationManager()
assert manager.load()["active"] is None
cube = bpy.data.objects["Cube"]
cube["unsaved_work"] = "preserve"
state = bpy.context.scene.studio
assert bpy.ops.studio.setup(action="diagnostics") == {"FINISHED"}
assert "host_blender" in json.loads(state.diagnostics)
development = json.loads((ROOT / "runtime/development.json").read_text())
prefs = addon.preferences(bpy.context)
prefs.workspace = str(DATA)
for key in ("backend", "distribution", "source", "python"):
    setattr(prefs, key, development[key])


class WM:
    windows = []
    def event_timer_add(self, *args, **kwargs):
        return "test timer"
    def event_timer_remove(self, timer):
        pass
    def modal_handler_add(self, operator):
        pass


class Context:
    window_manager = WM()
    def __getattr__(self, key):
        return getattr(bpy.context, key)


context = Context()


def setup(action):
    operator = types.SimpleNamespace(action=action, _job=None, _timer=None, _settings=None)
    operator.finish = lambda ctx: setup_ui.STUDIO_OT_Setup.finish(operator, ctx)
    operator.cancel = lambda ctx: setup_ui.STUDIO_OT_Setup.cancel(operator, ctx)
    assert setup_ui.STUDIO_OT_Setup.execute(operator, context) == {"RUNNING_MODAL"}
    deadline = time.monotonic() + 120
    while True:
        outcome = setup_ui.STUDIO_OT_Setup.modal(operator, context, types.SimpleNamespace(type="TIMER"))
        if outcome in ({"FINISHED"}, {"CANCELLED"}):
            return outcome
        assert time.monotonic() < deadline
        time.sleep(.1)


assert setup("detect") == {"FINISHED"}, state.details
assert manager.active()["validation"]["compatible"]
assert not manager.active()["managed"]
assert cube["unsaved_work"] == "preserve"
original = manager.settings()
prefs.source = "/not-an-infinigen-installation"
assert setup("existing") == {"CANCELLED"}
assert "not an Infinigen" in state.error
assert manager.settings() == original
prefs.source = original["source"]
# Direct diagnostics and removal guards preserve externally managed environments.
operator = types.SimpleNamespace(action="repair", _job=None, _timer=None, _settings=None)
assert setup_ui.STUDIO_OT_Setup.execute(operator, context) == {"CANCELLED"}
assert "externally managed" in state.error
assert setup("selftest") == {"FINISHED"}, state.details
report = json.loads(state.diagnostics)
assert "smoke_test" in report
catalogue = json.loads((ROOT / "test_output/worker/discover/result.json").read_text())
addon.load_catalogue(bpy.context, catalogue)
state.creation_mode = "ROOM"
state.room_type = "bedroom"
state.seed = 12345
request = addon.scene_request(state)
assert request["settings"]["render_device"] == "AUTO"
entry = history.record(DATA, request, {"seed": 12345}, DATA, DATA / "scene.blend")
assert bpy.ops.studio.utility(action="history_favorite", target=entry["id"]) == {"FINISHED"}
assert history.records(DATA)[0]["favorite"]
path = DATA / "bedroom.json"
assert bpy.ops.studio.scene_preset_save(filepath=str(path)) == {"FINISHED"}
state.seed = 1
assert bpy.ops.studio.scene_preset_load(filepath=str(path)) == {"FINISHED"}
assert state.seed == 12345 and state.creation_mode == "ROOM"
addon_utils.disable("infinigen_asset_studio", default_set=True)
addon_utils.enable("infinigen_asset_studio", default_set=True, persistent=True)
assert InfinigenInstallationManager().settings() == original
assert cube["unsaved_work"] == "preserve"
print("STUDIO_SETUP_TEST_PASSED", flush=True)
