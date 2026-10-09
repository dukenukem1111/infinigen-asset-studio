# Changelog

## Extension 0.2.1 (submission candidate)

Added a Blender Extensions manifest, GPL distribution with preserved BSD notices,
official Blender package build and validation, and an existing-installation-only
setup workflow. The extension omits dependency installation code. Fixed scene
export and separate scene opening to use Blender's extension namespace. The legacy
add-on retains managed installation, with downloads respecting Allow Online Access.

## 0.2.0

Added a persistent installation registry, first-run setup, pinned archive-based managed
installation, diagnostics/self-test/repair, Room and World adapters, scene presets,
history, output metadata, a versioned release builder and GitHub Actions. Existing
factory controls, articulation, library, LOD/collision tools and exports are retained.

## 0.1.0

Added a native Blender asset browser, isolated generation, seeded controls, native joint
inspection, a reusable library, game preparation and evaluated mesh exports.
