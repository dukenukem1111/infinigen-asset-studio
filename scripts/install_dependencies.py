"""CLI for unattended setup; normal users use the Blender Setup panel."""
import argparse
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infinigen_asset_studio.installation import InfinigenInstallationManager
from infinigen_asset_studio.bridge import Job


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--distribution", default="")
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    manager = InfinigenInstallationManager(args.data_dir)
    value = manager.managed_settings(args.distribution)
    job = Job(dict(value, python="python3"), manager.root, dict(action="install", managed_root=value["managed_root"]), "setup_worker.py")
    print("Log:", job.folder / "worker.log", flush=True)
    try:
        while True:
            result = job.poll()
            if result:
                manager.activate(value, result["report"])
                print(json.dumps(result["report"], indent=2))
                return
            time.sleep(.5)
    except KeyboardInterrupt:
        job.cancel()
        raise


if __name__ == "__main__":
    main()
