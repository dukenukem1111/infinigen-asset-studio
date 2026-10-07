"""Persistent installation registry; importing this module never installs software."""
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from .core import write_json

MANIFEST = json.loads(Path(__file__).with_name("compatibility.json").read_text(encoding="utf8"))


def data_directory():
    override = os.environ.get("ASSET_STUDIO_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "InfinigenAssetStudio"
    if platform.system() == "Darwin":
        return Path.home() / "Library/Application Support/InfinigenAssetStudio"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "InfinigenAssetStudio"


def run(command, timeout=15):
    return subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=timeout,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


def distributions():
    if os.name != "nt" or not shutil.which("wsl.exe"):
        return []
    result = subprocess.run(["wsl.exe", "--list", "--quiet"], capture_output=True, timeout=15,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    return [line.strip() for line in result.stdout.decode("utf-16-le", errors="replace").splitlines() if line.strip()]


class InfinigenInstallationManager:
    def __init__(self, root=None):
        self.root = Path(root) if root else data_directory()
        self.config_path = self.root / "configuration.json"

    def load(self):
        if not self.config_path.exists():
            return {"schema_version": 1, "active": None}
        value = json.loads(self.config_path.read_text(encoding="utf8"))
        if value.get("schema_version") != 1:
            raise ValueError("Unsupported installation configuration version")
        return value

    def active(self):
        value = self.load().get("active")
        if not value:
            raise ValueError("Set up Infinigen first: find an existing installation or install a managed copy.")
        return value

    def activate(self, settings, report, allow_mismatch=False):
        if not report.get("healthy"):
            raise ValueError(report.get("message", "Installation validation failed"))
        if not report.get("compatible") and not allow_mismatch:
            raise ValueError("Version mismatch. Install the recommended version or explicitly enable Use Anyway.")
        value = self.load()
        value["active"] = dict(settings, validation=report)
        write_json(self.config_path, value)
        return value["active"]

    def update_report(self, report):
        value = self.load()
        if value.get("active"):
            value["active"]["validation"] = report
            write_json(self.config_path, value)

    def settings(self):
        value = self.active()
        return {key: value.get(key, "") for key in ("backend", "distribution", "source", "python")}

    def command(self, settings, args):
        if settings["backend"] == "WSL":
            return ["wsl.exe", "-d", settings["distribution"], "--", *args]
        return args

    def managed_settings(self, distribution=""):
        # Linux native storage avoids slow builds and Windows permissions in /mnt/c.
        if os.name == "nt":
            available = distributions()
            preferred = [name for name in available if name.lower().startswith(("ubuntu", "debian"))]
            distro = distribution or (preferred[0] if preferred else available[0] if available else "")
            if distro not in available:
                raise ValueError("Full scene installation needs WSL2 with an initialized Linux distribution. Install WSL from Windows Settings, then retry.")
            result = run(["wsl.exe", "-d", distro, "--", "python3", "-c", "import pathlib; print(pathlib.Path.home() / '.local/share/InfinigenAssetStudio')"])
            if result.returncode:
                raise ValueError("This WSL distribution needs Python 3 to run the installer. See Diagnostics.")
            root = result.stdout.strip()
            return {"backend": "WSL", "distribution": distro, "source": root + "/infinigen",
                    "python": root + "/environments/python/bin/python", "managed_root": root, "managed": True}
        return {"backend": "LOCAL", "distribution": "", "source": str(self.root / "infinigen"),
                "python": str(self.root / "environments/python/bin/python"), "managed_root": str(self.root), "managed": True}

    def candidates(self):
        """Small, read-only search in customary locations; validation runs separately."""
        values = []
        active = self.load().get("active")
        if active:
            values.append(active)
        if os.name == "nt":
            for distro in distributions():
                script = ("import pathlib,json; h=pathlib.Path.home(); "
                          "sources=[h/'infinigen',h/'.local/share/InfinigenAssetStudio/infinigen']; "
                          "py=[h/'.local/share/InfinigenAssetStudio/environments/python/bin/python',h/'miniconda3/envs/infinigen/bin/python',h/'anaconda3/envs/infinigen/bin/python']; "
                          "print(json.dumps([{'source':str(s),'python':str(p)} for s in sources for p in py if (s/'infinigen/__init__.py').is_file() and p.is_file()]))")
                try:
                    result = run(["wsl.exe", "-d", distro, "--", "python3", "-c", script])
                    for value in json.loads(result.stdout or "[]"):
                        values.append(dict(value, backend="WSL", distribution=distro, managed=False))
                except (ValueError, OSError, subprocess.TimeoutExpired):
                    continue
        else:
            for source in (Path.home() / "infinigen", self.root / "infinigen"):
                for interpreter in (source / ".venv/bin/python", Path.home() / "miniconda3/envs/infinigen/bin/python", self.root / "environments/python/bin/python"):
                    if (source / "infinigen/__init__.py").is_file() and interpreter.is_file():
                        values.append(dict(backend="LOCAL", distribution="", source=str(source), python=str(interpreter), managed=False))
        return list({(v["source"], v["python"], v.get("distribution", "")): v for v in values}.values())
