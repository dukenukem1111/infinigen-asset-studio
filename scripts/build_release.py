"""Build a versioned installable legacy add-on; no machine configuration included."""
import ast
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent


def build():
    package = ROOT / "infinigen_asset_studio"
    manifest = json.loads((package / "compatibility.json").read_text())
    version = manifest["studio_version"]
    output = ROOT / "dist" / ("InfinigenAssetStudio-" + version + ".zip")
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in sorted(package.rglob("*")):
            if path.is_file() and path.suffix in {".py", ".json", ".txt"} and path.name != "machine.json":
                if path.suffix == ".py":
                    ast.parse(path.read_text(encoding="utf8"))
                archive.write(path, path.relative_to(ROOT))
        for name in ("LICENSE", "THIRD_PARTY_LICENSES.md"):
            archive.write(ROOT / name, "infinigen_asset_studio/" + name)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(digest + "  " + output.name + "\n")
    print(output)
    return output


if __name__ == "__main__":
    build()
