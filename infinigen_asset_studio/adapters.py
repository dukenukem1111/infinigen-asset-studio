"""Engine boundary. Only the actually supported Infinigen 1.19 adapter exists."""
from pathlib import Path
from . import discovery, scenes


class Infinigen1Adapter:
    def __init__(self, source):
        self.source = Path(source)

    def discover_assets(self):
        return discovery.discover(self.source)

    def discover_room_presets(self):
        return list(scenes.ROOMS) if (self.source / "infinigen_examples/generate_indoors.py").is_file() else []

    def discover_nature_presets(self):
        return scenes.discover_configs(self.source)["world_presets"]

    def generate_asset(self, folder, request, catalogue):
        from .worker import generate
        return generate(folder, request, self.source, catalogue)

    def generate_room(self, folder, request):
        if request.get("mode") != "ROOM":
            raise ValueError("Room adapter requires Room mode")
        return scenes.generate(folder, request, self.source)

    def generate_world(self, folder, request):
        if request.get("mode") != "WORLD":
            raise ValueError("World adapter requires World mode")
        return scenes.generate(folder, request, self.source)

    def get_version(self):
        from .worker import version_info
        return version_info(self.source)

    def validate_installation(self, smoke=False):
        from .setup_worker import validation
        return validation(self.source, smoke)

    def get_capabilities(self):
        return self.validate_installation()["capabilities"]
