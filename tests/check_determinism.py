import sys
from pathlib import Path
import bpy
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from infinigen_asset_studio.scene_tools import append_asset
a = append_asset(ROOT / "test_output/worker/chair_42/asset.blend")
b = append_asset(ROOT / "test_output/worker/chair_42_repeat/asset.blend")
graph = bpy.context.evaluated_depsgraph_get()
oa, ob = list(a.all_objects)[0], list(b.all_objects)[0]
ma, mb = oa.evaluated_get(graph).to_mesh(), ob.evaluated_get(graph).to_mesh()
differences = [(v.co - w.co).length for v, w in zip(ma.vertices, mb.vertices)]
print("DETERMINISM_DIFFERENCE", max(differences), sum(differences) / len(differences), sum(v > 1e-5 for v in differences), len(differences))
print("MODIFIERS_A", [(m.name, m.type) for m in oa.modifiers])
print("MODIFIERS_B", [(m.name, m.type) for m in ob.modifiers])
print("POLYGONS_DIFFER", sum(tuple(p.vertices) != tuple(q.vertices) for p, q in zip(ma.polygons, mb.polygons)))
print("BASE_MESH_DIFFERENCE", max((v.co - w.co).length for v, w in zip(oa.data.vertices, ob.data.vertices)))
print("CANONICAL_FACE_DIFFERENCE", len({tuple(sorted(p.vertices)) for p in ma.polygons} ^ {tuple(sorted(p.vertices)) for p in mb.polygons}))
