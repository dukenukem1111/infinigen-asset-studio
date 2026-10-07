# Contributing

Use Python 3.10+ for pure integration tests and Blender 4.2.0 for host validation.
The external generation runtime must use Python 3.11 and bpy 4.2.0. Do not install
engine dependencies into your interactive Blender interpreter.

Run `python -m unittest discover -s tests -p "test_*.py"` for pure tests. Tests
requiring a real engine are named separately and require an explicitly configured
local environment. Build the release ZIP using `python scripts/build_release.py`.

For developer launchers, set `ASSET_STUDIO_BLENDER` or create an ignored
`runtime/development.json` containing your local Blender executable and runtime
paths. Use the Setup panel to persist a validated installation. Never commit this
file, credentials, generated .blend files, binaries, dependencies or caches.

Preserve the existing worker metadata contract and use source inspection before
adding gin mappings. New engine versions require capability and regression testing;
do not update the pinned commit based only on a newer release number. Asset checks
must still cover native articulation, reconstruction from seeds and parameters, export cleanup
and restart. Scene checks must produce actual furnished rooms and populated fine
terrain, not just proxy geometry. Installer checks must use a clean owned directory.

Release tags are `vX.Y.Z` and must match `compatibility.json` and `bl_info`. The tag
workflow builds the ZIP and checksum and attaches them to GitHub Releases. This
project is hosted at [infinigen-asset-studio](https://github.com/dukenukem1111/infinigen-asset-studio).
