"""Run extension integration checks without using the real Blender profile."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender")
    parser.add_argument("--skip-room", action="store_true")
    args = parser.parse_args()
    blender = args.blender or json.loads((ROOT / "runtime/development.json").read_text())["blender"]
    profile = ROOT / "test_output/extension" / ("profile-" + str(time.time_ns()))
    # Blender ignores BLENDER_USER_CONFIG when this directory does not exist.
    profile.mkdir(parents=True)
    env = dict(os.environ, BLENDER_USER_CONFIG=str(profile), PYTHONDONTWRITEBYTECODE="1")
    command = [blender, "--background", "--factory-startup", "--offline-mode",
               "--python-exit-code", "1", "--python", str(ROOT / "tests/blender_extension.py")]
    if args.skip_room:
        command += ["--", "--skip-room"]
    log = profile / "validation.log"
    with log.open("w", encoding="utf8") as output:
        result = subprocess.run(command, env=env, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
    text = log.read_text(encoding="utf8")
    if result.returncode or "STUDIO_EXTENSION_TEST_PASSED" not in text:
        print(text[-16000:])
        raise RuntimeError("Extension validation failed; see " + str(log))
    assert (profile / "userpref.blend").is_file(), "The isolated profile was not saved"
    print("Extension integration checks passed; log:", log)


if __name__ == "__main__":
    main()
