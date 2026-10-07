"""Native setup, diagnostics and scene result operators; heavy work is isolated."""
import json
import os
import subprocess
import platform
import shutil
import sys
from pathlib import Path
import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper
from . import bridge, history, scenes
from .core import write_json
from .installation import InfinigenInstallationManager, MANIFEST


def ui():
    from . import addon
    return addon


def world_items(self, context):
    global WORLD_KEY
    if WORLD_KEY == self.scene_configs:
        return WORLD_ITEMS
    values = json.loads(self.scene_configs or "{}")
    # Blender's enum strings must remain alive.
    WORLD_ITEMS[:] = [(v["id"], v["name"], v["id"]) for v in values.get("world_presets", [])]
    if not WORLD_ITEMS:
        WORLD_ITEMS[:] = [("NONE", "Discover scene configs first", "Use Discover generators after setup")]
    WORLD_KEY = self.scene_configs
    return WORLD_ITEMS


WORLD_ITEMS = []
WORLD_KEY = None
CONFIG_ITEMS = []
CONFIG_KEY = None
RENDER_ITEMS = [("AUTO", "Auto", "Use native Cycles device selection"), ("CPU", "CPU", "Use CPU Cycles rendering")]
RENDER_KEY = None


def config_items(self, context):
    global CONFIG_KEY
    key = (self.scene_configs, self.creation_mode, self.config_search)
    if key != CONFIG_KEY:
        configs = json.loads(self.scene_configs or "{}").get(self.creation_mode, [])
        CONFIG_ITEMS[:] = [(v["id"], v["name"], v["id"]) for v in configs if self.config_search.lower() in (v["name"] + v["id"]).lower()]
        if not CONFIG_ITEMS:
            CONFIG_ITEMS[:] = [("NONE", "No matching configs", "Discover scene configs first")]
        CONFIG_KEY = key
    return CONFIG_ITEMS


def render_items(self, context):
    global RENDER_KEY
    active = InfinigenInstallationManager().load().get("active") or {}
    devices = active.get("validation", {}).get("hardware", {}).get("cycles_devices", [])
    supported = {v["type"] for v in devices}
    key = tuple(sorted(supported))
    if key != RENDER_KEY:
        RENDER_ITEMS[:] = [("AUTO", "Auto", "Native Cycles selection"), ("CPU", "CPU", "CPU Cycles rendering")] + [(v, "CUDA" if v == "CUDA" else "OptiX", "Reported by worker Cycles") for v in ("CUDA", "OPTIX") if v in supported]
        RENDER_KEY = key
    return RENDER_ITEMS


def host_diagnostics(context):
    value = {"studio": MANIFEST["studio_version"], "host_blender": bpy.app.version_string,
             "host_python": sys.version, "os": platform.platform(), "cpu": os.environ.get("PROCESSOR_IDENTIFIER", platform.processor()),
             "cpu_count": os.cpu_count(), "disk_free_gb": round(shutil.disk_usage(ui().workspace(context)).free / 1024 ** 3, 1)}
    if os.name == "nt":
        import ctypes
        class Memory(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [(name, ctypes.c_ulonglong) for name in ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")]
        memory = Memory()
        memory.length = ctypes.sizeof(memory)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            value["ram_gb"] = round(memory.total / 1024 ** 3, 1)
    elif hasattr(os, "sysconf"):
        value["ram_gb"] = round(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1024 ** 3, 1)
    return value


class STUDIO_OT_Setup(bpy.types.Operator):
    bl_idname = "studio.setup"
    bl_label = "Infinigen Setup"
    action: StringProperty(default="detect")
    _job = None
    _timer = None
    _settings = None

    @classmethod
    def poll(cls, context):
        return not context.scene.studio.busy

    def invoke(self, context, event):
        if self.action == "remove":
            return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def execute(self, context):
        addon = ui()
        manager = InfinigenInstallationManager()
        state, prefs = context.scene.studio, addon.preferences(context)
        try:
            if self.action == "diagnostics" and not manager.load().get("active"):
                state.diagnostics = json.dumps(host_diagnostics(context), indent=2)
                state.status = "Host diagnostics ready · Copy Diagnostics to inspect"
                return {"FINISHED"}
            if self.action in {"install", "repair", "update", "remove"}:
                if self.action == "install":
                    value = manager.managed_settings(prefs.distribution)
                else:
                    value = manager.active()
                    if not value.get("managed"):
                        raise ValueError("This installation is externally managed. Asset Studio will not modify it. Install a separate managed copy instead.")
                self._settings = value
                request = dict(action="remove" if self.action == "remove" else "install", managed_root=value["managed_root"])
                settings = dict(value, python="python3")
            elif self.action == "detect":
                candidates = manager.candidates()
                if not candidates:
                    raise ValueError("No existing installation found. Install a managed copy or select the source and worker Python below.")
                self._settings = candidates[0]
                settings = self._settings
                request = {"action": "validate", "smoke": False}
            elif self.action == "existing":
                self._settings = {key: getattr(prefs, key) for key in ("backend", "distribution", "source", "python")}
                self._settings["managed"] = False
                settings = self._settings
                request = {"action": "validate", "smoke": False}
            else:
                self._settings = manager.active()
                settings = self._settings
                request = {"action": "validate", "smoke": self.action == "selftest"}
            self._job = bridge.Job(settings, addon.workspace(context), request, "setup_worker.py")
            state.busy, state.error, state.details = True, "", ""
            state.last_log = str(self._job.folder / "worker.log")
            addon.RUNNING = self
            self._timer = context.window_manager.event_timer_add(.3, window=context.window)
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}
        except Exception as exception:
            addon.error(context, exception)
            return {"CANCELLED"}

    def finish(self, context):
        ui().STUDIO_OT_Job.finish(self, context)

    def cancel(self, context):
        ui().STUDIO_OT_Job.cancel(self, context)

    def modal(self, context, event):
        addon = ui()
        state = context.scene.studio
        if event.type == "ESC":
            self.cancel(context)
            return {"CANCELLED"}
        if addon.RUNNING is not self:
            return {"CANCELLED"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        try:
            status = self._job.status()
            state.status, state.progress = status["stage"], status["progress"]
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    area.tag_redraw()
            result = self._job.poll()
            if result is None:
                return {"PASS_THROUGH"}
            manager = InfinigenInstallationManager()
            report = result["report"]
            if self.action == "remove":
                config = manager.load()
                config["active"] = None
                write_json(manager.config_path, config)
                state.status = "Managed dependency removed; outputs and library preserved"
            else:
                state.diagnostics = json.dumps(report, indent=2)
                if self.action in {"detect", "existing", "install", "repair", "update"}:
                    manager.activate(self._settings, report, addon.preferences(context).allow_mismatch)
                    prefs = addon.preferences(context)
                    for key in ("backend", "distribution", "source", "python"):
                        setattr(prefs, key, self._settings[key])
                else:
                    manager.update_report(report)
                state.status = "Infinigen ready · use Discover generators to load assets and scene configs"
            self.finish(context)
            return {"FINISHED"}
        except Exception as exception:
            addon.error(context, exception)
            self.finish(context)
            return {"CANCELLED"}


class STUDIO_OT_Utility(bpy.types.Operator):
    bl_idname = "studio.utility"
    bl_label = "Studio Utility"
    action: StringProperty()
    target: StringProperty()

    def execute(self, context):
        addon = ui()
        state = context.scene.studio
        manager = InfinigenInstallationManager()
        try:
            if self.action == "diagnostics_copy":
                context.window_manager.clipboard = json.dumps({"host": host_diagnostics(context), "installation": manager.load(), "runtime": json.loads(state.diagnostics or "{}"),
                    "output": str(addon.workspace(context)), "last_status": state.status}, indent=2)
                return {"FINISHED"}
            if self.action == "config_add":
                if state.scene_config_choice == "NONE":
                    raise ValueError("Select a discovered configuration")
                state.extra_configs = "\n".join(dict.fromkeys([v for v in state.extra_configs.splitlines() if v] + [state.scene_config_choice]))
                return {"FINISHED"}
            if self.action == "configs":
                text = bpy.data.texts.get("Studio Scene Configs") or bpy.data.texts.new("Studio Scene Configs")
                text.clear()
                text.write(json.dumps(json.loads(state.scene_configs or "{}"), indent=2))
                state.status = "Configuration catalogue loaded in Blender's Text Editor"
                return {"FINISHED"}
            if self.action == "overrides_edit":
                text = bpy.data.texts.get("Studio Scene Overrides") or bpy.data.texts.new("Studio Scene Overrides")
                text.clear()
                text.write(state.scene_overrides)
                state.status = "Edit Studio Scene Overrides in Text Editor, then Apply Overrides"
                return {"FINISHED"}
            if self.action == "overrides_apply":
                text = bpy.data.texts.get("Studio Scene Overrides")
                if not text:
                    raise ValueError("Open the override editor first")
                state.scene_overrides = text.as_string()
                state.status = "Scene overrides applied to the next generation request"
                return {"FINISHED"}
            if self.action == "check_updates":
                active = manager.load().get("active") or {}
                commit = active.get("validation", {}).get("commit")
                state.status = "Recommended commit already installed" if commit == MANIFEST["commit"] else "Recommended Infinigen 1.19.0 is available in this add-on's manifest"
                return {"FINISHED"}
            if self.action.startswith("history_"):
                items = history.records(addon.workspace(context))
                entry = next(v for v in items if v["id"] == self.target)
                if self.action == "history_favorite":
                    entry["favorite"] = not entry["favorite"]
                    write_json(addon.workspace(context) / "history.json", items)
                    return {"FINISHED"}
                if self.action == "history_regenerate":
                    addon.apply_scene_request(state, entry["request"])
                    return bpy.ops.studio.job(action="scene") if entry["request"].get("mode") in {"ROOM", "WORLD"} else bpy.ops.studio.job(action="generate")
                path = entry["output"] if self.action == "history_open" else entry["folder"]
            elif self.action == "scene_open":
                path = state.scene_output
            elif self.action == "log":
                if not state.last_log:
                    raise ValueError("No job log yet")
                bpy.ops.text.open(filepath=state.last_log)
                state.status = "Log loaded in Blender's Text Editor"
                return {"FINISHED"}
            elif self.action == "source":
                active = manager.active()
                path = active["source"]
                if active["backend"] == "WSL":
                    path = "\\\\wsl.localhost\\" + active["distribution"] + path.replace("/", "\\")
            else:
                path = str(addon.workspace(context))
            if not path:
                raise ValueError("No generated scene yet")
            if str(path).endswith(".blend"):
                if not Path(path).is_file():
                    raise ValueError("Generated file is missing")
                subprocess.Popen([bpy.app.binary_path, path, "--python", str(Path(__file__).with_name("scene_open.py"))], creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            else:
                bpy.ops.wm.path_open(filepath=str(path))
            return {"FINISHED"}
        except Exception as exception:
            addon.error(context, exception)
            return {"CANCELLED"}


class STUDIO_OT_ScenePresetSave(bpy.types.Operator, ExportHelper):
    bl_idname = "studio.scene_preset_save"
    bl_label = "Save Scene Preset"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})
    target: StringProperty()

    def execute(self, context):
        try:
            entry = next(v for v in history.records(ui().workspace(context)) if v["id"] == self.target) if self.target else None
            request = entry["request"] if entry else ui().scene_request(context.scene.studio)
            source_version = entry["metadata"].get("source_version", {}) if entry else InfinigenInstallationManager().active().get("validation", {})
            write_json(self.filepath, history.preset(request, source_version))
            return {"FINISHED"}
        except Exception as exception:
            ui().error(context, exception)
            return {"CANCELLED"}


class STUDIO_OT_ScenePresetLoad(bpy.types.Operator, ImportHelper):
    bl_idname = "studio.scene_preset_load"
    bl_label = "Load Scene Preset"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        try:
            ui().apply_scene_request(context.scene.studio, history.read_preset(self.filepath))
            return {"FINISHED"}
        except Exception as exception:
            ui().error(context, exception)
            return {"CANCELLED"}


CLASSES = (STUDIO_OT_Setup, STUDIO_OT_Utility, STUDIO_OT_ScenePresetSave, STUDIO_OT_ScenePresetLoad)
