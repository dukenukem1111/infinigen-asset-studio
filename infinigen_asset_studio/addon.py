"""Native Blender sidebar, operators and persisted Studio UI state."""
import json
import logging
import math
import secrets
import shutil
import traceback
import uuid
from pathlib import Path

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import bridge, scene_tools as tools
from . import history, scenes, setup_ui, scene_ui
from .installation import InfinigenInstallationManager, data_directory, MANIFEST
from .distribution import is_extension
from .core import SCHEMA_VERSION, randomize, read_metadata, safe_name, validate_parameters, write_json

logger = logging.getLogger(__name__)
CATALOGUE = {}
ENUM_CACHE = {}
RUNNING = None
PREVIEWS = None
VARIATION_CACHE = []
VARIATION_KEY = None
JOINT_ENUM_CACHE = []
JOINT_ENUM_KEY = None
BOOTSTRAP = None


def preferences(context):
    return context.preferences.addons[__package__].preferences


def workspace(context):
    path = Path(bpy.path.abspath(preferences(context).workspace))
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings(context):
    return InfinigenInstallationManager().settings()


def scene_request(state):
    return scenes.build_request(state.creation_mode, state.seed, state.room_type if state.creation_mode == "ROOM" else state.world_preset,
        state.scene_quality, height=state.room_height, clutter=state.room_clutter, camera=state.room_camera,
        override_trees=state.override_trees, tree_density=state.tree_density, override_sun=state.override_sun,
        sun_elevation=state.sun_elevation, extra_configs=[v.strip() for v in state.extra_configs.splitlines() if v.strip()],
        render_device=state.render_device,
        overrides=[v.strip() for v in state.scene_overrides.splitlines() if v.strip()])


def apply_scene_request(state, request):
    state.seed = request["seed"]
    if request.get("mode") not in {"ROOM", "WORLD"}:
        index = next(i for i, item in enumerate(state.assets) if item.generator == request["generator"])
        state.asset_index = index
        state.creation_mode = "ASSET"
        state.quality = request.get("quality", "PREVIEW")
        for param in state.parameters:
            param.enabled = param.name in request.get("parameters", {})
            if param.enabled:
                set_value(param, request["parameters"][param.name])
        return
    state.creation_mode = request["mode"]
    setattr(state, "room_type" if state.creation_mode == "ROOM" else "world_preset", request["preset"])
    state.scene_quality = request["quality"]
    mapping = {"height": "room_height", "clutter": "room_clutter", "camera": "room_camera"}
    for key, value in request.get("settings", {}).items():
        if key in {"extra_configs", "overrides"}:
            setattr(state, "extra_configs" if key == "extra_configs" else "scene_overrides", "\n".join(value))
        elif hasattr(state, mapping.get(key, key)):
            setattr(state, mapping.get(key, key), value)


def error(context, exception):
    state = context.scene.studio
    text = str(exception)
    state.error = text.splitlines()[0][:240] if text else "Operation failed. See Technical Details."
    state.details = traceback.format_exc()
    logger.error(state.error, exc_info=True)
    state.status = "Operation failed"


def selected(context):
    state = context.scene.studio
    if not state.assets or not 0 <= state.asset_index < len(state.assets):
        return None
    return CATALOGUE.get(state.assets[state.asset_index].generator)


def definitions(state):
    return [json.loads(p.definition) for p in state.parameters]


def values(state):
    result = {}
    for p in state.parameters:
        if p.enabled:
            result[p.name] = p.boolean if p.kind == "bool" else p.choice if p.kind == "enum" else p.integer if p.kind == "int" else p.number
    return result


def set_value(p, value):
    setattr(p, "boolean" if p.kind == "bool" else "choice" if p.kind == "enum" else "integer" if p.kind == "int" else "number", value)


def changed(self, context):
    self.enabled = True
    if context and hasattr(context.scene, "studio"):
        context.scene.studio.modified = True


def lock_changed(self, context):
    if self.locked:
        self.enabled = True


def variation_items(self, context):
    global VARIATION_KEY
    if context is None or PREVIEWS is None:
        return VARIATION_CACHE
    collections = [c for c in context.scene.collection.children if "studio_metadata" in c]
    key = tuple((c.name, c.get("studio_thumbnail", "")) for c in collections)
    if key != VARIATION_KEY:
        VARIATION_CACHE.clear()
        for index, collection in enumerate(collections):
            path = collection.get("studio_thumbnail", "")
            icon = "MESH_DATA"
            if Path(path).is_file():
                if path not in PREVIEWS:
                    PREVIEWS.load(path, path, "IMAGE")
                icon = PREVIEWS[path].icon_id
            VARIATION_CACHE.append((collection.name, collection.name, "Open this generated variation", icon, index))
        VARIATION_KEY = key
    return VARIATION_CACHE


def variation_changed(self, context):
    if not context or self.busy:
        return
    collection = bpy.data.collections.get(self.variation)
    if collection:
        tools.select_collection(context, collection)
        self.statistics = json.dumps(tools.statistics(collection))
        try:
            load_metadata(context, json.loads(collection["studio_metadata"]))
        except ValueError as exception:
            self.status = str(exception)


def joint_position_get(self):
    collection = bpy.data.collections.get(self.active_collection)
    joint_list = tools.joints(collection) if collection else []
    if not joint_list:
        return 0.0
    _, _, node = joint_list[min(self.joint_index, len(joint_list) - 1)]
    low, high = node.inputs.get("Min"), node.inputs.get("Max")
    low, high = low.default_value if low else 0, high.default_value if high else 1
    return max(0.0, min(1.0, (node.inputs["Value"].default_value - low) / (high - low))) if high != low else 0.0


def joint_position_set(self, value):
    collection = bpy.data.collections.get(self.active_collection)
    joint_list = tools.joints(collection) if collection else []
    if not joint_list:
        return
    obj, tree, node = joint_list[min(self.joint_index, len(joint_list) - 1)]
    socket = node.inputs["Value"]
    if socket.is_linked:
        return
    if "studio_rest" not in node:
        node["studio_rest"] = socket.default_value
    low, high = node.inputs.get("Min"), node.inputs.get("Max")
    low, high = low.default_value if low else 0, high.default_value if high else 1
    socket.default_value = low + (high - low) * value
    tree.interface_update(bpy.context)
    obj.update_tag()


def joint_items(self, context):
    global JOINT_ENUM_KEY
    collection = bpy.data.collections.get(self.active_collection)
    joint_list = tools.joints(collection) if collection else []
    key = tuple((tree.name, node.name) for _, tree, node in joint_list)
    if key != JOINT_ENUM_KEY:
        JOINT_ENUM_CACHE.clear()
        for index, (_, _, node) in enumerate(joint_list):
            label = node.inputs.get("Joint Label")
            text = label.default_value if label and not label.is_linked else node.name
            JOINT_ENUM_CACHE.append((str(index), str(text).replace("_", " ").title(), "Inspect this native joint and its connected components", index))
        JOINT_ENUM_KEY = key
    return JOINT_ENUM_CACHE


def choice_items(self, context):
    key = self.choices
    if key not in ENUM_CACHE:
        ENUM_CACHE[key] = [(str(v), str(v), "Generator style: " + str(v)) for v in json.loads(key or "[]")]
    return ENUM_CACHE[key]


def select_generator(self, context):
    item = selected(context)
    self.parameters.clear()
    self.reconstruction = ""
    if not item:
        return
    for definition in item["parameters"]:
        p = self.parameters.add()
        p.name = definition["name"]
        p.label = definition["display_name"]
        p.kind = definition["type"]
        p.definition = json.dumps(definition)
        p.choices = json.dumps(definition.get("enum_values", []))
        set_value(p, definition["default"])
        p.enabled = False
    self.modified = True


def restore_catalogue(state):
    CATALOGUE.clear()
    if state.catalogue:
        for item in json.loads(state.catalogue):
            CATALOGUE[item["id"]] = item


def load_catalogue(context, data):
    state = context.scene.studio
    state.catalogue = json.dumps(data["catalogue"])
    state.version = json.dumps(data["version"])
    restore_catalogue(state)
    state.assets.clear()
    favorites_path = workspace(context) / "generator_favorites.json"
    favorites = json.loads(favorites_path.read_text(encoding="utf8")) if favorites_path.exists() else []
    for item in data["catalogue"]:
        entry = state.assets.add()
        entry.name = item["name"]
        entry.generator = item["id"]
        entry.category = item["category"]
        entry.articulated = item["articulated"]
        entry.favorite = item["id"] in favorites
    state.asset_index = 0
    select_generator(state, context)
    state.status = f"Discovered {len(state.assets)} generator candidates"


def load_metadata(context, metadata):
    state = context.scene.studio
    match = next((i for i, a in enumerate(state.assets) if a.generator == metadata["generator"]), None)
    if match is None:
        raise ValueError("Discover the source installation containing this generator before loading its parameters.")
    state.asset_index = match
    select_generator(state, context)
    validate_parameters(definitions(state), metadata.get("parameters", {}))
    state.seed = metadata["seed"]
    state.quality = metadata.get("quality", "PREVIEW")
    for p in state.parameters:
        if p.name in metadata.get("parameters", {}):
            set_value(p, metadata["parameters"][p.name])
            p.enabled = True
        p.locked = p.name in metadata.get("locks", [])
    state.modified = False
    state.reconstruction = json.dumps(metadata)


class STUDIO_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    backend: EnumProperty(name="Generation backend", items=[("WSL", "Ubuntu / WSL", "Linux runtime through WSL"), ("LOCAL", "Local Python", "Isolated Python environment with compatible bpy and Infinigen")], default="WSL" if __import__("os").name == "nt" else "LOCAL")
    distribution: StringProperty(name="WSL distribution")
    source: StringProperty(name="Existing source folder", description="Path as seen by the selected backend")
    python: StringProperty(name="Existing worker Python", description="Interpreter with Infinigen and bpy installed")
    allow_mismatch: BoolProperty(name="Use Anyway (untested version)", description="Explicitly allow a healthy existing environment that differs from the tested commit", default=False)
    workspace: StringProperty(name="Studio library and output folder", subtype="DIR_PATH", default=str(data_directory()))

    def draw(self, context):
        layout = self.layout
        layout.label(text="Use Blender 4.2 to match this installed Infinigen runtime.", icon="INFO")
        for key in ("backend", "distribution", "source", "python", "workspace"):
            if key != "distribution" or self.backend == "WSL":
                layout.prop(self, key)
        layout.label(text="Use Setup → Validate & Use to activate these inputs.")


class STUDIO_Parameter(bpy.types.PropertyGroup):
    label: StringProperty()
    kind: StringProperty()
    definition: StringProperty()
    choices: StringProperty(default="[]")
    enabled: BoolProperty(name="Override", description="Use this value instead of the generator's native seeded sampling", default=False)
    locked: BoolProperty(name="Lock", description="Enable and preserve this explicit value during parameter randomization", update=lock_changed)
    number: FloatProperty(name="Value", description="Explicit generator control; supported range is shown below", update=changed)
    integer: IntProperty(name="Value", description="Explicit whole-number generator control", update=changed)
    boolean: BoolProperty(name="Value", description="Enable or disable this generator feature", update=changed)
    choice: EnumProperty(name="Style", description="Native generator choice", items=choice_items, update=changed)


class STUDIO_Asset(bpy.types.PropertyGroup):
    generator: StringProperty()
    category: StringProperty()
    articulated: BoolProperty()
    favorite: BoolProperty()


class STUDIO_LibraryEntry(bpy.types.PropertyGroup):
    path: StringProperty()
    collection: StringProperty()
    tags: StringProperty()
    favorite: BoolProperty()
    thumbnail: StringProperty()


class STUDIO_State(bpy.types.PropertyGroup):
    creation_mode: EnumProperty(name="Create", items=[("ASSET", "Asset", "Individual procedural objects"), ("ROOM", "Room", "Native indoor solver"), ("WORLD", "World", "Native nature pipeline")], default="ASSET")
    scene_configs: StringProperty()
    room_type: EnumProperty(name="Room Type", items=[(v, label, "Native furnished room constraints") for v, label in scenes.ROOMS], default="random")
    world_preset: EnumProperty(name="Environment", items=setup_ui.world_items)
    scene_quality: EnumProperty(name="Scene Quality", items=[("DRAFT", "Draft", "Native fast solver / simple nature preset"), ("PREVIEW", "Preview", "Native fast solver / dev nature preset"), ("FINAL", "Final", "Native full indoor solver / high quality terrain")], default="DRAFT")
    room_height: FloatProperty(name="Wall Height", min=2.4, max=5, default=3, unit="LENGTH")
    room_clutter: BoolProperty(name="Solve small decorations", default=True)
    room_camera: EnumProperty(name="Camera", items=[("OVERHEAD", "Overhead", "Native overhead config"), ("INTERIOR", "Interior", "Search native interior camera poses")], default="OVERHEAD")
    override_trees: BoolProperty(name="Override tree density")
    tree_density: FloatProperty(name="Tree Density", min=0, max=1, default=.05)
    override_sun: BoolProperty(name="Override sun elevation")
    sun_elevation: FloatProperty(name="Sun Elevation (degrees)", min=0, max=90, default=40)
    extra_configs: StringProperty(name="Additional config paths", description="Discovered paths separated by newline; no arbitrary external files")
    scene_overrides: StringProperty(name="Gin overrides", description="One selector=value binding per line; advanced native settings")
    config_search: StringProperty(name="Search configurations")
    scene_config_choice: EnumProperty(name="Configuration", items=setup_ui.config_items)
    render_device: EnumProperty(name="Cycles Device", items=setup_ui.render_items)
    scene_output: StringProperty(subtype="FILE_PATH")
    diagnostics: StringProperty()
    last_log: StringProperty(subtype="FILE_PATH")
    catalogue: StringProperty()
    version: StringProperty()
    assets: CollectionProperty(type=STUDIO_Asset)
    asset_index: IntProperty(update=select_generator)
    parameters: CollectionProperty(type=STUDIO_Parameter)
    search: StringProperty(name="Search assets", description="Search generator names, categories and descriptions")
    category: StringProperty(name="Category", description="Category filter; leave empty to show all categories")
    favorites_only: BoolProperty(name="Favorites only")
    advanced: BoolProperty(name="Advanced controls", description="Show conservatively inferred generator controls and technical information")
    seed: IntProperty(name="Seed", description="Reproducible factory seed, recorded with parameter overrides", default=42, min=0, max=2147483646)
    quality: EnumProperty(name="Quality", items=[("DRAFT", "Draft", "Limit remaining subdivision for a faster viewport"), ("PREVIEW", "Preview", "Limit remaining subdivision to level one"), ("PRODUCTION", "Production", "Retain the factory's original geometry and modifiers")], default="PREVIEW")
    modified: BoolProperty(default=True)
    reconstruction: StringProperty()
    preserve_edits: BoolProperty(name="Preserve live node edits", description="Reapply saved or current modifier inputs and native joint controls after regeneration", default=True)
    busy: BoolProperty(default=False, options={"SKIP_SAVE"})
    status: StringProperty(default="Connect to your installed Infinigen runtime")
    progress: FloatProperty(min=0, max=1, subtype="FACTOR")
    error: StringProperty()
    details: StringProperty()
    show_details: BoolProperty(name="Technical Details")
    active_collection: StringProperty()
    batch_count: IntProperty(name="Variations", description="Generate sequential seeds without freezing Blender", min=1, max=64, default=4)
    random_nonce: IntProperty(default=0, min=0)
    variation: EnumProperty(name="Variation browser", items=variation_items, update=variation_changed)
    statistics: StringProperty()
    asset_name: StringProperty(name="Name", default="My Asset")
    tags: StringProperty(name="Tags", description="Comma-separated search tags")
    library: CollectionProperty(type=STUDIO_LibraryEntry)
    library_index: IntProperty()
    library_search: StringProperty(name="Search library")
    library_favorites: BoolProperty(name="Favorite assets only")
    joint_index: IntProperty(name="Joint", min=0)
    joint_choice: EnumProperty(name="Select Joint", items=joint_items, get=lambda self: self.joint_index, set=lambda self, value: setattr(self, "joint_index", value))
    joint_position: FloatProperty(name="Test Position", description="Move the selected native joint between its minimum and maximum limits", min=0, max=1, subtype="FACTOR", get=joint_position_get, set=joint_position_set)
    scale: FloatProperty(name="Scale multiplier", description="Uniformly scale root objects while preserving their hierarchy", min=0.001, max=1000, default=1)
    lod_level: EnumProperty(name="Inspect LOD", items=[("0", "Original", "Original live geometry"), ("1", "LOD 1 · 50%", "Show first simplified copy"), ("2", "LOD 2 · 25%", "Show second simplified copy"), ("3", "LOD 3 · 10%", "Show third simplified copy")], default="0")


class STUDIO_UL_Assets(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.name.removesuffix("Factory"), icon="CONSTRAINT_BONE" if item.articulated else "MESH_DATA")
        if item.favorite:
            row.label(text="", icon="SOLO_ON")

    def filter_items(self, context, data, propname):
        state = context.scene.studio
        flags = []
        for item in getattr(data, propname):
            description = CATALOGUE.get(item.generator, {}).get("description", "")
            match = state.search.lower() in (item.name + item.category + description).lower() and state.category.lower() in item.category.lower()
            flags.append(self.bitflag_filter_item if match and (not state.favorites_only or item.favorite) else 0)
        return flags, []


class STUDIO_UL_Library(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row()
        row.label(text=item.name, icon="SOLO_ON" if item.favorite else "ASSET_MANAGER")

    def filter_items(self, context, data, propname):
        state = context.scene.studio
        return [self.bitflag_filter_item if state.library_search.lower() in (v.name + " " + v.tags).lower() and (v.favorite or not state.library_favorites) else 0 for v in getattr(data, propname)], []


class STUDIO_OT_Job(bpy.types.Operator):
    bl_idname = "studio.job"
    bl_label = "Generate"
    bl_description = "Run the installed generator in an isolated cancellable process"
    action: EnumProperty(items=[("generate", "Generate", "Generate an asset"), ("discover", "Discover", "Inspect source factories"), ("batch", "Batch", "Generate variations sequentially"), ("scene", "Scene", "Run the native room or world pipeline")], default="generate")
    _job = None
    _timer = None
    _remaining = 0
    _request = None

    @classmethod
    def poll(cls, context):
        return not context.scene.studio.busy

    def execute(self, context):
        global RUNNING
        state = context.scene.studio
        try:
            if self.action == "discover":
                self._request = {"action": "discover"}
                self._remaining = 1
            elif self.action == "scene":
                active = InfinigenInstallationManager().active()
                key = "rooms" if state.creation_mode == "ROOM" else "worlds"
                if not active.get("validation", {}).get("capabilities", {}).get(key, {}).get("available"):
                    raise ValueError("This installation does not have the required scene capability. Run Diagnostics or repair a managed copy.")
                self._request = scene_request(state)
                self._remaining = 1
            else:
                item = selected(context)
                if not item:
                    raise ValueError("Discover generators and select an asset first.")
                self._request = {"action": "generate", "generator": item["id"], "seed": state.seed,
                    "quality": state.quality, "parameters": validate_parameters(definitions(state), values(state))}
                if state.preserve_edits:
                    current = active_or_none(context)
                    source_data = tools.snapshot(current) if current else json.loads(state.reconstruction or "{}")
                    edits = source_data.get("native_edits", {})
                    if edits.get("generator") == item["id"]:
                        self._request["native_edits"] = edits
                self._remaining = state.batch_count if self.action == "batch" else 1
            self._job = bridge.Job(settings(context), workspace(context), self._request)
            state.last_log = str(self._job.folder / "worker.log")
            state.busy, state.error, state.details = True, "", ""
            RUNNING = self
            self._timer = context.window_manager.event_timer_add(0.3, window=context.window)
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}
        except Exception as exception:
            error(context, exception)
            return {"CANCELLED"}

    def finish(self, context):
        global RUNNING
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        context.scene.studio.busy = False
        RUNNING = None

    def cancel(self, context):
        try:
            if self._job:
                self._job.cancel()
        except Exception as exception:
            error(context, exception)
        finally:
            self.finish(context)
            context.scene.studio.status = "Cancelled; existing assets are preserved"

    def modal(self, context, event):
        state = context.scene.studio
        if event.type == "ESC":
            self.cancel(context)
            return {"CANCELLED"}
        if RUNNING is not self:
            return {"CANCELLED"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        try:
            status = self._job.status()
            state.status, state.progress = status["stage"], status["progress"]
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == "VIEW_3D":
                        area.tag_redraw()
            result = self._job.poll()
            if result is None:
                return {"PASS_THROUGH"}
            if self._request["action"] == "discover":
                state.scene_configs = json.dumps(result.get("configs", {}))
                load_catalogue(context, result)
                write_json(workspace(context) / "catalogue.json", result)
            elif self._request["action"] == "scene":
                state.scene_output = str(self._job.folder / result["scene"])
                state.status = "Scene ready · Open Generated Scene in a new Blender window"
                history.record(workspace(context), self._request, result["metadata"], self._job.folder, state.scene_output)
            else:
                collection = tools.append_asset(self._job.folder / "asset.blend", result["collection"])
                collection["studio_thumbnail"] = str(self._job.folder / "thumbnail.png")
                tools.select_collection(context, collection)
                state.asset_name = result["metadata"]["name"]
                state.statistics = json.dumps(result["metadata"]["statistics"])
                state.modified = False
                state.status = result.get("warning") or f'Generated in {result["metadata"]["generation_seconds"]:.2f}s'
                history.record(workspace(context), self._request, result["metadata"], self._job.folder, self._job.folder / "asset.blend")
            self._remaining -= 1
            if self._remaining:
                self._request["seed"] = (self._request["seed"] + 1) % 2147483647
                self._job = bridge.Job(settings(context), workspace(context), self._request)
                state.seed = self._request["seed"]
                return {"PASS_THROUGH"}
            self.finish(context)
            return {"FINISHED"}
        except Exception as exception:
            error(context, exception)
            self.finish(context)
            return {"CANCELLED"}


class STUDIO_OT_Action(bpy.types.Operator):
    bl_idname = "studio.action"
    bl_label = "Asset Studio"
    bl_options = {"REGISTER", "UNDO"}
    action: StringProperty()
    target: StringProperty()

    def execute(self, context):
        state = context.scene.studio
        try:
            if self.action == "CANCEL":
                if RUNNING:
                    RUNNING.cancel(context)
            elif self.action in {"PREVIOUS", "NEXT", "SEED", "COPY_SEED"}:
                if self.action == "COPY_SEED":
                    context.window_manager.clipboard = str(state.seed)
                else:
                    state.seed = secrets.randbelow(2147483647) if self.action == "SEED" else (state.seed + (1 if self.action == "NEXT" else -1)) % 2147483647
                    state.modified = True
            elif self.action == "RANDOMIZE":
                visible = [p for p in definitions(state) if state.advanced or not p["advanced"]]
                new_values = randomize(visible, values(state), {p.name for p in state.parameters if p.locked}, state.seed + state.random_nonce)
                state.random_nonce = (state.random_nonce + 1) % 2147483647
                for p in state.parameters:
                    if not p.locked and p.name in new_values:
                        set_value(p, new_values[p.name])
                        p.enabled = True
                state.modified = True
            elif self.action == "FAVORITE_GENERATOR":
                if state.assets:
                    item = state.assets[state.asset_index]
                    item.favorite = not item.favorite
                    write_json(workspace(context) / "generator_favorites.json", [a.generator for a in state.assets if a.favorite])
            elif self.action in {"RESET", "OPEN", "CLOSE", "POSE"}:
                count = tools.pose(tools.asset_collection(context), self.action, state.seed)
                state.status = f"Updated {count} unlinked native joint controls"
            elif self.action == "SELECT":
                collection = bpy.data.collections.get(self.target)
                if collection:
                    tools.select_collection(context, collection)
                    state.statistics = json.dumps(tools.statistics(collection))
                    load_metadata(context, json.loads(collection["studio_metadata"]))
            elif self.action == "STATS":
                state.statistics = json.dumps(tools.statistics(tools.asset_collection(context)))
            elif self.action == "LODS":
                collection = tools.asset_collection(context)
                if any(o.get("studio_derived") == "LOD" for o in collection.all_objects):
                    raise ValueError("LOD copies already exist. Delete those copies in the Outliner before rebuilding.")
                tools.make_lods(collection)
                state.status = "Created independent LOD copies; choose a level to inspect"
            elif self.action == "SHOW_LOD":
                collection = tools.asset_collection(context)
                level = int(state.lod_level)
                if level and not any(o.get("studio_lod") == level for o in collection.all_objects):
                    raise ValueError("Build LODs before choosing this level.")
                for obj in collection.all_objects:
                    if obj.type == "MESH" and obj.get("studio_derived") != "COLLISION":
                        obj.hide_set(obj.get("studio_lod", 0) != level)
            elif self.action in {"HULL", "BOX"}:
                tools.make_collision(tools.asset_collection(context), self.action)
            elif self.action == "PIVOT":
                tools.ground_pivot(tools.asset_collection(context))
            elif self.action == "SCALE":
                collection = tools.asset_collection(context)
                for obj in collection.all_objects:
                    if obj.parent is None:
                        obj.scale *= state.scale
                context.scene.unit_settings.system = "METRIC"
                context.scene.unit_settings.scale_length = 1
                state.scale = 1
            elif self.action == "MATERIAL":
                collection = tools.asset_collection(context)
                rng = __import__("random").Random(state.seed)
                mat = bpy.data.materials.new("Studio independent material")
                mat.use_nodes = True
                bsdf = mat.node_tree.nodes.get("Principled BSDF")
                bsdf.inputs["Base Color"].default_value = (rng.random(), rng.random(), rng.random(), 1)
                bsdf.inputs["Roughness"].default_value = rng.uniform(0.15, 0.8)
                for obj in collection.all_objects:
                    if obj.type == "MESH" and not obj.get("studio_derived"):
                        obj.data = obj.data.copy()
                        obj.data.materials.clear()
                        obj.data.materials.append(mat)
                state.status = "Applied an independent mesh material; node-assigned materials may override it"
            elif self.action == "LIBRARY_REFRESH":
                refresh_library(context)
            elif self.action == "SAVE_LIBRARY":
                collection = tools.asset_collection(context)
                folder = workspace(context) / "library" / uuid.uuid4().hex
                folder.mkdir(parents=True)
                metadata = tools.save_blend(collection, folder / "asset.blend")
                metadata.update(name=state.asset_name, tags=state.tags, favorite=True, collection=collection.name)
                write_json(folder / "metadata.json", metadata)
                thumb = Path(collection.get("studio_thumbnail", ""))
                if thumb.is_file():
                    shutil.copy2(thumb, folder / "thumbnail.png")
                refresh_library(context)
                state.status = "Saved favorite asset, reconstruction JSON and native .blend"
            elif self.action == "LIBRARY_OPEN":
                entry = state.library[state.library_index]
                collection = tools.append_asset(Path(entry.path) / "asset.blend", entry.collection)
                collection["studio_thumbnail"] = str(Path(entry.path) / "thumbnail.png")
                tools.select_collection(context, collection)
                load_metadata(context, read_metadata(Path(entry.path) / "metadata.json"))
                state.statistics = json.dumps(tools.statistics(collection))
            elif self.action == "LIBRARY_FAVORITE":
                entry = state.library[state.library_index]
                metadata = read_metadata(Path(entry.path) / "metadata.json")
                metadata["favorite"] = not metadata.get("favorite", False)
                write_json(Path(entry.path) / "metadata.json", metadata)
                entry.favorite = metadata["favorite"]
            elif self.action == "DETAILS":
                text = bpy.data.texts.get("Studio Technical Details") or bpy.data.texts.new("Studio Technical Details")
                text.clear()
                text.write(state.details)
                state.status = "Technical Details are available in Blender's Text Editor"
            else:
                raise ValueError("Unsupported Studio operation")
            state.error = ""
            return {"FINISHED"}
        except Exception as exception:
            error(context, exception)
            self.report({"ERROR"}, state.error)
            return {"CANCELLED"}


def refresh_library(context):
    state = context.scene.studio
    state.library.clear()
    for path in sorted((workspace(context) / "library").glob("*/metadata.json")):
        try:
            data = read_metadata(path)
            entry = state.library.add()
            entry.name, entry.path, entry.collection = data.get("name", "Asset"), str(path.parent), data["collection"]
            entry.tags, entry.favorite = data.get("tags", ""), data.get("favorite", False)
            entry.thumbnail = str(path.parent / "thumbnail.png")
        except (ValueError, KeyError, OSError):
            logger.warning("Skipped unreadable library entry %s", path)
    state.library_index = min(state.library_index, max(0, len(state.library) - 1))


class STUDIO_OT_Save(bpy.types.Operator, ExportHelper):
    bl_idname = "studio.save"
    bl_label = "Save Studio Data"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})
    project: BoolProperty(name="Include native .blend asset", default=False)

    def execute(self, context):
        try:
            state = context.scene.studio
            item = selected(context)
            if not item:
                raise ValueError("Select a generator first.")
            data = {"schema_version": SCHEMA_VERSION, "generator": item["id"], "seed": state.seed,
                "parameters": validate_parameters(definitions(state), values(state)), "quality": state.quality,
                "locks": [p.name for p in state.parameters if p.locked], "source_version": json.loads(state.version or "{}")}
            path = Path(self.filepath)
            if self.project:
                collection = tools.asset_collection(context)
                generated = json.loads(collection["studio_metadata"])
                left, right = generated["parameters"], data["parameters"]
                same_parameters = left.keys() == right.keys() and all(
                    math.isclose(left[k], right[k], rel_tol=1e-6, abs_tol=1e-7) if type(left[k]) in {int, float} and type(right[k]) in {int, float} else left[k] == right[k] for k in left)
                if generated["generator"] != item["id"] or generated["seed"] != state.seed or not same_parameters:
                    raise ValueError("Generate the current parameters before saving a project. Save Preset can store ungenerated settings.")
                blend_path = path.with_suffix(".blend")
                if blend_path.exists():
                    raise FileExistsError("The companion .blend already exists. Choose a new project filename to preserve it.")
                data = tools.save_blend(collection, blend_path)
                data.update(collection=collection.name, locks=[p.name for p in state.parameters if p.locked])
            write_json(path, data)
            state.status = "Saved project" if self.project else "Saved parameter preset"
            return {"FINISHED"}
        except Exception as exception:
            error(context, exception)
            self.report({"ERROR"}, context.scene.studio.error)
            return {"CANCELLED"}


class STUDIO_OT_Load(bpy.types.Operator, ImportHelper):
    bl_idname = "studio.load"
    bl_label = "Open Preset / Project"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        try:
            path = Path(self.filepath)
            metadata = read_metadata(path)
            load_metadata(context, metadata)
            if metadata.get("collection") and path.with_suffix(".blend").is_file():
                collection = tools.append_asset(path.with_suffix(".blend"), metadata["collection"])
                tools.select_collection(context, collection)
                context.scene.studio.statistics = json.dumps(tools.statistics(collection))
            context.scene.studio.status = "Loaded saved Studio data"
            return {"FINISHED"}
        except Exception as exception:
            error(context, exception)
            self.report({"ERROR"}, context.scene.studio.error)
            return {"CANCELLED"}


class STUDIO_OT_ParameterHelp(bpy.types.Operator):
    bl_idname = "studio.parameter_help"
    bl_label = "Parameter Help"
    tooltip: StringProperty(options={"HIDDEN"})

    @classmethod
    def description(cls, context, properties):
        return properties.tooltip

    def execute(self, context):
        self.report({"INFO"}, self.tooltip)
        return {"FINISHED"}


def export_formats(self, context):
    return EXPORT_FORMATS


EXPORT_FORMATS = [("BLEND", "Blender · .blend", "Preserve Infinigen procedural geometry, materials and articulation")]


class STUDIO_OT_Export(bpy.types.Operator, ExportHelper):
    bl_idname = "studio.export"
    bl_label = "Export Asset"
    filename_ext = ""
    format: EnumProperty(name="Format", items=export_formats)
    preset: EnumProperty(name="Target", items=[("BLENDER", "Blender", "Native procedural archive"), ("UNITY", "Unity", "FBX Y up, -Z forward"), ("UNREAL", "Unreal", "FBX Z up, -Y forward; import with engine conversion"), ("GODOT", "Godot", "glTF recommended, Y up"), ("GENERIC", "Generic", "Native exporter defaults")], default="BLENDER")
    acknowledge: BoolProperty(name="Export a static pose without procedural materials or joints", description="Mesh formats do not preserve Infinigen node-based articulation; procedural shaders are not baked")
    include_derived: BoolProperty(name="Include LOD and collision copies", default=False)

    def draw(self, context):
        self.layout.prop(self, "format")
        self.layout.prop(self, "preset")
        if self.format != "BLEND":
            self.layout.label(text="Exports evaluated geometry at the current pose.", icon="INFO")
            self.layout.label(text="Procedural shaders need a separate baking workflow.")
            self.layout.prop(self, "acknowledge")
            self.layout.prop(self, "include_derived")

    def execute(self, context):
        try:
            if self.format != "BLEND" and not self.acknowledge:
                raise ValueError("Acknowledge the static pose/material limitation or choose .blend to preserve live articulation.")
            suffix = {"BLEND": ".blend", "GLB": ".glb", "FBX": ".fbx", "OBJ": ".obj", "USD": ".usdc"}[self.format]
            path = Path(self.filepath).with_suffix(suffix)
            if path.exists() or path.with_suffix(suffix + ".json").exists():
                raise FileExistsError("Choose a new export filename to preserve the existing asset and metadata.")
            data = tools.export_asset(context, tools.asset_collection(context), path, self.format, self.preset, self.include_derived)
            data["export"] = {"format": self.format, "preset": self.preset, "static_pose": self.format != "BLEND"}
            write_json(path.with_suffix(suffix + ".json"), data)
            context.scene.studio.status = "Exported " + path.name
            return {"FINISHED"}
        except Exception as exception:
            error(context, exception)
            self.report({"ERROR"}, context.scene.studio.error)
            return {"CANCELLED"}


def button(layout, action, label, icon="NONE", target=""):
    op = layout.operator("studio.action", text=label, icon=icon)
    op.action, op.target = action, target
    return op


def active_or_none(context):
    try:
        return tools.asset_collection(context)
    except ValueError:
        return None


class StudioPanel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Asset Studio"


class STUDIO_PT_Main(StudioPanel, bpy.types.Panel):
    bl_idname = "STUDIO_PT_Main"
    bl_label = "INFINIGEN ASSET STUDIO"

    def draw(self, context):
        state, layout = context.scene.studio, self.layout
        layout.prop(state, "creation_mode", expand=True)
        layout.label(text=state.status[:65], icon="TIME" if state.busy else "INFO")
        if state.busy:
            layout.progress(factor=state.progress, type="BAR", text="Native generation")
            button(layout, "CANCEL", "Cancel", "CANCEL")
        if state.error:
            box = layout.box()
            box.alert = True
            box.label(text=state.error[:65], icon="ERROR")
            box.prop(state, "show_details")
            if state.show_details:
                button(box, "DETAILS", "Open Technical Details", "TEXT")
        row = layout.row()
        row.enabled = not state.busy
        row.operator("studio.job", text="Discover assets & scene configs", icon="FILE_REFRESH").action = "discover"
        layout.prop(state, "advanced")
        if state.advanced:
            prefs = preferences(context)
            layout.prop(prefs, "source")
            layout.prop(prefs, "python")
            layout.prop(prefs, "distribution")
            layout.prop(prefs, "workspace")
            if state.version:
                data = json.loads(state.version)
                layout.label(text=f'Infinigen {data["infinigen"]} · bpy {data["blender"]}')
                layout.label(text="Commit " + data["commit"][:10])


class STUDIO_PT_Browser(StudioPanel, bpy.types.Panel):
    bl_label = "Asset Browser"
    bl_parent_id = "STUDIO_PT_Main"

    @classmethod
    def poll(cls, context):
        return context.scene.studio.creation_mode == "ASSET"

    def draw(self, context):
        state, layout = context.scene.studio, self.layout
        layout.prop(state, "search", icon="VIEWZOOM")
        layout.prop(state, "category")
        layout.prop(state, "favorites_only")
        layout.template_list("STUDIO_UL_Assets", "", state, "assets", state, "asset_index", rows=5)
        item = selected(context)
        if item:
            row = layout.row()
            row.label(text=item["category"])
            button(row, "FAVORITE_GENERATOR", "Favorite", "SOLO_ON" if state.assets[state.asset_index].favorite else "SOLO_OFF")
            if state.advanced:
                layout.label(text=item["module"])
                layout.label(text="Candidate compatibility checked on generation", icon="INFO")


class STUDIO_PT_Generation(StudioPanel, bpy.types.Panel):
    bl_label = "Generation & Variations"
    bl_parent_id = "STUDIO_PT_Main"

    @classmethod
    def poll(cls, context):
        return context.scene.studio.creation_mode == "ASSET"

    def draw(self, context):
        state, layout = context.scene.studio, self.layout
        layout.enabled = not state.busy
        layout.prop(state, "seed")
        row = layout.row(align=True)
        button(row, "PREVIOUS", "", "TRIA_LEFT")
        button(row, "SEED", "Random Seed", "FILE_REFRESH")
        button(row, "NEXT", "", "TRIA_RIGHT")
        button(row, "COPY_SEED", "", "COPYDOWN")
        layout.prop(state, "quality")
        if state.advanced:
            layout.prop(state, "preserve_edits")
        layout.operator("studio.job", text="Generate / Update Preview", icon="PLAY").action = "generate"
        button(layout, "RANDOMIZE", "Randomize Unlocked Parameters", "MOD_NOISE")
        row = layout.row(align=True)
        row.prop(state, "batch_count")
        row.operator("studio.job", text="Generate Variations", icon="DUPLICATE").action = "batch"
        if any("studio_metadata" in c for c in context.scene.collection.children):
            layout.template_icon_view(state, "variation", show_labels=True, scale=3)
        for collection in bpy.data.collections:
            if "studio_metadata" in collection and collection.name in context.scene.collection.children:
                button(layout, "SELECT", collection.name, "RADIOBUT_ON" if collection.name == state.active_collection else "RADIOBUT_OFF", collection.name)


class STUDIO_PT_Parameters(StudioPanel, bpy.types.Panel):
    bl_label = "Shape & Native Controls"
    bl_parent_id = "STUDIO_PT_Main"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return context.scene.studio.creation_mode == "ASSET"

    def draw(self, context):
        state, layout = context.scene.studio, self.layout
        layout.label(text="Enable an override to replace native sampling.", icon="INFO")
        column = layout.column()
        column.enabled = not state.busy
        for p in state.parameters:
            definition = json.loads(p.definition)
            if definition["advanced"] and not state.advanced:
                continue
            row = column.row(align=True)
            row.prop(p, "enabled", text="")
            control = row.row()
            control.enabled = p.enabled
            control.prop(p, "boolean" if p.kind == "bool" else "choice" if p.kind == "enum" else "integer" if p.kind == "int" else "number", text=p.label)
            row.prop(p, "locked", text="", icon="LOCKED" if p.locked else "UNLOCKED")
            row.operator("studio.parameter_help", text="", icon="QUESTION").tooltip = definition["tooltip"]
            if p.kind in {"float", "int"}:
                column.label(text=f'  Range {definition["minimum"]:g} – {definition["maximum"]:g}')
        collection = active_or_none(context)
        if collection:
            layout.separator()
            layout.label(text="Live Geometry Nodes · current asset")
            for obj, mod, item in tools.native_inputs(collection):
                layout.prop(mod, '["' + item.identifier + '"]', text=item.name)
        if not state.parameters and collection is None:
            layout.label(text="Generate to discover live node controls.")


class STUDIO_PT_Articulation(StudioPanel, bpy.types.Panel):
    bl_label = "Articulation & Components"
    bl_parent_id = "STUDIO_PT_Main"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return context.scene.studio.creation_mode == "ASSET"

    def draw(self, context):
        state, layout = context.scene.studio, self.layout
        collection = active_or_none(context)
        if collection is None:
            layout.label(text="Generate an articulated asset first.")
            return
        for obj in collection.all_objects:
            if not obj.get("studio_derived"):
                layout.label(text=("  ↳ " if obj.parent else "") + obj.name, icon="OUTLINER_OB_" + obj.type if obj.type in {"MESH", "EMPTY", "ARMATURE"} else "OBJECT_DATA")
        joints = tools.joints(collection)
        if not joints:
            layout.label(text="No editable native joint groups found.")
            return
        layout.prop(state, "joint_choice")
        index = min(state.joint_index, len(joints) - 1)
        obj, tree, node = joints[index]
        label = node.inputs.get("Joint Label")
        layout.label(text=f'{index + 1}/{len(joints)} · {label.default_value if label and not label.is_linked else node.name}')
        layout.label(text=node.node_tree.name.split(".")[0])
        for label_name in ("Parent Label", "Child Label"):
            socket = node.inputs.get(label_name)
            if socket and not socket.is_linked and socket.default_value:
                layout.label(text=label_name.removesuffix(" Label") + ": " + str(socket.default_value))
        for name in ("Position", "Axis", "Min", "Max", "Value", "Show Joint"):
            socket = node.inputs.get(name)
            if socket:
                if socket.is_linked:
                    layout.label(text=name + " · driven by native node graph", icon="LINKED")
                else:
                    if name == "Value" and "studio_rest" not in node:
                        node["studio_rest"] = socket.default_value
                    if name == "Value":
                        layout.prop(state, "joint_position", slider=True)
                        layout.prop(socket, "default_value", text="Native Value")
                    else:
                        layout.prop(socket, "default_value", text=name)
        row = layout.row(align=True)
        button(row, "RESET", "Reset")
        button(row, "OPEN", "Open All")
        button(row, "CLOSE", "Close All")
        button(layout, "POSE", "Random Pose", "MOD_NOISE")
        layout.label(text="Hinge angles use radians. Linked sockets stay driven.")
        layout.label(text="Some joints belong to inactive generator variants.")


class STUDIO_PT_Materials(StudioPanel, bpy.types.Panel):
    bl_label = "Materials"
    bl_parent_id = "STUDIO_PT_Main"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return context.scene.studio.creation_mode == "ASSET"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if obj and obj.active_material:
            mat = obj.active_material
            layout.label(text=mat.name, icon="MATERIAL")
            if mat.node_tree:
                for node in mat.node_tree.nodes:
                    if node.type == "BSDF_PRINCIPLED":
                        for key in ("Base Color", "Roughness", "Metallic"):
                            socket = node.inputs.get(key)
                            if socket and not socket.is_linked:
                                layout.prop(socket, "default_value", text=key)
                            else:
                                layout.label(text=key + " · procedural (Shader Editor)")
        button(layout, "MATERIAL", "Apply Random Mesh Material", "MATERIAL")
        layout.label(text="Live node material assignments may override mesh slots.")


class STUDIO_PT_GameReady(StudioPanel, bpy.types.Panel):
    bl_label = "Game Ready & Export"
    bl_parent_id = "STUDIO_PT_Main"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return context.scene.studio.creation_mode == "ASSET"

    def draw(self, context):
        state, layout = context.scene.studio, self.layout
        if state.statistics:
            stats = json.loads(state.statistics)
            for key in ("vertices", "edges", "faces", "triangles", "objects", "materials", "textures"):
                layout.label(text=key.title() + ": " + f'{stats.get(key, 0):,}')
            layout.label(text=f'Estimated mesh memory: {stats.get("estimated_mesh_memory_mb", 0):g} MB')
            if stats.get("triangles", 0) > 100000:
                layout.label(text="High triangle count for a single game asset", icon="ERROR")
        button(layout, "STATS", "Refresh Evaluated Statistics", "FILE_REFRESH")
        row = layout.row(align=True)
        row.prop(state, "scale")
        button(row, "SCALE", "Apply Scale")
        button(layout, "PIVOT", "Ground Pivot · Static Meshes")
        button(layout, "LODS", "Build Non-destructive LODs", "MOD_DECIM")
        row = layout.row(align=True)
        row.prop(state, "lod_level")
        button(row, "SHOW_LOD", "Inspect")
        row = layout.row(align=True)
        button(row, "HULL", "Convex Hulls")
        button(row, "BOX", "Box Collisions")
        layout.label(text="Collision per mesh object; joint parts may share a mesh.")
        layout.operator("studio.export", text="Export Asset…", icon="EXPORT")


def draw_thumbnail(layout, path):
    if PREVIEWS is None or not Path(path).is_file():
        return
    if path not in PREVIEWS:
        try:
            PREVIEWS.load(path, path, "IMAGE")
        except (RuntimeError, KeyError):
            return
    layout.template_icon(icon_value=PREVIEWS[path].icon_id, scale=6)


class STUDIO_PT_Library(StudioPanel, bpy.types.Panel):
    bl_label = "Presets, Projects & Asset Library"
    bl_parent_id = "STUDIO_PT_Main"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return context.scene.studio.creation_mode == "ASSET"

    def draw(self, context):
        state, layout = context.scene.studio, self.layout
        row = layout.row(align=True)
        row.operator("studio.save", text="Save Preset…").project = False
        row.operator("studio.load", text="Open Data…")
        layout.operator("studio.save", text="Save Project…", icon="FILE_BLEND").project = True
        layout.prop(state, "asset_name")
        layout.prop(state, "tags")
        collection = active_or_none(context)
        if collection:
            draw_thumbnail(layout, collection.get("studio_thumbnail", ""))
        button(layout, "SAVE_LIBRARY", "Save Favorite to Library", "SOLO_ON")
        button(layout, "LIBRARY_REFRESH", "Refresh Library", "FILE_REFRESH")
        layout.prop(state, "library_search")
        layout.prop(state, "library_favorites")
        layout.template_list("STUDIO_UL_Library", "", state, "library", state, "library_index", rows=3)
        if state.library and 0 <= state.library_index < len(state.library):
            entry = state.library[state.library_index]
            draw_thumbnail(layout, entry.thumbnail)
            row = layout.row(align=True)
            button(row, "LIBRARY_OPEN", "Open", "FILE_FOLDER")
            button(row, "LIBRARY_FAVORITE", "Favorite", "SOLO_ON" if entry.favorite else "SOLO_OFF")


class STUDIO_PT_Setup(StudioPanel, bpy.types.Panel):
    bl_label = "Setup & Diagnostics"
    bl_parent_id = "STUDIO_PT_Main"

    def draw(self, context):
        state, layout = context.scene.studio, self.layout
        manager, prefs = InfinigenInstallationManager(), preferences(context)
        try:
            active = manager.load().get("active")
        except Exception as exception:
            layout.label(text=str(exception)[:60], icon="ERROR")
            active = None
        controls = layout.column()
        controls.enabled = not state.busy
        if not active:
            controls.label(text="Infinigen is required to generate content.")
            controls.operator("studio.setup", text="Find Existing Installation", icon="VIEWZOOM").action = "detect"
            if is_extension():
                controls.label(text="Install Infinigen outside Blender first.")
                controls.label(text="See the extension setup guide.")
            else:
                controls.operator("studio.setup", text="Install Infinigen Automatically", icon="IMPORT").action = "install"
            controls.label(text="Windows worlds require WSL2 + Linux build tools.")
            controls.label(text="Setup never changes Blender's Python.")
            controls.operator("studio.setup", text="Run Host Diagnostics").action = "diagnostics"
        else:
            report = active.get("validation", {})
            controls.label(text="Infinigen " + report.get("version", "unknown"), icon="CHECKMARK" if report.get("compatible") else "ERROR")
            controls.label(text=report.get("message", "Run Diagnostics")[:60])
            controls.label(text="Managed copy" if active.get("managed") else "Existing installation")
            row = controls.row(align=True)
            row.operator("studio.setup", text="Diagnostics").action = "diagnostics"
            row.operator("studio.setup", text="Self Test").action = "selftest"
            if active.get("managed") and not is_extension():
                row = controls.row(align=True)
                row.operator("studio.setup", text="Repair").action = "repair"
                row.operator("studio.setup", text="Install Recommended").action = "update"
                controls.operator("studio.setup", text="Remove Managed Dependency", icon="TRASH").action = "remove"
            row = controls.row(align=True)
            row.operator("studio.utility", text="Open Infinigen Folder").action = "source"
            row.operator("studio.utility", text="Check Compatible Updates").action = "check_updates"
            hardware = report.get("hardware", {})
            if hardware:
                controls.label(text=f'RAM {hardware.get("ram_gb", "?")} GB · free disk {hardware.get("disk_free_gb", "?")} GB')
                for device in hardware.get("cycles_devices", []):
                    controls.label(text=f'{device["type"]}: {device["name"]}'[:65])
                controls.label(text="CPU terrain; Cycles devices are separate.")
        if state.advanced or not active:
            controls.separator()
            controls.label(text="Select existing installation (advanced)")
            for key in ("backend", "distribution", "source", "python", "allow_mismatch"):
                if key != "distribution" or prefs.backend == "WSL":
                    controls.prop(prefs, key)
            controls.operator("studio.setup", text="Validate & Use Selected Installation").action = "existing"
            controls.prop(prefs, "workspace")
        row = layout.row(align=True)
        row.operator("studio.utility", text="Copy Diagnostics", icon="COPYDOWN").action = "diagnostics_copy"
        row.operator("studio.utility", text="View Last Log", icon="TEXT").action = "log"
        layout.operator("studio.utility", text="Open Output / Log Folder").action = "outputs"


class STUDIO_PT_Scenes(StudioPanel, bpy.types.Panel):
    bl_label = "Scene Generation"
    bl_parent_id = "STUDIO_PT_Main"

    @classmethod
    def poll(cls, context):
        return context.scene.studio.creation_mode in {"ROOM", "WORLD"}

    def draw(self, context):
        state, layout = context.scene.studio, self.layout
        controls = layout.column()
        controls.enabled = not state.busy
        controls.prop(state, "room_type" if state.creation_mode == "ROOM" else "world_preset")
        controls.prop(state, "seed")
        row = controls.row(align=True)
        button(row, "PREVIOUS", "Previous", "TRIA_LEFT")
        button(row, "SEED", "New Seed", "FILE_REFRESH")
        button(row, "COPY_SEED", "Copy", "COPYDOWN")
        controls.prop(state, "scene_quality")
        controls.prop(state, "render_device")
        if state.creation_mode == "ROOM":
            controls.prop(state, "room_height")
            controls.prop(state, "room_clutter")
            controls.prop(state, "room_camera")
            controls.label(text="Native floor plan; furniture limited to selected type.")
            controls.label(text="Exact room dimensions and style are not mapped.")
        else:
            controls.prop(state, "override_trees")
            if state.override_trees:
                controls.prop(state, "tree_density")
            controls.prop(state, "override_sun")
            if state.override_sun:
                controls.prop(state, "sun_elevation")
            controls.label(text="Complete terrain + populated assets + fine terrain.")
        controls.label(text="Scene generation can require substantial RAM.", icon="INFO")
        controls.label(text="Final quality increases geometry and solver work.")
        controls.operator("studio.job", text="Generate Room" if state.creation_mode == "ROOM" else "Generate World", icon="PLAY").action = "scene"
        row = controls.row(align=True)
        row.operator("studio.scene_preset_save", text="Save Preset…")
        row.operator("studio.scene_preset_load", text="Load Preset…")
        if state.scene_output:
            layout.operator("studio.utility", text="Open Generated Scene", icon="FILE_BLEND").action = "scene_open"
            layout.label(text="Opens in a separate Blender window.")
        layout.label(text="Edit and export through Blender's native tools.")
        layout.label(text="Partial solver regeneration is unsupported.")
        layout.label(text="Scene seed reproducibility varies by platform.")
        if state.advanced:
            controls.prop(state, "config_search")
            controls.prop(state, "scene_config_choice")
            controls.operator("studio.utility", text="Add Selected Config").action = "config_add"
            controls.operator("studio.utility", text="View Config / Pipeline Catalogue").action = "configs"
            controls.prop(state, "extra_configs")
            controls.prop(state, "scene_overrides")
            row = controls.row(align=True)
            row.operator("studio.utility", text="Edit Overrides").action = "overrides_edit"
            row.operator("studio.utility", text="Apply Overrides").action = "overrides_apply"
            controls.label(text="Tasks: coarse" if state.creation_mode == "ROOM" else "Tasks: coarse → populate + fine terrain")
            controls.label(text="Config paths: see discovered catalogue in Details.")
            for config in json.loads(state.scene_configs or "{}").get("world_presets", []):
                controls.label(text=config["id"].split("/")[-1])


class STUDIO_PT_History(StudioPanel, bpy.types.Panel):
    bl_label = "Generation History"
    bl_parent_id = "STUDIO_PT_Main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        try:
            for entry in history.records(workspace(context))[:12]:
                request = entry["request"]
                box = layout.box()
                label = request.get("preset", request.get("generator", "Asset")).split("/")[-1]
                box.label(text=f'{request["seed"]} · {label}'[:65])
                row = box.row(align=True)
                for action, label in (("history_regenerate", "Regenerate"), ("history_open", "Open"), ("history_folder", "Folder"), ("history_favorite", "★" if entry["favorite"] else "☆")):
                    operator = row.operator("studio.utility", text=label)
                    operator.action, operator.target = action, entry["id"]
                box.operator("studio.scene_preset_save", text="Save This Preset…").target = entry["id"]
        except Exception:
            layout.label(text="History unavailable; check output folder permissions.")


CLASSES = (STUDIO_Preferences, STUDIO_Parameter, STUDIO_Asset, STUDIO_LibraryEntry, STUDIO_State,
    STUDIO_UL_Assets, STUDIO_UL_Library, STUDIO_OT_Job, STUDIO_OT_Action, STUDIO_OT_Save, STUDIO_OT_Load,
    STUDIO_OT_Export, STUDIO_OT_ParameterHelp, STUDIO_PT_Main, STUDIO_PT_Browser, STUDIO_PT_Generation, STUDIO_PT_Parameters,
    STUDIO_PT_Articulation, STUDIO_PT_Materials, STUDIO_PT_GameReady, STUDIO_PT_Library,
    STUDIO_PT_Setup, STUDIO_PT_Scenes, STUDIO_PT_History) + setup_ui.CLASSES + scene_ui.CLASSES


@bpy.app.handlers.persistent
def on_load(_):
    state = bpy.context.scene.studio
    state.busy = False
    if state.catalogue:
        restore_catalogue(state)
    else:
        try:
            path = workspace(bpy.context) / "catalogue.json"
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf8"))
                state.scene_configs = json.dumps(data.get("configs", {}))
                load_catalogue(bpy.context, data)
        except Exception:
            logger.exception("Could not restore generator catalogue")
    try:
        refresh_library(bpy.context)
    except Exception:
        logger.exception("Could not restore asset library")


def register():
    global PREVIEWS, BOOTSTRAP
    from bpy.utils import previews
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.studio = PointerProperty(type=STUDIO_State)
    PREVIEWS = previews.new()
    EXPORT_FORMATS[:] = [("BLEND", "Blender · .blend", "Preserve live procedural data")]
    for identifier, label, module, operator in (("GLB", "glTF · .glb", "export_scene", "gltf"), ("FBX", "FBX · .fbx", "export_scene", "fbx"), ("OBJ", "Wavefront · .obj", "wm", "obj_export"), ("USD", "USD · .usdc", "wm", "usd_export")):
        try:
            getattr(getattr(bpy.ops, module), operator).get_rna_type()
            EXPORT_FORMATS.append((identifier, label, "Evaluated static mesh export"))
        except (AttributeError, RuntimeError):
            pass
    bpy.app.handlers.load_post.append(on_load)
    def restore_after_enable():
        on_load(None)
        return None
    BOOTSTRAP = restore_after_enable
    bpy.app.timers.register(restore_after_enable, first_interval=0.5)


def unregister():
    global PREVIEWS, BOOTSTRAP
    if BOOTSTRAP is not None and bpy.app.timers.is_registered(BOOTSTRAP):
        bpy.app.timers.unregister(BOOTSTRAP)
    BOOTSTRAP = None
    if RUNNING:
        RUNNING.cancel(bpy.context)
    if on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_load)
    if PREVIEWS is not None:
        from bpy.utils import previews
        previews.remove(PREVIEWS)
        PREVIEWS = None
    del bpy.types.Scene.studio
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    CATALOGUE.clear()
    ENUM_CACHE.clear()
    VARIATION_CACHE.clear()
    JOINT_ENUM_CACHE.clear()
