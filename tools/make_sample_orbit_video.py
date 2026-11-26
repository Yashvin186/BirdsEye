"""
Generate a synthetic 360-degree orbit video of a textured temple-like building.

Purpose: a known-good input for Birds Eye. Two slow circles (high oblique, then lower) around one subject,
constant zoom, no cuts or fades, rich surface texture. If the app cannot build a complete model from THIS
video, the problem is in the software; if it can, a real video filmed the same way will work too.

Usage:  python tools/make_sample_orbit_video.py out.mp4 [--frames-per-lap 120] [--size 1280x720]
Needs:  numpy, opencv-python, trimesh, scipy
"""
import argparse
import math

import cv2
import numpy as np
import trimesh


def fbm(p, seed=0):
    """Cheap multi-frequency value noise from 3D positions (gives SIFT plenty of texture)."""
    rng = np.random.default_rng(seed)
    out = np.zeros(len(p))
    for k, freq in enumerate((0.7, 1.9, 4.3, 9.1)):
        d = rng.normal(size=3); d /= np.linalg.norm(d)
        ph = rng.uniform(0, 6.28, size=3)
        out += (0.5 ** k) * (np.sin(freq * (p @ d) + ph[0]) * np.sin(freq * 1.3 * p[:, 0] + ph[1]) * np.cos(freq * 0.9 * p[:, 2] + ph[2]))
    return out / 1.9


def build_scene(n_points=4_000_000, seed=0):
    parts = []   # (mesh, base colour, kind)
    box = lambda ext, c: trimesh.creation.box(extents=ext, transform=trimesh.transformations.translation_matrix(c))
    parts.append((box([60, 60, 0.4], [0, 0, -0.2]), (0.30, 0.42, 0.22), "ground"))
    parts.append((box([22, 22, 2.0], [0, 0, 1.0]), (0.74, 0.70, 0.62), "stone"))
    parts.append((box([14, 14, 8.0], [0, 0, 6.0]), (0.62, 0.20, 0.16), "wall"))
    roof = trimesh.creation.cone(radius=11.5, height=6.0, sections=4)
    roof.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 4, [0, 0, 1]))
    roof.apply_translation([0, 0, 10.0])
    parts.append((roof, (0.38, 0.40, 0.44), "roof"))
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl = trimesh.creation.cylinder(radius=1.3, height=9.0, sections=24, transform=trimesh.transformations.translation_matrix([sx * 9.5, sy * 9.5, 6.5]))
            parts.append((cyl, (0.88, 0.86, 0.80), "tower"))
            cap = trimesh.creation.icosphere(subdivisions=3, radius=1.5)
            cap.apply_translation([sx * 9.5, sy * 9.5, 11.5])
            parts.append((cap, (0.85, 0.80, 0.55), "cap"))
    dome = trimesh.creation.icosphere(subdivisions=4, radius=3.0)
    dome.apply_translation([0, 0, 17.0])
    parts.append((dome, (0.86, 0.80, 0.50), "cap"))
    # a small annex so the building is not symmetric (symmetry confuses matching)
    parts.append((box([6, 4, 5], [13.5, -3, 4.5]), (0.55, 0.50, 0.30), "wall"))

    areas = np.array([m.area * (0.35 if k == "ground" else 1.0) for m, _, k in parts]); counts = (n_points * areas / areas.sum()).astype(int)
    P, C = [], []
    for (m, base, kind), n in zip(parts, counts):
        pts, fi = trimesh.sample.sample_surface(m, n, seed=seed)
        nrm = m.face_normals[fi]
        n_ = fbm(pts * 1.0, seed=hash(kind) % 1000)
        col = np.tile(np.array(base), (len(pts), 1)) * (0.72 + 0.5 * n_[:, None])
        if kind in ("wall", "stone"):          # windows / blocks / bricks
            u = pts[:, 0] * nrm[:, 1] + pts[:, 1] * (-nrm[:, 0]) + 0.0
            v = pts[:, 2]
            win = ((np.mod(u, 3.0) < 1.1) & (np.mod(v, 3.0) < 1.6) & (np.abs(nrm[:, 2]) < 0.5))
            col[win] = (0.12, 0.10, 0.12)
            brick = (np.mod(v * 2.0, 1.0) < 0.07) | (np.mod(u * 1.3 + np.floor(v * 2.0) * 0.5, 1.0) < 0.05)
            col[brick] *= 0.55
        if kind == "roof":
            col *= (0.8 + 0.3 * (np.mod(pts[:, 2] * 3.0, 1.0) < 0.12))[:, None]
        if kind == "ground":
            col *= (0.85 + 0.3 * (np.sin(pts[:, 0] * 2.2) * np.sin(pts[:, 1] * 2.7) > 0.4))[:, None]
        P.append(pts); C.append(np.clip(col, 0, 1))
    return np.vstack(P), np.vstack(C)


def look_at(eye, target, up=(0, 0, 1)):
    z = np.asarray(target, float) - eye; z /= np.linalg.norm(z)
    x = np.cross(z, up); x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return np.stack([x, y, z])          # world -> camera rotation (OpenCV convention: x right, y down, z forward)


def render(P, C, eye, target, W, H, f):
    R = look_at(eye, target)
    Pc = (P - eye) @ R.T
    z = Pc[:, 2]
    ok = z > 0.5
    u = (f * Pc[ok, 0] / z[ok] + W / 2).astype(int)
    v = (f * Pc[ok, 1] / z[ok] + H / 2).astype(int)
    inb = (u >= 0) & (u < W) & (v >= 0) & (v < H)
    u, v, zz, cc = u[inb], v[inb], z[ok][inb], C[ok][inb]
    order = np.argsort(-zz)
    sky = np.linspace(0.92, 0.62, H)[:, None, None] * np.array([0.75, 0.85, 1.0])[None, None, :]
    img = np.broadcast_to(sky, (H, W, 3)).copy()
    u, v, cc = u[order], v[order], cc[order]
    # Each point is drawn as a small square, far to near, so nearer surfaces cover farther ones
    # (a point cloud is sparse: without a splat footprint the background shows through the gaps).
    for dx, dy in [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1), (0, 0)]:   # centre last
        uu, vv = np.clip(u + dx, 0, W - 1), np.clip(v + dy, 0, H - 1)
        img[vv, uu] = cc
    return cv2.GaussianBlur((img * 255).astype(np.uint8), (0, 0), 0.7)[:, :, ::-1]      # RGB -> BGR for OpenCV writer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--frames-per-lap", type=int, default=120)
    ap.add_argument("--size", default="1280x720")
    ap.add_argument("--fps", type=int, default=24)
    a = ap.parse_args()
    W, H = (int(x) for x in a.size.split("x"))
    f = 0.95 * W
    P, C = build_scene()
    vw = cv2.VideoWriter(a.out, cv2.VideoWriter_fourcc(*"mp4v"), a.fps, (W, H))
    target = np.array([0.0, 0.0, 6.0])
    laps = [(46.0, 22.0), (40.0, 10.0)]          # (radius, camera height): high oblique, then lower
    n = a.frames_per_lap
    for li, (radius, height) in enumerate(laps):
        for i in range(n):
            ang = 2 * math.pi * i / n + (0.0 if li == 0 else math.pi / n)
            eye = np.array([radius * math.cos(ang), radius * math.sin(ang), height])
            vw.write(render(P, C, eye, target, W, H, f))
    vw.release()
    print("wrote", a.out)


if __name__ == "__main__":
    main()
