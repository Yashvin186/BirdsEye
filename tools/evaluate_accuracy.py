"""
Accuracy check on a SYNTHETIC scene with known dimensions (tools/make_sample_orbit_video.py).

The generator knows the exact camera path and the exact building (metres). After a reconstruction we
  1. fit a similarity transform (scale, rotation, translation) from the reconstructed camera centres to the true ones,
  2. report the camera-position error in metres and how many cameras were registered,
  3. measure the reconstructed model against the true surfaces (median / 90th-percentile distance, metres),
  4. read known lengths off the model (building height, ground-to-dome) and compare.
This is a SYNTHETIC test: it proves the pipeline's geometry is consistent, not that real footage will be as exact.

Usage: python tools/evaluate_accuracy.py <project_outputs_dir> <n_source_frames=240> <n_used=80> <frames_per_lap=120>
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).parent))
from make_sample_orbit_video import build_scene  # noqa: E402


def umeyama(src, dst):
    mu_s, mu_d = src.mean(0), dst.mean(0)
    xs, xd = src - mu_s, dst - mu_d
    U, S, Vt = np.linalg.svd(xd.T @ xs / len(src))
    D = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        D[2, 2] = -1
    R = U @ D @ Vt
    s = np.trace(np.diag(S) @ D) / ((xs ** 2).sum() / len(src))
    return s, R, mu_d - s * R @ mu_s


def true_cam(i, n=120):
    laps = [(46.0, 22.0), (40.0, 10.0)]
    li, k = divmod(i, n)
    r, h = laps[li]
    ang = 2 * math.pi * k / n + (0.0 if li == 0 else math.pi / n)
    return np.array([r * math.cos(ang), r * math.sin(ang), h])


def main(out_dir, n_src=240, n_used=80, per_lap=120):
    out = Path(out_dir)
    cams = json.loads((out / "cameras.json").read_text())
    idx = np.unique(np.linspace(0, n_src - 1, n_used).round().astype(int))
    src, dst = [], []
    for c in cams:
        k = int(c["name"].split("_")[1].split(".")[0]) - 1
        src.append(c["position"]); dst.append(true_cam(int(idx[k]), per_lap))
    src, dst = np.array(src), np.array(dst)
    s, R, t = umeyama(src, dst)
    # robust: refit on the better 80 %
    for _ in range(2):
        err = np.linalg.norm(s * src @ R.T + t - dst, axis=1)
        keep = err <= np.percentile(err, 80)
        s, R, t = umeyama(src[keep], dst[keep])
    err = np.linalg.norm(s * src @ R.T + t - dst, axis=1)
    print(f"cameras registered: {len(cams)}/{n_used}")
    print(f"scale: 1 model unit = {s:.3f} m | camera position error: median {np.median(err):.2f} m, 90th pct {np.percentile(err, 90):.2f} m (orbit radius 40-46 m)")

    mesh_f = out / "model_mesh.ply"
    m = trimesh.load(mesh_f, process=False)
    v = s * np.asarray(m.vertices) @ R.T + t
    P, _ = build_scene(n_points=1)   # only to reuse geometry builder is not enough: rebuild meshes below
    parts = []
    box = lambda ext, c: trimesh.creation.box(extents=ext, transform=trimesh.transformations.translation_matrix(c))
    parts += [box([22, 22, 2.0], [0, 0, 1.0]), box([14, 14, 8.0], [0, 0, 6.0]), box([6, 4, 5], [13.5, -3, 4.5])]
    roof = trimesh.creation.cone(radius=11.5, height=6.0, sections=4); roof.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 4, [0, 0, 1])); roof.apply_translation([0, 0, 10.0]); parts.append(roof)
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(trimesh.creation.cylinder(radius=1.3, height=9.0, sections=24, transform=trimesh.transformations.translation_matrix([sx * 9.5, sy * 9.5, 6.5])))
    dome = trimesh.creation.icosphere(subdivisions=4, radius=3.0); dome.apply_translation([0, 0, 17.0]); parts.append(dome)
    gt = trimesh.util.concatenate(parts)
    sel = v[(v[:, 2] > 0.5) & (np.abs(v[:, 0]) < 20) & (np.abs(v[:, 1]) < 20)]       # building region only (ground excluded)
    if len(sel) > 20000:
        sel = sel[np.random.default_rng(0).choice(len(sel), 20000, replace=False)]
    d = np.abs(trimesh.proximity.signed_distance(gt, sel))
    print(f"surface error vs true building ({len(sel)} vertices): median {np.median(d):.2f} m, 90th pct {np.percentile(d, 90):.2f} m")
    top = v[:, 2].max()
    print(f"highest point of the model: {top:.1f} m above true ground level (true dome top = 20.0 m)")


if __name__ == "__main__":
    a = sys.argv
    main(a[1], *(int(x) for x in a[2:5]))
