"""Infinigen Asset Studio: artist-facing Blender integration."""

bl_info = {
    "name": "Infinigen Asset Studio",
    "author": "Asset Studio contributors",
    "version": (0, 2, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Asset Studio",
    "description": "Browse, generate, articulate and export installed Infinigen assets",
    "category": "Add Mesh",
}


def register():
    from . import addon
    addon.register()


def unregister():
    from . import addon
    addon.unregister()
