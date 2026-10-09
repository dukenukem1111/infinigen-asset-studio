# Blender Extensions submission

## Package and listing

Upload `dist/infinigen_asset_studio-0.2.1.zip` as an add-on extension. The manifest
declares Windows x64 and Linux x64, Blender 4.2.x, GPL-3.0-or-later, and file and
clipboard permissions. The source is in the public project repository.

Suggested description:

> Generate and customize procedural assets, furnished indoor scenes and nature
> scenes through an existing external Infinigen 1.19.0 installation. Explore
> seeded controls, live Geometry Nodes, supported articulated joints, variations,
> presets and favorites. Keep native .blend outputs or export evaluated meshes.
>
> Requires Blender 4.2.x, an external Python 3.11 runtime with bpy 4.2.0 and
> Infinigen's dependencies. On Windows, scene generation requires WSL2. You must
> install Infinigen outside Blender before generating anything; this extension
> does not install dependencies. Full scenes can take several minutes and require
> substantial RAM. Read the setup guide before installing.
>
> Discovery includes unverified generator candidates. Arbitrary partial scene
> regeneration, procedural shader baking and simulation exports are unsupported.
> This independent interface is not endorsed by Princeton or Blender.

## Build

Run:

```text
python scripts/build_extension.py --blender <Blender-4.2-executable>
```

The builder stages a separate extension without changing the legacy package.
It removes legacy `bl_info`, replaces the dependency installer with a validation-only
worker, and adapts external worker imports for Blender's extension namespace.
Blender's official extension builder and validator produce and check the ZIP.
The SHA-256 checksum is written beside it.

Run real installation and generation checks with
`python scripts/run_extension_validation.py --blender <Blender-4.2-executable>`.
The runner creates and checks an isolated Blender preferences directory before
allowing the tests to save preferences. Results are summarized in [testing.md](testing.md).

The GPL text is stored in `extension/COPYING`; original BSD notices are retained.
No engine, runtime, wheels, generated scenes or preview images are bundled.

## Publication

Sign in with Blender ID at the [Blender Extensions platform](https://extensions.blender.org/)
and choose **Upload your Extension**. Upload the ZIP, complete the listing and
submit it for moderator review. Successful package validation is not approval;
the listing becomes public only after the moderation process.

Review the [terms of service](https://extensions.blender.org/terms-of-service/) and
[add-on guidelines](https://developer.blender.org/docs/handbook/extensions/addon_guidelines/).
The standalone dependency installer is outside the extension because the official
repository prohibits extensions from installing Python modules or pip packages.

Submission status: not submitted. A signed-in Blender ID is required.
