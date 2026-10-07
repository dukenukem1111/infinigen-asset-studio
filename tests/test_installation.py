"""Pure installation/preset/release boundary checks without any Blender imports."""
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from infinigen_asset_studio.installation import InfinigenInstallationManager, MANIFEST
from infinigen_asset_studio.setup_worker import unpack, install
from infinigen_asset_studio import history, scenes


class InstallationTests(unittest.TestCase):
    def test_registry_requires_validation_and_explicit_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = InfinigenInstallationManager(folder)
            with self.assertRaises(ValueError):
                manager.settings()
            settings = dict(backend="LOCAL", distribution="", source="/some source", python="/isolated/python", managed=False)
            with self.assertRaises(ValueError):
                manager.activate(settings, {"healthy": False, "message": "wrong directory"})
            with self.assertRaises(ValueError):
                manager.activate(settings, {"healthy": True, "compatible": False})
            manager.activate(settings, {"healthy": True, "compatible": False}, allow_mismatch=True)
            # A new manager instance represents a restart or add-on update.
            restored = InfinigenInstallationManager(folder)
            self.assertEqual(restored.settings()["source"], "/some source")
            self.assertFalse(restored.active()["managed"])

    def test_archive_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "bad.zip"
            with ZipFile(archive, "w") as output:
                output.writestr("root/../../escape.py", "bad")
            with self.assertRaises(ValueError):
                unpack(archive, Path(folder) / "destination")
            self.assertFalse((Path(folder) / "escape.py").exists())

    def test_managed_installer_rejects_unowned_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "managed"
            (root / "infinigen").mkdir(parents=True)
            sentinel = root / "infinigen/do-not-change.txt"
            sentinel.write_text("external environment")
            with self.assertRaisesRegex(ValueError, "unowned"):
                install(Path(folder), {"action": "install", "managed_root": str(root)})
            self.assertEqual(sentinel.read_text(), "external environment")
            self.assertFalse((root / ".studio-managed.json").exists())

    def test_remove_owned_dependencies_preserves_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "managed"
            for name in ("infinigen", "environments", "outputs", "downloads", "logs"):
                (root / name).mkdir(parents=True)
                (root / name / "sentinel.txt").write_text(name)
            (root / ".studio-managed.json").write_text(json.dumps({"owner": "InfinigenAssetStudio", "root": str(root.resolve())}))
            result = install(Path(folder), {"action": "remove", "managed_root": str(root)})
            self.assertTrue(result["removed"])
            self.assertFalse((root / "infinigen").exists())
            self.assertFalse((root / "environments").exists())
            for name in ("outputs", "downloads", "logs"):
                self.assertEqual((root / name / "sentinel.txt").read_text(), name)

    def test_scene_presets_and_history_reconstruct_request(self):
        with tempfile.TemporaryDirectory() as folder:
            request = scenes.build_request("ROOM", 12345, "bedroom", height=3.2, clutter=False)
            path = Path(folder) / "preset.json"
            path.write_text(json.dumps(history.preset(request)))
            self.assertEqual(history.read_preset(path), request)
            value = json.loads(path.read_text())
            value["infinigen_commit"] = "incompatible"
            path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                history.read_preset(path)
            history.record(folder, request, {"seed": 12345}, folder, Path(folder) / "scene.blend")
            self.assertEqual(history.records(folder)[0]["request"]["seed"], 12345)

    def test_no_fake_room_categories_or_unpinned_backend(self):
        self.assertNotIn("office", dict(scenes.ROOMS))
        self.assertEqual(len(MANIFEST["commit"]), 40)
        self.assertEqual(MANIFEST["worker_bpy"], "4.2.0")
        with self.assertRaises(ValueError):
            scenes.build_request("WORLD", -1, "forest")


if __name__ == "__main__":
    unittest.main()
