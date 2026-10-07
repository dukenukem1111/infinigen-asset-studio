"""Cancellable process bridge; no bpy calls on background threads."""
import json
import os
import subprocess
import signal
import uuid
from pathlib import Path
from .core import write_json, safe_name


def linux_path(path):
    path = str(Path(path).resolve()).replace("\\", "/")
    if len(path) > 2 and path[1] == ":":
        return "/mnt/" + path[0].lower() + path[2:]
    return path


class Job:
    def __init__(self, settings, workspace, request, worker_name="worker.py"):
        self.settings = settings
        category = "rooms" if request.get("mode") == "ROOM" else "worlds" if request.get("mode") == "WORLD" else "assets"
        name = Path(request["preset"]).stem if request.get("action") == "scene" else request.get("generator", "Asset").split(".")[-1]
        base = Path(workspace) / "outputs" / category / safe_name(name) if request.get("action") in {"generate", "scene"} else Path(workspace) / "jobs"
        self.folder = base / uuid.uuid4().hex
        self.folder.mkdir(parents=True)
        self.request = dict(request, source=settings["source"])
        write_json(self.folder / "request.json", self.request)
        if worker_name not in {"worker.py", "setup_worker.py"}:
            raise ValueError("Unknown Studio worker")
        worker = Path(__file__).with_name(worker_name)
        self.log = (self.folder / "worker.log").open("w", encoding="utf8")
        if settings["backend"] == "WSL":
            command = ["wsl.exe", "-d", settings["distribution"], "--", settings["python"],
                       linux_path(worker), linux_path(self.folder)]
        else:
            command = [settings["python"], str(worker), str(self.folder)]
        try:
            self.process = subprocess.Popen(command, stdout=self.log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                start_new_session=os.name != "nt")
        except Exception:
            self.log.close()
            raise

    def status(self):
        try:
            return json.loads((self.folder / "status.json").read_text(encoding="utf8"))
        except (OSError, ValueError):
            return {"stage": "Starting the installed runtime", "progress": 0}

    def poll(self):
        if self.process.poll() is None:
            return None
        self.log.close()
        result = self.folder / "result.json"
        if not result.exists():
            detail = (self.folder / "worker.log").read_text(encoding="utf8", errors="replace")[-16000:]
            raise RuntimeError("The generation runtime stopped before returning a result. Check runtime paths and Technical Details.\n" + detail)
        data = json.loads(result.read_text(encoding="utf8"))
        if not data.get("ok"):
            raise RuntimeError(data.get("message", "Generation failed") + "\n" + data.get("traceback", ""))
        return data

    def cancel(self):
        # Also covers cancellation while WSL is still starting, before a PID exists.
        write_json(self.folder / "cancel.json", {"cancel": True})
        status = self.status()
        if self.settings["backend"] == "WSL" and status.get("pid"):
            subprocess.run(["wsl.exe", "-d", self.settings["distribution"], "--", "kill", "-TERM", "--", "-" + str(int(status["pid"]))],
                timeout=10, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if self.process.poll() is None:
            if os.name != "nt":
                os.killpg(self.process.pid, signal.SIGTERM)
            elif self.settings["backend"] == "LOCAL":
                subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"], timeout=10,
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if self.process.poll() is None:
                self.process.terminate()
            self.process.wait(timeout=10)
        self.log.close()
