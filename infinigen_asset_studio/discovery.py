"""Conservative source inspection: no speculative imports or arbitrary evaluation."""
import ast
from pathlib import Path

BASIC = {"width", "size", "scale", "depth", "thickness", "leg_height", "back_height", "has_arm", "is_seat_round", "has_handle", "has_guard", "leg_type"}
EXCLUDED = {"factory_seed", "coarse", "pre_level", "seed"}


def literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def parameter(name, value):
    """Infer only independent scalar literal values and literal distribution ranges."""
    lo = hi = default = None
    choices = []
    kind = None
    if isinstance(value, ast.Call):
        fn = ast.unparse(value.func).split(".")[-1]
        args = [literal(a) for a in value.args]
        if fn in {"uniform", "log_uniform", "randint"} and len(args) == 2 and all(type(a) in {float, int} for a in args):
            lo, hi = args
            kind = "int" if fn == "randint" else "float"
            if kind == "int":
                hi -= 1
            default = int((lo + hi) / 2) if kind == "int" else (lo + hi) / 2
        elif fn == "choice" and args and isinstance(args[0], (list, tuple)):
            if all(isinstance(v, str) for v in args[0]):
                choices = list(args[0])
                kind, default = "enum", choices[0]
            elif all(type(v) is bool for v in args[0]):
                kind, default = "bool", False
    elif isinstance(value, ast.Compare):
        # Scalar Bernoulli tests; they remain explicit UI overrides.
        if isinstance(value.left, ast.Call) and ast.unparse(value.left.func).split(".")[-1] == "uniform":
            kind, default = "bool", False
    else:
        v = literal(value)
        if type(v) is bool:
            kind, default = "bool", v
        # Fixed numeric constructor constants are not necessarily independent controls.
    if kind is None or name in EXCLUDED or lo is not None and hi < lo:
        return None
    return {"name": name, "display_name": name.replace("_", " ").title(), "type": kind,
            "minimum": lo, "maximum": hi, "default": default, "step": 1 if kind == "int" else 0.01,
            "category": "Shape", "tooltip": f"Override {name.replace('_', ' ')} before generation. Inferred from the installed constructor; dependent controls may need an explicit schema.",
            "randomizable": True, "advanced": name not in BASIC, "enum_values": choices, "target": "attribute"}


def discover(source):
    source = Path(source)
    root = source / "infinigen/assets"
    if not root.is_dir():
        raise FileNotFoundError("Choose the Infinigen repository containing infinigen/assets.")
    classes = {}
    for folder in (root / "objects", root / "sim_objects"):
        for path in sorted(folder.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf8"))
            except (SyntaxError, UnicodeError):
                continue
            for node in tree.body:
                if not isinstance(node, ast.ClassDef) or not node.name.endswith("Factory"):
                    continue
                module = ".".join(path.relative_to(source).with_suffix("").parts)
                bases = [ast.unparse(b).split(".")[-1] for b in node.bases]
                methods = {n.name: n for n in node.body if isinstance(n, ast.FunctionDef)}
                abstract = "create_asset" in methods and any(isinstance(n, ast.Raise) and "NotImplementedError" in ast.unparse(n) for n in ast.walk(methods["create_asset"]))
                definitions = []
                if "__init__" in methods:
                    for assign in ast.walk(methods["__init__"]):
                        if not isinstance(assign, ast.Assign) or len(assign.targets) != 1:
                            continue
                        target = assign.targets[0]
                        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                            p = parameter(target.attr, assign.value)
                            if p:
                                definitions.append(p)
                classes[module + "." + node.name] = {"id": module + "." + node.name, "name": node.name,
                    "module": module, "category": "Articulated" if folder.name == "sim_objects" else path.relative_to(folder).parts[0].replace("_", " ").title(),
                    "articulated": folder.name == "sim_objects", "description": (ast.get_docstring(node) or "Procedural " + node.name.removesuffix("Factory"))[:240],
                    "parameters": list({p["name"]: p for p in definitions}.values()), "bases": bases, "abstract": abstract,
                    "creates": "create_asset" in methods}
    by_name = {}
    for item in classes.values():
        by_name.setdefault(item["name"], []).append(item)

    def concrete(item, seen=None):
        seen = set() if seen is None else seen
        if item["id"] in seen or item["abstract"]:
            return False
        seen.add(item["id"])
        if item["creates"]:
            return True
        return any(concrete(parent, seen.copy()) for base in item["bases"] for parent in by_name.get(base, []))

    import json
    for path in sorted(Path(__file__).with_name("schemas").glob("*.json")):
        schema = json.loads(path.read_text(encoding="utf8"))
        item = classes.get(schema["generator"])
        if item is None:
            continue
        params = {p["name"]: p for p in item["parameters"]}
        for override in schema.get("parameters", []):
            name = override["name"]
            definition = dict(params.get(name, {}), **override)
            if definition.get("target", "attribute") != "attribute":
                raise ValueError(f"Unsupported schema target in {path.name}: {name}")
            definition.setdefault("minimum", None)
            definition.setdefault("maximum", None)
            definition.setdefault("enum_values", [])
            definition.setdefault("step", 0.01)
            definition.setdefault("category", "Shape")
            definition.setdefault("advanced", False)
            definition.setdefault("randomizable", True)
            definition.setdefault("target", "attribute")
            for required in ("type", "default", "display_name", "tooltip"):
                if required not in definition:
                    raise ValueError(f"Missing {required} in schema {path.name}: {name}")
            params[name] = definition
        item["parameters"] = list(params.values())
    return sorted([v for v in classes.values() if concrete(v)], key=lambda v: (v["category"], v["name"]))
