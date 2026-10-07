"""Original versioned presets and generation records outside the add-on."""
import json
import time
import uuid
from pathlib import Path
from .core import write_json
from .installation import MANIFEST


def records(root):
    path = Path(root) / "history.json"
    return json.loads(path.read_text(encoding="utf8")) if path.is_file() else []


def record(root, request, metadata, folder, output):
    items = records(root)
    entry = {"id": uuid.uuid4().hex, "request": request, "metadata": metadata,
             "folder": str(folder), "output": str(output), "favorite": False}
    items.insert(0, entry)
    write_json(Path(root) / "history.json", items)
    return entry


def preset(request, source_version=None):
    source_version = source_version or {}
    return {"schema_version": 1, "studio_version": MANIFEST["studio_version"],
            "infinigen_commit": source_version.get("commit", MANIFEST["commit"]),
            "infinigen_version": source_version.get("infinigen", source_version.get("version", MANIFEST["infinigen_version"])), "mode": request.get("mode", "ASSET"),
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "request": request, "export_options": {}}


def read_preset(path):
    value = json.loads(Path(path).read_text(encoding="utf8"))
    if value.get("schema_version") != 1 or value.get("mode") not in {"ROOM", "WORLD", "ASSET"}:
        raise ValueError("Unsupported Studio preset")
    if value.get("infinigen_commit") != MANIFEST["commit"]:
        raise ValueError("Preset was created for another Infinigen commit")
    return value["request"]
