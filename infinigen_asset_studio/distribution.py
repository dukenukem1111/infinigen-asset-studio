"""Distribution capabilities; the official extension uses an existing engine only."""
from pathlib import Path


def is_extension():
    return Path(__file__).with_name("blender_manifest.toml").is_file()


def require_dependency_management():
    if is_extension():
        raise ValueError(
            "The Blender extension connects to an existing Infinigen installation. "
            "Install or repair Infinigen outside Blender, then use Validate & Use."
        )
