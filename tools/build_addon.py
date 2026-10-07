"""Compatibility wrapper for the versioned release builder."""
import runpy
import shutil
from pathlib import Path
root = Path(__file__).resolve().parent.parent
output = runpy.run_path(str(root / "scripts/build_release.py"))["build"]()
shutil.copyfile(output, root / "dist/Infinigen_Asset_Studio.zip")
