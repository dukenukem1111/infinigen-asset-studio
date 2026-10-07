"""Pure Python metadata, parameter validation and seeded randomization."""
import json
import math
import random
import re
from pathlib import Path
from typing import TypedDict

SCHEMA_VERSION = 1


class ParameterDefinition(TypedDict, total=False):
    name: str
    display_name: str
    type: str
    minimum: float | None
    maximum: float | None
    default: float | int | bool | str
    step: float
    category: str
    tooltip: str
    randomizable: bool
    advanced: bool
    enum_values: list[str]
    target: str


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf8")
    temp.replace(path)


def read_metadata(path):
    data = json.loads(Path(path).read_text(encoding="utf8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("This file uses an unsupported Studio metadata version.")
    if not isinstance(data.get("generator"), str):
        raise ValueError("The file does not identify a generator.")
    seed = data.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2147483646:
        raise ValueError("Seed must be an integer between 0 and 2147483646.")
    return data


def safe_name(name: str) -> str:
    return re.sub(r"[^\w .-]", "_", name).strip(" .")[:80] or "Asset"


def validate_parameters(definitions: list[ParameterDefinition], values: dict) -> dict:
    definitions = {p["name"]: p for p in definitions}
    result = {}
    for name, value in values.items():
        if name not in definitions:
            raise ValueError(f'Parameter "{name}" is not supported by this generator.')
        definition = definitions[name]
        kind = definition["type"]
        if kind == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"{name} must be a checkbox value.")
        elif kind == "enum":
            if value not in definition["enum_values"]:
                raise ValueError(f"{name} has an unsupported choice.")
        elif kind in {"float", "int"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number.")
            if kind == "int" and int(value) != value:
                raise ValueError(f"{name} must be a whole number.")
            lower, upper = definition["minimum"], definition["maximum"]
            # Blender stores RNA floats at single precision. Preserve authored bounds.
            if kind == "float" and math.isclose(value, lower, rel_tol=1e-6, abs_tol=1e-7):
                value = lower
            if kind == "float" and math.isclose(value, upper, rel_tol=1e-6, abs_tol=1e-7):
                value = upper
            if not lower <= value <= upper:
                raise ValueError(f'{name} must be between {definition["minimum"]} and {definition["maximum"]}.')
        else:
            raise ValueError(f"Unsupported parameter type: {kind}")
        result[name] = value
    return result


def randomize(definitions: list[ParameterDefinition], values: dict, locked: set[str], seed: int) -> dict:
    rng = random.Random(seed)
    result = dict(values)
    for p in definitions:
        if p["name"] in locked or not p.get("randomizable", True):
            continue
        if p["type"] == "bool":
            value = bool(rng.randrange(2))
        elif p["type"] == "enum":
            value = rng.choice(p["enum_values"])
        elif p["type"] == "int":
            value = rng.randint(math.ceil(p["minimum"]), math.floor(p["maximum"]))
        else:
            value = rng.uniform(p["minimum"], p["maximum"])
        result[p["name"]] = value
    return result
