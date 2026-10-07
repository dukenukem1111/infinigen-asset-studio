"""Assert release structure, no machine data, matching version and valid syntax."""
import ast
import json
import os
from pathlib import Path
from zipfile import ZipFile
root = Path(__file__).resolve().parent.parent
manifest = json.loads((root / "infinigen_asset_studio/compatibility.json").read_text())
version = manifest["studio_version"]
tag = os.environ.get("GITHUB_REF_NAME", "")
if os.environ.get("GITHUB_REF_TYPE") == "tag":
    assert tag == "v" + version, "Release tag must match manifest version"
with ZipFile(root / "dist" / ("InfinigenAssetStudio-" + version + ".zip")) as archive:
    names = archive.namelist()
    assert "infinigen_asset_studio/__init__.py" in names
    assert "infinigen_asset_studio/LICENSE" in names
    assert "infinigen_asset_studio/dependency-constraints.txt" in names
    assert all(name.startswith("infinigen_asset_studio/") and ".." not in Path(name).parts for name in names)
    assert not any(any(part in name for part in ("machine.json", "__pycache__", ".blend", "/runtime/", "/.git/")) for name in names)
    tree = ast.parse(archive.read("infinigen_asset_studio/__init__.py"))
    info = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "bl_info" for t in node.targets))
    assert ".".join(map(str, info["version"])) == version
print("Release structure and version verified")
