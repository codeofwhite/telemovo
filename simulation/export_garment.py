"""Export the exact RoboDojo garment asset, retaining source and layout provenance."""
from pathlib import Path
import argparse
import hashlib
import json



def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True,help='RoboDojo garment USD/USDZ')
    parser.add_argument('--layout',type=Path,required=True,help='resolved-layout.json containing Garment/Top_Long')
    parser.add_argument('--output',type=Path,required=True,help='New asset output directory')
    args=parser.parse_args()
    SOURCE=args.source.resolve();LAYOUT=args.layout.resolve()
    import numpy as np
    from pxr import Usd, UsdGeom
    stage = Usd.Stage.Open(str(SOURCE))
    meshes = [UsdGeom.Mesh(p) for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]
    assert len(meshes) == 1
    mesh = meshes[0]
    points = np.asarray(mesh.GetPointsAttr().Get(), dtype=float)
    faces = np.asarray(mesh.GetFaceVertexIndicesAttr().Get(), dtype=int).reshape(-1, 3)
    assert all(n == 3 for n in mesh.GetFaceVertexCountsAttr().Get())
    matrix = np.asarray(UsdGeom.XformCache().GetLocalToWorldTransform(mesh.GetPrim()))
    points = (np.c_[points, np.ones(len(points))] @ matrix)[:, :3]
    points *= UsdGeom.GetStageMetersPerUnit(stage)
    layout = json.loads(LAYOUT.read_text())['Garment']['Top_Long'][0]
    w, x, y, z = layout['default_ori']
    rot = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                    [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                    [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
    points = (points * np.asarray(layout['scale'])) @ rot.T + layout['default_pos']
    assert np.isfinite(points).all() and faces.max() < len(points)
    assets = args.output.resolve()
    assets.mkdir(parents=True,exist_ok=False)
    target = assets/'garment.obj'
    target.write_text(''.join('v %.10g %.10g %.10g\n' % tuple(p) for p in points)
                      + ''.join('f %d %d %d\n' % tuple(f+1) for f in faces))
    manifest = dict(source=str(SOURCE), source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                    layout=str(LAYOUT), layout_sha256=hashlib.sha256(LAYOUT.read_bytes()).hexdigest(),
                    mesh_prim=str(mesh.GetPath()), source_vertices=len(points), triangles=len(faces),
                    bounds_m=[points.min(0).tolist(), points.max(0).tolist()],
                    obj_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                    source_physics=layout['physics'], notes=[
                        'USD mesh transforms, stage units and saved garment placement baked into OBJ.',
                        'PhysX merged state has 9455 nodes; source asset has 9487 vertices.',
                        'Genesis may remesh; report actual solver particle count.',
                        'No material equivalence between PhysX springs and Genesis compliance is assumed.'])
    (assets/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({k:manifest[k] for k in ['source_vertices','triangles','bounds_m']}))


if __name__ == '__main__':
    main()
