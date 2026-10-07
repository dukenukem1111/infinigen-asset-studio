# Dependency architecture

The interactive add-on never installs packages into Blender with pip. Existing asset generation
continues through `bridge.Job` and `worker.py`. Scene orchestration runs in the
same external environment and starts independent native scene task processes.
All bpy calls occur on each process's main thread. The host polls with modal
timers; cancellation marks the job and terminates its process group on Linux/WSL.

`InfinigenInstallationManager` owns `configuration.json` outside the add-on.
It contains the active backend, WSL distribution, source, interpreter, managed
ownership and validation report. The source and interpreter fields in Preferences are staging
inputs until **Validate & Use** succeeds. Workers receive a snapshot of the active
configuration; they never read personal defaults from the add-on package.

On Windows, the installation registry and outputs default to `%LOCALAPPDATA%/InfinigenAssetStudio`.
Linux uses `$XDG_DATA_HOME/InfinigenAssetStudio` or `~/.local/share/InfinigenAssetStudio`, and macOS uses
`~/Library/Application Support/InfinigenAssetStudio`. The optional
`ASSET_STUDIO_DATA_DIR` override is useful for isolated tests and portable setups.
On Windows, WSL native dependencies live inside the selected distribution's
`~/.local/share/InfinigenAssetStudio`, while jobs and outputs remain in the Windows
data directory. Builds stay on a Linux filesystem; no source directory is used
for dependencies. Add-on updates leave both locations untouched.

The only supported managed full-scene backend in this release is Linux x86_64
(including Windows WSL2). Other platforms may use a validated existing installation.
WSL must already be initialized and provide Python 3, bash, g++ and make. The
installer checks these and never installs WSL, runs sudo, or changes shell startup
files. The normal flow needs no terminal once these platform prerequisites exist.
Ubuntu users missing build tools can install their distribution's build-essential
package themselves; this is an explicit prerequisite, not a hidden installer step.

An official checksum-pinned Miniconda Python 3.11 runtime is installed in a private
environment. The source and three required submodules are downloaded as official
HTTPS archives at exact commits. Archive traversal and symlinks are rejected. Git is unnecessary.
A minimal editable pip installation bypasses upstream's Git submodule setup hook;
the original CPU terrain build script and Cython extension are then built explicitly.
OpenGL training annotations, fluid simulation and CUDA compilation are not part
of the managed capability promise. CPU terrain is sufficient for nature scenes.

Validation checks source identity, 276 candidate factories, the exact worker bpy
and Python versions, indoor/nature imports, native terrain presence and a real PanFactory .blend
smoke test. Discovery candidates are not a claim that every factory can generate
under every config. The central compatibility manifest pins only a tested engine;
**Check Compatible Updates** compares against that manifest rather than pulling `main`.

Repair repeats dependency installation and native compilation only for an owned
managed directory. Removal deletes owned source/environment paths and preserves
outputs, downloads, logs, the library and configuration storage. Externally managed
environments have no repair/update/removal operations. Output Blender scenes open
in a new process so unsaved work in the interactive host is preserved.

Stage names come from the native RandomStageExecutor. Percentages indicate coarse
pipeline milestones, not invented time estimates; a long stage can remain at one
milestone. Logs preserve native output. Exact task configs and overrides, the seed,
source version, timing and output files are written to `generation.json`.
