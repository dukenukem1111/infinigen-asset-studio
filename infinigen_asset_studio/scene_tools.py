"""Blender scene tools. All functions must execute on Blender's main thread."""
import json
import random
from pathlib import Path
import bpy
from mathutils import Vector


def asset_collection(context):
    name = context.scene.studio.active_collection
    collection = bpy.data.collections.get(name)
    if collection is None or "studio_metadata" not in collection:
        raise ValueError("Generate or open a Studio asset first.")
    return collection


def statistics(collection):
    graph = bpy.context.evaluated_depsgraph_get()
    totals = dict(vertices=0, edges=0, faces=0, triangles=0, objects=sum(not o.get("studio_derived") for o in collection.all_objects), materials=0, textures=0)
    materials, textures = set(), set()
    for obj in collection.all_objects:
        if obj.type != "MESH" or obj.get("studio_derived"):
            continue
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            totals["vertices"] += len(mesh.vertices)
            totals["edges"] += len(mesh.edges)
            totals["faces"] += len(mesh.polygons)
            totals["triangles"] += len(mesh.loop_triangles)
            for material in mesh.materials:
                if material:
                    materials.add(material.name)
                    if material.node_tree:
                        textures.update(n.image.name for n in material.node_tree.nodes if n.type == "TEX_IMAGE" and n.image)
        finally:
            evaluated.to_mesh_clear()
    totals["materials"], totals["textures"] = len(materials), len(textures)
    totals["estimated_mesh_memory_mb"] = round((totals["vertices"] * 32 + totals["triangles"] * 12 + totals["edges"] * 8) / 1048576, 2)
    return totals


def joints(collection):
    """Inspect native joint node groups, including nested groups; preserve live RNA."""
    found, visited = [], set()
    def walk(tree, owner):
        if tree is None or tree.as_pointer() in visited:
            return
        visited.add(tree.as_pointer())
        for node in tree.nodes:
            if node.type != "GROUP" or not node.node_tree:
                continue
            group = node.node_tree.name.lower()
            if any(term in group for term in ("hinge_joint", "sliding_joint", "ball_joint")):
                if node.inputs.get("Value"):
                    found.append((owner, tree, node))
            else:
                walk(node.node_tree, owner)
    for obj in collection.all_objects:
        for mod in obj.modifiers:
            if mod.type == "NODES":
                walk(mod.node_group, obj)
    return found


def pose(collection, action, seed=0):
    rng = random.Random(seed)
    changed = 0
    for obj, tree, node in joints(collection):
        value = node.inputs["Value"]
        if value.is_linked:
            continue
        lo = node.inputs.get("Min")
        hi = node.inputs.get("Max")
        low, high = (lo.default_value if lo else 0), (hi.default_value if hi else 1)
        if action == "RESET":
            target = node.get("studio_rest", value.default_value)
        else:
            if "studio_rest" not in node:
                node["studio_rest"] = value.default_value
            target = high if action == "OPEN" else low if action == "CLOSE" else rng.uniform(low, high)
        value.default_value = target
        tree.interface_update(bpy.context)
        obj.update_tag()
        changed += 1
    return changed


def select_collection(context, collection):
    for obj in context.selected_objects:
        obj.select_set(False)
    # Keep variations intact while presenting one clear preview at a time.
    for other in context.scene.collection.children:
        if "studio_metadata" in other and other != collection:
            for obj in other.all_objects:
                if obj.name in context.view_layer.objects:
                    obj.hide_set(True)
    for obj in collection.all_objects:
        if obj.name in context.view_layer.objects:
            derived = bool(obj.get("studio_derived"))
            obj.hide_set(derived)
            if not derived:
                obj.select_set(True)
    meshes = [o for o in collection.all_objects if o.type == "MESH" and not o.get("studio_derived")]
    if meshes:
        context.view_layer.objects.active = meshes[0]
    context.scene.studio.active_collection = collection.name
    if context.area and context.area.type == "VIEW_3D":
        try:
            bpy.ops.view3d.view_selected(use_all_regions=False)
        except RuntimeError:
            pass


def append_asset(path, name="Studio Asset"):
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        if name not in source.collections:
            raise ValueError("This file does not contain the requested Studio collection.")
        target.collections = [name]
    collection = target.collections[0]
    if "studio_metadata" not in collection:
        bpy.data.collections.remove(collection)
        raise ValueError("This file is missing Studio reconstruction metadata.")
    bpy.context.scene.collection.children.link(collection)
    metadata = json.loads(collection["studio_metadata"])
    collection.name = metadata.get("name", "Studio Asset")
    return collection


def native_inputs(collection):
    for obj in collection.all_objects:
        for mod in obj.modifiers:
            if mod.type == "NODES" and mod.node_group:
                for item in mod.node_group.interface.items_tree:
                    if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.socket_type in {
                        "NodeSocketFloat", "NodeSocketInt", "NodeSocketBool", "NodeSocketVector", "NodeSocketColor", "NodeSocketString"}:
                        if item.identifier in mod:
                            yield obj, mod, item


def snapshot(collection):
    """Record explicit pose/socket edits alongside the native .blend."""
    metadata = json.loads(collection["studio_metadata"])
    metadata["native_inputs"] = [{"object": obj.name, "modifier": mod.name, "name": item.name,
        "identifier": item.identifier, "value": list(mod[item.identifier]) if hasattr(mod[item.identifier], "to_list") else mod[item.identifier]}
        for obj, mod, item in native_inputs(collection)]
    metadata["joints"] = []
    for obj, tree, node in joints(collection):
        values = {}
        for key in ("Value", "Min", "Max", "Axis", "Position", "Show Joint"):
            socket = node.inputs.get(key)
            if socket and not socket.is_linked:
                value = socket.default_value
                values[key] = list(value) if hasattr(value, "__len__") and not isinstance(value, str) else value
        metadata["joints"].append({"object": obj.name, "tree": tree.name, "node": node.name, "values": values})
    metadata["transforms"] = [{"name": o.name, "matrix_world": [list(row) for row in o.matrix_world]} for o in collection.all_objects if not o.get("studio_derived")]
    baseline = metadata.get("generation_baseline", {})
    old_inputs = baseline.get("native_inputs", [])
    old_joints = baseline.get("joints", [])
    metadata["native_edits"] = {"generator": metadata["generator"], "native_inputs": [], "joints": []}
    for index, entry in enumerate(metadata["native_inputs"]):
        if index < len(old_inputs) and entry["value"] != old_inputs[index]["value"]:
            # Stable input index prevents object renaming from losing the edited control.
            metadata["native_edits"]["native_inputs"].append(dict(entry, input_index=index))
    for index, entry in enumerate(metadata["joints"]):
        old_values = old_joints[index]["values"] if index < len(old_joints) else {}
        changes = {key: value for key, value in entry["values"].items() if key in old_values and value != old_values[key]}
        metadata["native_edits"]["joints"].append(dict(entry, values=changes))
    metadata["statistics"] = statistics(collection)
    return metadata


def restore_edits(collection, metadata):
    """Reapply saved node/socket edits using stable order/name fallbacks."""
    saved_inputs = metadata.get("native_inputs", [])
    for index, (obj, mod, item) in enumerate(native_inputs(collection)):
        match = next((p for p in saved_inputs if p["modifier"] == mod.name and p["identifier"] == item.identifier and p["object"] == obj.name), None)
        if match is None:
            match = next((p for p in saved_inputs if p.get("input_index") == index and p["name"] == item.name), None)
        if match:
            mod[item.identifier] = match["value"]
            obj.update_tag()
    saved_joints = metadata.get("joints", [])
    for index, (obj, tree, node) in enumerate(joints(collection)):
        if index >= len(saved_joints):
            break
        for key, value in saved_joints[index]["values"].items():
            socket = node.inputs.get(key)
            if socket and not socket.is_linked:
                socket.default_value = value
        tree.interface_update(bpy.context)
        obj.update_tag()
    bpy.context.view_layer.update()


def evaluated_copy(obj, collection):
    mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()), preserve_all_data_layers=True, depsgraph=bpy.context.evaluated_depsgraph_get())
    copy = bpy.data.objects.new(obj.name + "_copy", mesh)
    copy.matrix_world = obj.matrix_world.copy()
    collection.objects.link(copy)
    return copy


def make_lods(collection):
    originals = [o for o in collection.all_objects if o.type == "MESH" and not o.get("studio_derived")]
    for level, ratio in enumerate((0.5, 0.25, 0.1), 1):
        for obj in originals:
            copy = evaluated_copy(obj, collection)
            copy.name = obj.name + f"_LOD{level}"
            copy["studio_derived"] = "LOD"
            copy["studio_lod"] = level
            mod = copy.modifiers.new("LOD simplification", "DECIMATE")
            mod.ratio = ratio
            copy.hide_set(True)
            copy.hide_render = True


def make_collision(collection, mode):
    import bmesh
    originals = [o for o in collection.all_objects if o.type == "MESH" and not o.get("studio_derived")]
    for obj in originals:
        if mode == "HULL":
            copy = evaluated_copy(obj, collection)
            bm = bmesh.new()
            try:
                bm.from_mesh(copy.data)
                result = bmesh.ops.convex_hull(bm, input=list(bm.verts), use_existing_faces=False)
                unused = list(set(result.get("geom_interior", []) + result.get("geom_unused", [])))
                if unused:
                    bmesh.ops.delete(bm, geom=unused, context="VERTS")
                bm.to_mesh(copy.data)
            finally:
                bm.free()
        else:
            bounds = [Vector(c) for c in obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).bound_box]
            low = Vector(tuple(min(v[i] for v in bounds) for i in range(3)))
            high = Vector(tuple(max(v[i] for v in bounds) for i in range(3)))
            mesh = bpy.data.meshes.new("Collision box")
            mesh.from_pydata([(x, y, z) for x in (low.x, high.x) for y in (low.y, high.y) for z in (low.z, high.z)], [],
                            [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])
            copy = bpy.data.objects.new("Collision box", mesh)
            collection.objects.link(copy)
            copy.matrix_world = obj.matrix_world.copy()
        copy.name = "UCX_" + obj.name
        copy["studio_derived"] = "COLLISION"
        copy.display_type = "WIRE"
        copy.hide_render = True


def ground_pivot(collection):
    """Move origins of static objects without changing geometry/world transforms."""
    graph = bpy.context.evaluated_depsgraph_get()
    meshes = [o for o in collection.all_objects if o.type == "MESH" and not o.get("studio_derived")]
    if any(o.modifiers or o.parent or o.children or o.constraints for o in meshes):
        raise ValueError("Ground pivot is available for static meshes without modifiers/parents. Live procedural and articulated assets retain their native pivot.")
    for obj in meshes:
        coords = [obj.matrix_world @ Vector(c) for c in obj.evaluated_get(graph).bound_box]
        world = Vector(((min(v.x for v in coords) + max(v.x for v in coords)) / 2,
                        (min(v.y for v in coords) + max(v.y for v in coords)) / 2, min(v.z for v in coords)))
        delta = obj.matrix_world.inverted() @ world
        obj.data = obj.data.copy()
        for v in obj.data.vertices:
            v.co -= delta
        obj.matrix_world.translation = world


def save_blend(collection, path):
    metadata = snapshot(collection)
    collection["studio_metadata"] = json.dumps(metadata)
    bpy.data.libraries.write(str(path), {collection}, fake_user=True, compress=True)
    return metadata


def export_asset(context, collection, path, format, preset, include_derived=False):
    """Mesh export operates on evaluated disposable copies, preserving source nodes."""
    if format == "BLEND":
        return save_blend(collection, path)
    old_active = context.view_layer.objects.active
    old_selected = list(context.selected_objects)
    temp = bpy.data.collections.new("Studio export temporary")
    context.scene.collection.children.link(temp)
    copies = []
    try:
        for obj in collection.all_objects:
            if obj.type == "MESH" and (include_derived or not obj.get("studio_derived")):
                copy = evaluated_copy(obj, temp)
                copy.name = obj.name + "_export"
                copies.append(copy)
        if not copies:
            raise ValueError("This asset has no exportable mesh geometry.")
        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in copies:
            obj.select_set(True)
        context.view_layer.objects.active = copies[0]
        if format == "GLB":
            result = bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, export_yup=True, export_extras=False)
        elif format == "FBX":
            result = bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, axis_forward="-Z" if preset in {"UNITY", "GODOT"} else "-Y",
                axis_up="Y" if preset in {"UNITY", "GODOT"} else "Z", apply_unit_scale=True, bake_anim=False, path_mode="AUTO")
        elif format == "OBJ":
            result = bpy.ops.wm.obj_export(filepath=str(path), export_selected_objects=True)
        elif format == "USD":
            result = bpy.ops.wm.usd_export(filepath=str(path), selected_objects_only=True)
        else:
            raise ValueError("This export format is not supported.")
        if "FINISHED" not in result:
            raise RuntimeError("Blender did not complete the export.")
    finally:
        for obj in copies:
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        bpy.data.collections.remove(temp)
        for obj in old_selected:
            if obj.name in context.view_layer.objects:
                obj.select_set(True)
        context.view_layer.objects.active = old_active
    return snapshot(collection)
