"""Isolated dependency installer. Never executed in the host Blender interpreter."""
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import traceback
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infinigen_asset_studio.core import write_json
from infinigen_asset_studio.installation import MANIFEST


def download(url, target, expected=None):
    allowed = ("https://codeload.github.com/", "https://repo.anaconda.com/miniconda/")
    if not url.startswith(allowed):
        raise ValueError("Download host is not in the official installer allowlist")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        partial = target.with_suffix(target.suffix + ".partial")
        request = urllib.request.Request(url, headers={"User-Agent": "InfinigenAssetStudio/0.2"})
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as output:
            if not response.url.startswith(allowed):
                raise ValueError("Unexpected download redirect")
            shutil.copyfileobj(response, output)
        partial.replace(target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if expected and digest != expected:
        target.unlink()
        raise ValueError("Download checksum mismatch; retry the download")
    print("Downloaded", target.name, "sha256", digest, flush=True)
    return digest


def unpack(archive, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as value:
        names = value.namelist()
        prefix = names[0].split("/")[0]
        for member in value.infolist():
            relative = Path(*Path(member.filename).parts[1:])
            if ".." in relative.parts or relative.is_absolute() or member.filename.split("/")[0] != prefix:
                raise ValueError("Unsafe archive member")
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Archive symlinks are unsupported")
            target = (destination / relative).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError("Archive escapes installation directory")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with value.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)


def validation(source, smoke=False):
    """Runs in the selected runtime; existing environments are inspected only."""
    import importlib
    from infinigen_asset_studio.discovery import discover
    if not (source / "infinigen/__init__.py").is_file() or not (source / "pyproject.toml").is_file():
        raise ValueError("Selected folder is not an Infinigen source installation")
    os.chdir(source)
    sys.path.insert(0, str(source))
    import bpy
    import infinigen
    modules = {}
    for key, name in (("assets", "infinigen.core.init"), ("rooms", "infinigen_examples.generate_indoors"), ("worlds", "infinigen_examples.generate_nature")):
        try:
            importlib.import_module(name)
            modules[key] = {"available": True}
        except Exception as error:
            modules[key] = {"available": False, "message": str(error)}
    factories = discover(source)
    commit = "unknown"
    dirty_source = []
    if shutil.which("git") and (source / ".git").exists():
        result = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True, text=True)
        if result.returncode == 0:
            commit = result.stdout.strip()
        dirty = subprocess.run(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, timeout=20)
        if dirty.returncode == 0:
            dirty_source = dirty.stdout.splitlines()
    record = source / ".studio-source.json"
    if commit == "unknown" and record.is_file():
        commit = json.loads(record.read_text())["commit"]
    compatible = (infinigen.__version__ == MANIFEST["infinigen_version"] and commit == MANIFEST["commit"]
                  and bpy.app.version_string == MANIFEST["worker_bpy"] and sys.version_info[:2] == (3, 11) and not dirty_source)
    terrain = source / "infinigen/terrain/lib/cpu"
    native_files = [terrain / path for path in ("elements/ground.so", "elements/waterbody.so", "meshing/uniform_mesher.so", "soil_machine/SoilMachine.so")]
    native_files.append(source / "infinigen/OcMesher/ocmesher/lib/core.so")
    missing_native = [str(path.relative_to(source)) for path in native_files if not path.is_file()]
    if not list((source / "infinigen/terrain").glob("marching_cubes*.so")):
        missing_native.append("infinigen/terrain/marching_cubes extension")
    modules["worlds"]["available"] &= not missing_native
    if missing_native:
        modules["worlds"]["missing_native"] = missing_native
    if not modules["worlds"]["available"]:
        modules["worlds"].setdefault("message", "CPU terrain build is missing. Repair a managed installation or configure an existing full installation.")
    devices = []
    try:
        cycles = bpy.context.preferences.addons["cycles"].preferences
        for device_type in cycles.get_device_types(bpy.context):
            cycles.get_devices_for_type(device_type[0])
        devices = [{"name": d.name, "type": d.type} for d in cycles.devices]
    except Exception:
        pass
    import psutil
    hardware = {"os": platform.platform(), "cpu": platform.processor(), "cpu_count": os.cpu_count(),
                "ram_gb": round(psutil.virtual_memory().total / 1024 ** 3, 1),
                "disk_free_gb": round(shutil.disk_usage(source).free / 1024 ** 3, 1), "cycles_devices": devices,
                "cuda_terrain_compiled": (source / "infinigen/terrain/lib/cuda/elements/ground.so").is_file()}
    if shutil.which("nvidia-smi"):
        probe = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"], capture_output=True, text=True, timeout=15)
        hardware["nvidia_driver"] = probe.stdout.strip() if probe.returncode == 0 else "Not available in this runtime"
    report = {"healthy": bool(factories) and modules["assets"]["available"], "compatible": compatible,
              "version": infinigen.__version__, "commit": commit, "python": platform.python_version(),
              "blender": bpy.app.version_string, "factory_count": len(factories), "capabilities": modules,
              "dirty_tracked_source": dirty_source,
              "hardware": hardware, "message": "Compatible" if compatible else "Version differs from the tested compatibility manifest"}
    if not report["healthy"]:
        report["message"] = "Runtime validation failed: " + modules["assets"].get("message", "No asset factories found")
    if smoke:
        import tempfile
        from infinigen_asset_studio.worker import initialize
        initialize(source)
        from infinigen.assets.objects.tableware.pan import PanFactory
        factory = PanFactory(212)
        asset = factory.spawn_asset(0)
        factory.finalize_assets(asset)
        with tempfile.TemporaryDirectory(prefix="studio-self-test-") as folder:
            target = Path(folder) / "smoke.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(target), check_existing=False)
            assert target.stat().st_size > 0
        report["smoke_test"] = "PanFactory seed 212 saved as .blend"
    return report


def install(folder, request):
    root = Path(request["managed_root"]).expanduser().resolve()
    source = root / "infinigen"
    marker = root / ".studio-managed.json"
    root.mkdir(parents=True, exist_ok=True)
    for path in (source, root / "environments", root / "environments/python", root / "downloads"):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("Managed dependency directory contains a symlink or escapes its owned root")
    if (source.exists() or (root / "environments/python").exists()) and not marker.is_file():
        raise ValueError("Managed directory already contains unowned software. Choose an empty directory; existing installations are never overwritten.")
    if marker.is_file():
        ownership = json.loads(marker.read_text())
        if ownership.get("owner") != "InfinigenAssetStudio" or ownership.get("root") != str(root):
            raise ValueError("Managed ownership check failed")
    write_json(marker, {"owner": "InfinigenAssetStudio", "root": str(root), "commit": MANIFEST["commit"]})

    def stage(label, progress):
        if (folder / "cancel.json").exists():
            raise InterruptedError("Setup cancelled")
        write_json(folder / "status.json", {"stage": label, "progress": progress, "pid": os.getpid()})
        print(label, flush=True)

    if request["action"] == "remove":
        # Deletion limited to manager-owned dependency paths, preserving outputs.
        owned = json.loads(marker.read_text())
        if owned.get("owner") != "InfinigenAssetStudio" or owned.get("root") != str(root) or root == Path.home():
            raise ValueError("Managed ownership check failed")
        for name in ("infinigen", "environments"):
            path = root / name
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError("Managed path escapes root")
            if path.exists():
                shutil.rmtree(path)
        return {"removed": True}

    stage("Checking system requirements", .03)
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("Automatic full-scene setup currently supports Linux x86_64 and Windows through WSL2. Other platforms can use a validated existing installation.")
    missing = [tool for tool in ("bash", "g++", "make") if not shutil.which(tool)]
    if missing:
        raise ValueError("Linux build prerequisites missing: " + ", ".join(missing) + ". Install the prerequisites listed in Setup documentation; Asset Studio never runs sudo.")
    if shutil.disk_usage(root).free < 8 * 1024 ** 3:
        raise ValueError("Managed setup needs at least 8 GB free disk space")
    env_path = root / "environments/python"
    python = env_path / "bin/python"
    stage("Preparing isolated Python 3.11", .08)
    if not python.is_file():
        bootstrap = MANIFEST["bootstrap"]["Linux-x86_64"]
        installer = root / "downloads" / bootstrap["url"].rsplit("/", 1)[1]
        download(bootstrap["url"], installer, bootstrap["sha256"])
        command = ["bash", str(installer), "-b", "-p", str(env_path)]
        if env_path.exists():
            command.append("-u")
        subprocess.run(command, check=True)
    stage("Downloading pinned Infinigen source", .18)
    hashes = {}
    downloads = [("", "princeton-vl/infinigen", MANIFEST["commit"], MANIFEST["source_sha256"])] + [(v["path"], v["repository"], v["commit"], v["sha256"]) for v in MANIFEST["submodules"]]
    for relative, repository, commit, expected in downloads:
        archive = root / "downloads" / (repository.replace("/", "-") + "-" + commit + ".zip")
        hashes[repository] = download("https://codeload.github.com/" + repository + "/zip/" + commit, archive, expected)
        unpack(archive, source / relative)
    write_json(source / ".studio-source.json", {"commit": MANIFEST["commit"], "sha256": hashes})
    stage("Installing Python dependencies", .35)
    env = dict(os.environ, INFINIGEN_MINIMAL_INSTALL="True", PIP_DISABLE_PIP_VERSION_CHECK="1")
    subprocess.run([str(python), "-m", "pip", "install", "setuptools==80.9.0", "numpy==1.26.4", "Cython==3.3.0", "wheel"], env=env, check=True)
    subprocess.run([str(python), "-m", "pip", "install", "--no-build-isolation", "-e", str(source) + "[terrain,vis]",
                    "-c", str(Path(__file__).with_name("dependency-constraints.txt"))], env=env, check=True)
    stage("Compiling CPU terrain and OcMesher", .68)
    subprocess.run(["bash", "scripts/install/compile_terrain.sh"], cwd=source, env=env, check=True)
    # Upstream setup.py's minimal mode excludes this extension. Build it explicitly
    # with its original source without invoking the git-dependent full setup hook.
    code = ("from setuptools import setup,Extension; from Cython.Build import cythonize; import numpy; "
            "setup(name='studio-terrain-build',ext_modules=cythonize([Extension('infinigen.terrain.marching_cubes',"
            "['infinigen/terrain/marching_cubes/_marching_cubes_lewiner_cy.pyx'],include_dirs=[numpy.get_include()])]),"
            "script_args=['build_ext','--inplace'])")
    subprocess.run([str(python), "-c", code], cwd=source, env=env, check=True)
    stage("Validating imports and basic asset generation", .9)
    subprocess.run([str(python), str(Path(__file__).resolve()), "--validate-child", str(folder)], check=True)
    report = json.loads((folder / "validation.json").read_text())
    if not report["healthy"] or not report["compatible"] or not all(v["available"] for v in report["capabilities"].values()):
        raise ValueError("Installation did not pass validation. See the install log.")
    write_json(root / "installation.json", dict(request, validation=report, downloads=hashes))
    return report


def main():
    if os.name != "nt" and "--validate-child" not in sys.argv and os.getpgrp() != os.getpid():
        os.setsid()
    folder = Path(sys.argv[-1]).resolve()
    request = json.loads((folder / "request.json").read_text())
    if (folder / "cancel.json").exists():
        return
    try:
        if "--validate-child" in sys.argv:
            write_json(folder / "validation.json", validation(Path(request["source"]), smoke=True))
            return
        write_json(folder / "status.json", {"stage": "Validating installation" if request["action"] == "validate" else "Starting setup", "progress": .02, "pid": os.getpid()})
        report = validation(Path(request["source"]), request.get("smoke", False)) if request["action"] == "validate" else install(folder, request)
        write_json(folder / "result.json", {"ok": True, "report": report})
        write_json(folder / "status.json", {"stage": "Complete", "progress": 1, "pid": os.getpid()})
    except Exception as error:
        traceback.print_exc()
        write_json(folder / "result.json", {"ok": False, "message": str(error), "traceback": traceback.format_exc()})
        sys.exit(1)


if __name__ == "__main__":
    main()
