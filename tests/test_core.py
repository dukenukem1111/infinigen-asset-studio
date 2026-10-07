import json
import tempfile
import unittest
from pathlib import Path
from infinigen_asset_studio.core import read_metadata, randomize, validate_parameters, write_json
from infinigen_asset_studio.discovery import discover


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.defs = [{"name": "width", "type": "float", "minimum": 0.4, "maximum": 0.5},
                     {"name": "style", "type": "enum", "enum_values": ["a", "b"]},
                     {"name": "enabled", "type": "bool"}]

    def test_seeded_randomization_and_lock(self):
        first = randomize(self.defs, {"width": 0.42}, {"width"}, 76)
        self.assertEqual(first, randomize(self.defs, {"width": 0.42}, {"width"}, 76))
        self.assertEqual(first["width"], 0.42)

    def test_rejects_invalid_parameters(self):
        for value in (-1, float("nan"), True, "0.4"):
            with self.assertRaises(ValueError):
                validate_parameters(self.defs, {"width": value})
        with self.assertRaises(ValueError):
            validate_parameters(self.defs, {"style": "invented"})
        with self.assertRaises(ValueError):
            validate_parameters(self.defs, {"missing": 1})

    def test_versioned_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "preset.json"
            data = {"schema_version": 1, "generator": "some.ChairFactory", "seed": 42, "parameters": {"width": 0.45}}
            write_json(path, data)
            self.assertEqual(read_metadata(path), data)
            data["schema_version"] = 999
            write_json(path, data)
            with self.assertRaises(ValueError):
                read_metadata(path)

    def test_discovery_does_not_execute_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "infinigen/assets/objects/chairs/example.py"
            path.parent.mkdir(parents=True)
            path.write_text('raise RuntimeError("must not import")\nclass ChairFactory(AssetFactory):\n    def __init__(self, seed):\n        self.width = uniform(0.4, 0.5)\n        self.dependent = uniform(self.width, 1)\n    def create_asset(self):\n        pass\n', encoding="utf8")
            result = discover(root)
            self.assertEqual(len(result), 1)
            self.assertEqual([p["name"] for p in result[0]["parameters"]], ["width"])


if __name__ == "__main__":
    unittest.main()
