"""Opt-in real managed install/asset/scene/repair tests; not a pure unit test."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infinigen_asset_studio.bridge import Job
from infinigen_asset_studio.installation import InfinigenInstallationManager, MANIFEST
from infinigen_asset_studio.scenes import build_request
from infinigen_asset_studio.core import write_json

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--managed-root", required=True)
    parser.add_argument("--distribution", default="")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--assets", action="store_true")
    parser.add_argument("--world", action="store_true")
    parser.add_argument("--room", action="store_true")
    parser.add_argument("--repair", action="store_true")
    args = parser.parse_args()
    value = dict(backend="WSL" if args.distribution else "LOCAL", distribution=args.distribution,
                 source=args.managed_root + "/infinigen", python=args.managed_root + "/environments/python/bin/python",
                 managed=True, managed_root=args.managed_root)
    output = ROOT / "test_output/managed_validation"
    output.mkdir(parents=True, exist_ok=True)
    checks = []

    def operation(label, request, setup=False, expect_failure=False):
        settings = dict(value, python="python3") if setup and request["action"] != "validate" else value
        job = Job(settings, output, request, "setup_worker.py" if setup else "worker.py")
        deadline = time.monotonic() + 2400
        try:
            while True:
                result = job.poll()
                if result:
                    if expect_failure:
                        assert not result.get("report", {}).get("healthy", True), "Expected a broken dependency to fail health validation"
                    checks.append(dict(check=label, ok=True, folder=str(job.folder), result=result))
                    write_json(output / "latest.json", checks)
                    print(label, "PASSED", flush=True)
                    return result, job.folder
                if time.monotonic() > deadline:
                    job.cancel()
                    raise TimeoutError(label)
                time.sleep(.25)
        except RuntimeError as error:
            if not expect_failure:
                raise
            checks.append(dict(check=label, ok=True, expected_failure=str(error).splitlines()[0], folder=str(job.folder)))
            write_json(output / "latest.json", checks)
            print(label, "PASSED (expected failure)", flush=True)
            return None, job.folder

    def remote(code, *arguments):
        command = InfinigenInstallationManager(output).command(value, [value["python"], "-c", code, *arguments])
        return subprocess.run(command, check=True, capture_output=True, text=True)

    if args.install:
        operation("fresh_install", dict(action="install", managed_root=args.managed_root), setup=True)
    if args.assets:
        for name, generator, seed, parameters in (
            ("chair_seed42", "infinigen.assets.objects.seating.chairs.chair.ChairFactory", 42, {"width": .4}),
            ("chair_seed43", "infinigen.assets.objects.seating.chairs.chair.ChairFactory", 43, {"width": .5}),
            ("articulated_box", "infinigen.assets.sim_objects.box.BoxFactory", 8, {})):
            result, folder = operation(name, dict(action="generate", generator=generator, seed=seed, parameters=parameters, quality="DRAFT"))
            assert (folder / "asset.blend").is_file()
            assert result["metadata"]["seed"] == seed
            assert result["metadata"]["parameters"] == parameters
            if name == "articulated_box":
                assert result["metadata"]["joints"], "Native articulation must survive managed generation"
    for enabled, mode, preset in ((args.room, "ROOM", "living-room"), (args.world, "WORLD", "infinigen_examples/configs_nature/scene_types/desert.gin")):
        if enabled:
            result, folder = operation(mode.lower(), build_request(mode, 0, preset, render_device="CPU"))
            assert (folder / result["scene"]).is_file()
            assert result["metadata"]["statistics"]["meshes"] > 10
            assert result["metadata"]["statistics"]["cameras"] >= 1
    if args.repair:
        # Mutate only this explicitly selected, owned test installation.
        marker = remote("import json,pathlib,sys; p=pathlib.Path(sys.argv[1]); print((p/'.studio-managed.json').read_text())", args.managed_root)
        assert json.loads(marker.stdout)["owner"] == "InfinigenAssetStudio"
        source_record = value["source"] + "/.studio-source.json"
        original = remote("import pathlib,sys; print(pathlib.Path(sys.argv[1]).read_text())", source_record).stdout
        try:
            remote("import json,pathlib,sys; p=pathlib.Path(sys.argv[1]); x=json.loads(p.read_text()); x['commit']='unsupported-test-commit'; p.write_text(json.dumps(x))", source_record)
            result, _ = operation("version_mismatch_detection", dict(action="validate"), setup=True)
            assert result["report"]["healthy"] and not result["report"]["compatible"]
            try:
                InfinigenInstallationManager(output / "registry").activate(value, result["report"])
                raise AssertionError("Mismatch was not rejected")
            except ValueError:
                pass
        finally:
            remote("import pathlib,sys; pathlib.Path(sys.argv[1]).write_text(sys.argv[2])", source_record, original)
        command = InfinigenInstallationManager(output).command(value, [value["python"], "-m", "pip", "uninstall", "--yes", "gin-config"])
        subprocess.run(command, check=True)
        operation("missing_dependency_detection", dict(action="validate"), setup=True, expect_failure=True)
        result, _ = operation("managed_repair", dict(action="install", managed_root=args.managed_root), setup=True)
        assert result["report"]["compatible"] and "smoke_test" in result["report"]
        operation("asset_after_repair", dict(action="generate", generator="infinigen.assets.objects.tableware.pan.PanFactory", seed=212, parameters={}, quality="DRAFT"))
    print("MANAGED_VALIDATION_PASSED", flush=True)


if __name__ == "__main__":
    main()
