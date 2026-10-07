"""Scene-level tools operate on generated files or explicitly selected meshes."""
import json
from pathlib import Path
import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy_extras.io_utils import ExportHelper
from . import scene_tools
from .core import write_json


class STUDIO_OT_SceneTools(bpy.types.Operator):
    bl_idname = "studio.scene_tools"
    bl_label = "Scene Preparation"
    bl_options = {"REGISTER", "UNDO"}
    action: StringProperty()

    def invoke(self, context, event):
        if self.action == "transforms":
            return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def execute(self, context):
        from . import addon
        try:
            if self.action == "statistics":
                value = scene_tools.statistics(context.scene.collection)
                context.scene.studio.statistics = json.dumps(value)
                context.scene.studio.status = f'Geometry: {value.get("vertices", "?")} vertices · {value.get("triangles", "?")} triangles'
                return {"FINISHED"}
            if self.action == "pack":
                bpy.ops.file.pack_all()
                context.scene.studio.status = "External resources packed; save a scene copy to retain them"
                return {"FINISHED"}
            if self.action == "transforms":
                return bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
            objects = [obj for obj in context.selected_objects if obj.type == "MESH" and not obj.get("studio_derived")]
            if not objects:
                raise ValueError("Select original mesh objects for LOD or collision copies")
            staging = bpy.data.collections.new("Studio selected source staging")
            context.scene.collection.children.link(staging)
            try:
                for obj in objects:
                    staging.objects.link(obj)
                context.view_layer.update()
                if self.action == "lod":
                    scene_tools.make_lods(staging)
                elif self.action == "collision":
                    scene_tools.make_collision(staging, "HULL")
                else:
                    raise ValueError("Unknown scene preparation action")
                derived = bpy.data.collections.get("Studio Scene Derived") or bpy.data.collections.new("Studio Scene Derived")
                if derived.name not in context.scene.collection.children:
                    context.scene.collection.children.link(derived)
                for obj in list(staging.objects):
                    if obj not in objects:
                        derived.objects.link(obj)
                context.scene.studio.status = "Derived copies created for selected meshes; original objects preserved"
            finally:
                bpy.data.collections.remove(staging)
            return {"FINISHED"}
        except Exception as exception:
            addon.error(context, exception)
            return {"CANCELLED"}


class STUDIO_OT_SceneExport(bpy.types.Operator, ExportHelper):
    bl_idname = "studio.scene_export"
    bl_label = "Export Scene Copy"
    filename_ext = ""
    format: EnumProperty(items=lambda self, context: __import__("infinigen_asset_studio.addon", fromlist=["EXPORT_FORMATS"]).EXPORT_FORMATS)
    preset: EnumProperty(name="Target", items=[("GENERIC", "Generic", "Native coordinate system"), ("UNITY", "Unity", "FBX Y up / -Z forward"), ("UNREAL", "Unreal", "FBX Z up / -Y forward"), ("GODOT", "Godot", "glTF Y up recommended")], default="GENERIC")
    acknowledge: BoolProperty(name="I understand procedural shaders, instances and articulation may not survive", default=False)

    def draw(self, context):
        self.layout.prop(self, "format")
        self.layout.prop(self, "preset")
        if self.format != "BLEND":
            self.layout.label(text="Native exporter; procedural shaders are not baked.", icon="INFO")
            self.layout.prop(self, "acknowledge")

    def execute(self, context):
        from . import addon
        try:
            if self.format != "BLEND" and not self.acknowledge:
                raise ValueError("Acknowledge format limitations or choose .blend")
            suffix = {"BLEND": ".blend", "GLB": ".glb", "FBX": ".fbx", "OBJ": ".obj", "USD": ".usdc"}[self.format]
            path = Path(self.filepath).with_suffix(suffix)
            if path.exists() or path.with_suffix(suffix + ".json").exists():
                raise FileExistsError("Choose a new filename to preserve the existing scene and metadata")
            if self.format == "BLEND":
                result = bpy.ops.wm.save_as_mainfile(filepath=str(path), copy=True, check_existing=False)
            elif self.format == "GLB":
                result = bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", export_yup=True, export_extras=False)
            elif self.format == "FBX":
                result = bpy.ops.export_scene.fbx(filepath=str(path), axis_forward="-Z" if self.preset in {"UNITY", "GODOT"} else "-Y",
                    axis_up="Y" if self.preset in {"UNITY", "GODOT"} else "Z", bake_anim=False)
            elif self.format == "OBJ":
                result = bpy.ops.wm.obj_export(filepath=str(path))
            else:
                result = bpy.ops.wm.usd_export(filepath=str(path))
            if "FINISHED" not in result:
                raise RuntimeError("Native scene exporter did not complete")
            write_json(path.with_suffix(suffix + ".json"), {"schema_version": 1, "mode": context.scene.get("studio_mode", context.scene.studio.creation_mode),
                "seed": context.scene.get("studio_seed", context.scene.studio.seed), "format": self.format, "target": self.preset,
                "configs": context.scene.get("studio_configs", "[]"), "overrides": context.scene.get("studio_overrides", "[]")})
            context.scene.studio.status = "Saved scene copy " + path.name
            return {"FINISHED"}
        except Exception as exception:
            addon.error(context, exception)
            return {"CANCELLED"}


class STUDIO_PT_SceneTools(bpy.types.Panel):
    bl_label = "Scene Export & Preparation"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Asset Studio"
    bl_parent_id = "STUDIO_PT_Main"

    @classmethod
    def poll(cls, context):
        return bool(context.scene.get("studio_mode"))

    def draw(self, context):
        layout = self.layout
        layout.operator("studio.scene_export", text="Save / Export Scene Copy…", icon="EXPORT")
        layout.operator("studio.scene_tools", text="Mesh Statistics").action = "statistics"
        layout.operator("studio.scene_tools", text="Pack External Resources").action = "pack"
        layout.label(text="Selected original meshes only:")
        row = layout.row(align=True)
        row.operator("studio.scene_tools", text="LOD Copies").action = "lod"
        row.operator("studio.scene_tools", text="Collision Copies").action = "collision"
        layout.operator("studio.scene_tools", text="Apply Selected Rotation / Scale…").action = "transforms"
        layout.label(text="Applying transforms changes selected originals.")
        layout.label(text="Realize instances and bake shaders as needed.")
        layout.label(text="Statistics exclude implicit instance multiplication.")


CLASSES = (STUDIO_OT_SceneTools, STUDIO_OT_SceneExport, STUDIO_PT_SceneTools)
