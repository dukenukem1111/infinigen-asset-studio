# Infinigen Asset Studio extension setup

The Blender extension connects to an **existing external Infinigen installation**.
It does not download or install Python packages, Infinigen, Blender, WSL or other
add-ons. Prepare the generation environment outside Blender before using it.

## Requirements

- Blender 4.2.x on Windows x64 or Linux x64. Other host versions are not advertised
  until tested. The external worker must use bpy exactly 4.2.0.
- Infinigen 1.19.0 at commit `01c39c7f7adcf7363ccbcc57c64410c69f4a4e7c`, with
  Python 3.11 and the dependencies needed for your chosen asset or scene.
- On Windows, room and world generation uses an existing WSL2 Linux distribution.
  Nature scenes additionally require Infinigen's native CPU terrain libraries.
- Enough disk space and RAM for generated scenes. Complete scenes can take several
  minutes and use substantially more memory than individual assets.

Follow the [pinned upstream installation instructions](https://github.com/princeton-vl/infinigen/blob/01c39c7f7adcf7363ccbcc57c64410c69f4a4e7c/docs/Installation.md)
outside Blender. If you use the Asset Studio standalone dependency installer, run
`python scripts/install_dependencies.py` from a downloaded checkout of
[the project](https://github.com/dukenukem1111/infinigen-asset-studio).
On Windows, pass `--distribution <WSL-name>` if needed. This is a separate user-run
command; the extension neither bundles nor launches the installer.

## Install and connect

1. Disable the legacy Infinigen Asset Studio add-on before enabling this extension.
   The two distributions provide the same operators and must not be enabled together.
2. Install `infinigen_asset_studio-0.2.1.zip` through Blender's **Get Extensions >
   Install from Disk** menu, then enable **Infinigen Asset Studio**.
3. Open the 3D View sidebar with **N**, then select **Asset Studio**.
4. In **Setup & Diagnostics**, choose **Find Existing Installation**, or enter
   your backend, source folder, worker Python path and WSL distribution manually.
   For WSL, use Linux paths for the source and worker interpreter.
5. Click **Validate & Use Selected Installation**. A healthy, matching environment
   is activated only after validation. **Self Test** generates a small test asset
   in the selected external runtime.
6. Click **Discover assets & scene configs** and choose Asset, Room or World.
   Set a seed and generate. Unsupported generators report their errors individually.

Installation, dependency repair, dependency updates and dependency removal must be
performed outside Blender. Those operations are unavailable in this extension.
Diagnostics, generation, presets, history, articulation and exports remain available.

## Files and permissions

The extension requests file access to read the existing engine and write outputs,
presets, library entries and logs. It requests clipboard access for explicit seed
and diagnostics copy actions. It makes no network requests and requests no network
permission. Any models or resources needed by your external engine must already
be available locally.

The default installation registry and output directory is
`%LOCALAPPDATA%/InfinigenAssetStudio` on Windows or
`$XDG_DATA_HOME/InfinigenAssetStudio` (falling back to
`~/.local/share/InfinigenAssetStudio`) on Linux. It can also be overridden with
`ASSET_STUDIO_DATA_DIR`. Nothing is written into the installed extension directory.
An existing Asset Studio configuration and library can be reused.

**Open Generated Scene** launches a separate Blender process with the installed
extension enabled. Save edits there; unsaved work in the original window is retained.
When using a custom extension repository, save its repository configuration in
Blender Preferences before opening a generated scene in another window.

## Limitations and support

The discovery catalog contains candidates, not a guarantee that every generator
works. Room and World use native upstream solvers; arbitrary partial regeneration
is unsupported. External mesh exports may lose procedural shaders, instances and
articulation. Native .blend files preserve those features.

See the [project documentation](https://github.com/dukenukem1111/infinigen-asset-studio#readme)
and [report issues](https://github.com/dukenukem1111/infinigen-asset-studio/issues).
Diagnostics include local paths; review them before sharing.

The extension distribution is GPL-3.0-or-later; see `COPYING`. Original BSD-3-Clause
notices are preserved in `LICENSE-BSD`. The existing legacy distribution remains
BSD-3-Clause. Infinigen is developed by Princeton Vision & Learning Lab and remains
external. This independent interface is not endorsed by Princeton or Blender.
