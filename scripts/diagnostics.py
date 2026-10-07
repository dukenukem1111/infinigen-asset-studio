"""Read persisted setup diagnostics without importing Blender."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infinigen_asset_studio.installation import InfinigenInstallationManager, MANIFEST
print(json.dumps({"studio": MANIFEST["studio_version"], "configuration": InfinigenInstallationManager().load()}, indent=2))
