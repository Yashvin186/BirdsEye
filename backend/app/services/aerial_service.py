"""
Aerial-survey mode: a drone flying over a place (infrastructure, disaster area, site) looking (nearly) straight down
does not film an "object" from several sides - it films the GROUND. Treating that as an object (subject isolation,
Poisson shell, "only one side filmed") throws most of the scene away.

This service handles that case the way survey photogrammetry does:
  1. detect it from the solved camera poses (optical axes ~parallel, cameras roughly on one plane),
  2. fit a ground plane and build a digital surface model (DSM, a height grid) from the well-triangulated SfM points,
  3. build an orthomosaic: every ground cell takes its colour from the frame that saw it most directly overhead,
  4. triangulate the DSM into a textured mesh (GLB/OBJ/PLY) plus DSM and orthomosaic images.

It is fast (seconds, no GPU, no dense stereo) and uses every registered frame.
"""
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import cv2
import numpy as np

from app.services.cpu_dense_service import CpuDenseService
from app.services.subject_service import SubjectService


class AerialService:
    NADIR_MAX_AXIS_SPREAD_DEG = 30.0   # optical axes must agree with their mean within this
    NADIR_MIN_TILT_DEG = 35.0          # mean optical axis must be at least this far from horizontal
    HEIGHT_GRID_COLS = 420             # DSM / mesh resolution along the longer side
    TEXTURE_LONG_SIDE = 4096           # fallback; normally sized to the real image detail (see MAX_TEXTURE)
    MAX_TEXTURE = 6144                 # long side cap (memory + GPU texture limits)
    MIN_POINTS = 200
    VERTICAL_EXAGGERATION = 2.0        # relief is ~1-2% of the footprint; 2x makes it readable in the viewer

    # ------------------------------------------------------------------ detection
    @classmethod
    def detect(cls, model_dir: Path) -> Dict[str, Any]:
        try:
            _cams, images = CpuDenseService.read_text_model(model_dir)
        except Exception as exc:
            return {"is_aerial": False, "reason": f"poses unreadable: {exc}"}
        if len(images) < 6:
            return {"is_aerial": False, "reason": "too few cameras"}
        axes = np.array([im["R"][2] for im in images])
        mean_axis = axes.mean(axis=0)
        if np.linalg.norm(mean_axis) < 1e-6:
            return {"is_aerial": False, "reason": "cameras look in opposing directions"}
        mean_axis /= np.linalg.norm(mean_axis)
        spread = np.degrees(np.arccos(np.clip(axes @ mean_axis, -1, 1)))
        centres = np.array([im["C"] for im in images])
        # Camera centres should spread mostly across the plane perpendicular to the viewing axis (a survey grid).
        c = centres - centres.mean(axis=0)
        along = c @ mean_axis
        across = c - np.outer(along, mean_axis)
        ratio = float(np.linalg.norm(across, axis=1).std() / max(along.std(), 1e-9))
        # Tilt of the optical axis from the world horizon is unknown (arbitrary SfM frame), so use the ground the
        # cameras see: points should lie "below" the cameras along the mean axis.
        pts = SubjectService.read_sparse_points(model_dir)
        below = float(np.mean((pts - centres.mean(axis=0)) @ mean_axis > 0)) if len(pts) else 0.0
        is_aerial = bool(np.percentile(spread, 90) <= cls.NADIR_MAX_AXIS_SPREAD_DEG and ratio >= 2.0 and below > 0.9
                         and len(pts) >= cls.MIN_POINTS)
        return {"is_aerial": is_aerial, "axis_spread_p90_deg": round(float(np.percentile(spread, 90)), 1),
                "path_planarity_ratio": round(ratio, 2), "points_in_front_fraction": round(below, 2)}


    # ------------------------------------------------------------------ dense heights (plane-sweep stereo)
    @classmethod
    def plane_sweep(cls, images, cams, frames_dir: Path, a, up, c, x0, z1, cell, nx, nz, prior, valid,
                    height_range: float, levels: int = 40, max_images: int = 30, log=None):
        """Per-cell height by photo-consistency: for every candidate height, project the cell into every
        frame that sees it and measure how well the (locally normalised) intensities agree. The height with the
        best agreement, anchored to the sparse terrain `prior`, wins. Works on CPU, no CUDA needed."""
        log = log or (lambda s: None)
        GX, GZ = np.meshgrid(x0 + np.arange(nx) * cell, z1 - np.arange(nz) * cell)
        base = (GX.reshape(-1, 1) * a + GZ.reshape(-1, 1) * c).astype(np.float64)
        h0 = np.where(valid, prior, np.nanmedian(prior)).reshape(-1).astype(np.float64)
        sel = np.linspace(0, len(images) - 1, min(max_images, len(images))).astype(int)
        offs = np.linspace(-height_range, height_range, levels)
        cams_data = []
        for k in sel:
            im = images[int(k)]
            path = frames_dir / im["name"]
            g = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE) if path.exists() else None
            if g is None:
                continue
            cam = cams[im["camera_id"]]
            sx, sy = g.shape[1] / cam["w"], g.shape[0] / cam["h"]
            K = cam["K"].copy()
            K[0] *= sx
            K[1] *= sy
            if np.any(np.abs(cam["D"]) > 1e-9):
                g = cv2.undistort(g, K, cam["D"])
            g = cv2.GaussianBlur(g.astype(np.float32) / 255.0, (0, 0), 1.0)
            R, tv = im["R"], im["t"]
            Rb = base @ R.T + tv                               # (N,3) camera coords of the ground-plane cell
            Ru = R @ up                                        # camera-space direction of "up" (height changes)
            cams_data.append((g, K, Rb.astype(np.float32), Ru.astype(np.float32)))
        if len(cams_data) < 3:
            return None
        N = nx * nz
        np.full(N, np.inf, np.float32)
        np.zeros(N, np.int32)
        cost_vol = np.empty((levels, nz, nx), np.float32)
        for li, off in enumerate(offs):
            hs = (h0 + off).astype(np.float32)
            s1 = np.zeros(N, np.float32); s2 = np.zeros(N, np.float32); cnt = np.zeros(N, np.float32)
            for g, K, Rb, Ru in cams_data:
                X = Rb + hs[:, None] * Ru
                z = X[:, 2]
                zz = np.where(z > 1e-6, z, 1.0)
                u = K[0, 0] * X[:, 0] / zz + K[0, 2]
                v = K[1, 1] * X[:, 1] / zz + K[1, 2]
                ok = (z > 1e-6) & (u > 3) & (u < g.shape[1] - 4) & (v > 3) & (v < g.shape[0] - 4)
                S = cv2.remap(g, u.reshape(nz, nx).astype(np.float32), v.reshape(nz, nx).astype(np.float32), cv2.INTER_LINEAR)
                m = cv2.boxFilter(S, -1, (7, 7)); q = cv2.boxFilter(S * S, -1, (7, 7))
                Sn = (S - m) / np.sqrt(np.maximum(q - m * m, 0) + 4e-4)
                Sn = Sn.reshape(-1) * ok
                s1 += Sn; s2 += Sn * Sn; cnt += ok
            var = np.where(cnt >= 3, s2 / np.maximum(cnt, 1) - (s1 / np.maximum(cnt, 1)) ** 2, 2.0)
            cv = cv2.boxFilter(var.reshape(nz, nx).astype(np.float32), -1, (5, 5))
            cv += 0.18 * (off / height_range) ** 2              # stay close to the measured sparse terrain unless photos disagree
            cost_vol[li] = cv
        idx = np.argmin(cost_vol, axis=0)
        # parabolic sub-level refinement
        ii = np.clip(idx, 1, levels - 2)
        rr, cc = np.indices(idx.shape)
        c0, c1, c2 = cost_vol[ii - 1, rr, cc], cost_vol[ii, rr, cc], cost_vol[ii + 1, rr, cc]
        den = c0 - 2 * c1 + c2
        sub = np.where(np.abs(den) > 1e-9, 0.5 * (c0 - c2) / den, 0.0).clip(-1, 1)
        step = offs[1] - offs[0]
        dh = offs[ii] + sub * step
        dh = np.where((idx == 0) | (idx == levels - 1), offs[idx], dh)
        # Cells whose best height sits at the edge of the search window have no trustworthy photo agreement
        # (few overlapping frames, repeating texture): fall back to the measured sparse terrain there.
        edge = (np.abs(dh) > 0.9 * height_range)
        edge = cv2.dilate(edge.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
        dh = np.where(edge, 0.0, dh)
        out = (h0.reshape(nz, nx) + dh).astype(np.float64)
        out = cv2.medianBlur(out.astype(np.float32), 5)
        out = cv2.GaussianBlur(out, (0, 0), 1.2).astype(np.float64)
        log(f"Plane-sweep stereo: {len(cams_data)} frames x {levels} height levels on a {nx}x{nz} grid.")
        return out

    # ------------------------------------------------------------------ build
    @classmethod
    def build(cls, project_dir: Path, model_dir: Path, preset=None, georef: Optional[Dict[str, Any]] = None,
              log: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        import trimesh
        from PIL import Image
        from scipy import ndimage
        from scipy.interpolate import LinearNDInterpolator
        from scipy.spatial import cKDTree

        log = log or (lambda s: None)
        project_dir, model_dir = Path(project_dir), Path(model_dir)
        out = project_dir / "outputs"
        out.mkdir(parents=True, exist_ok=True)

        cams, images = CpuDenseService.read_text_model(model_dir)
        pts = SubjectService.read_sparse_points(model_dir, max_error=1.0, min_track=3)
        if len(pts) < cls.MIN_POINTS:
            return {"status": "failed", "reason": f"only {len(pts)} reliable sparse points for a terrain model"}

        up = -np.mean([im["R"][2] for im in images], axis=0)
        up /= np.linalg.norm(up)
        a = np.cross(up, [1.0, 0.0, 0.0])
        if np.linalg.norm(a) < 1e-3:
            a = np.cross(up, [0.0, 0.0, 1.0])
        a /= np.linalg.norm(a)
        c = np.cross(a, up)                                  # (a, up, c) is right-handed -> y-up in three.js

        # Level the model: the camera axes only approximate the ground normal, so fit the dominant plane to the
        # points (trimmed least squares) and use ITS normal as "up" - otherwise the height model is tilted.
        for _ in range(4):
            loc = np.column_stack([pts @ a, pts @ up, pts @ c])
            m = np.abs(loc[:, 1] - np.median(loc[:, 1])) < 3.0 * (np.median(np.abs(loc[:, 1] - np.median(loc[:, 1]))) * 1.4826 + 1e-9)
            A = np.column_stack([loc[m, 0], loc[m, 2], np.ones(m.sum())])
            coef, *_ = np.linalg.lstsq(A, loc[m, 1], rcond=None)
            n = up - coef[0] * a - coef[1] * c
            n /= np.linalg.norm(n)
            if float(n @ up) < 0:
                n = -n
            up = n
            a = a - (a @ up) * up
            a /= np.linalg.norm(a)
            c = np.cross(a, up)

        # North-up: with GPS the map's x axis is made to point east (the ground plane is kept, so this is a pure rotation about 'up').
        geo_ok = bool(georef and georef.get("status") == "gps_aligned")
        if geo_ok:
            east = np.array(georef["east_sfm"], dtype=float)
            if float(up @ np.array(georef["up_sfm"], dtype=float)) < 0:
                up = -up
            e_h = east - (east @ up) * up
            if np.linalg.norm(e_h) > 1e-6:
                a = e_h / np.linalg.norm(e_h)
                c = np.cross(a, up)

        def to_local(p):
            return np.column_stack([p @ a, p @ up, p @ c])

        local = to_local(pts)
        # Reject gross height outliers (mismatches far above / below the ground).
        h = local[:, 1]
        med = np.median(h)
        mad = np.median(np.abs(h - med)) * 1.4826 + 1e-9
        keep = np.abs(h - med) < 6.0 * mad
        local = local[keep]
        log(f"Aerial survey: {len(local)} reliable ground points after outlier rejection.")

        x0, x1 = np.percentile(local[:, 0], [0.5, 99.5])
        z0, z1 = np.percentile(local[:, 2], [0.5, 99.5])
        W, H = x1 - x0, z1 - z0
        cell = max(W, H) / cls.HEIGHT_GRID_COLS
        nx, nz = int(W / cell) + 1, int(H / cell) + 1
        gx = x0 + np.arange(nx) * cell
        gz = z1 - np.arange(nz) * cell                      # row 0 = far edge so the texture reads upright
        GX, GZ = np.meshgrid(gx, gz)

        interp = LinearNDInterpolator(local[:, [0, 2]], local[:, 1])
        DSM = interp(GX, GZ)
        # Cells far from any reliable point stay empty instead of being invented.
        tree = cKDTree(local[:, [0, 2]])
        dist, _ = tree.query(np.column_stack([GX.ravel(), GZ.ravel()]))
        spacing = np.median(tree.query(local[::max(1, len(local) // 3000), [0, 2]], k=2)[0][:, 1])
        valid = (~np.isnan(DSM)) & (dist.reshape(DSM.shape) < max(14 * spacing, 4 * cell))
        valid = ndimage.binary_closing(valid, iterations=2)
        valid = ndimage.binary_fill_holes(valid)
        # Holes the Delaunay hull left (NaN inside the footprint) take the nearest measured height.
        nanmask = np.isnan(DSM) & valid
        if nanmask.any() and (~np.isnan(DSM)).any():
            idx = ndimage.distance_transform_edt(np.isnan(DSM), return_distances=False, return_indices=True)
            DSM = np.where(nanmask, DSM[tuple(idx)], DSM)
        DSM = np.where(valid, DSM, np.nan)
        # NaN-aware light smoothing (removes triangulation noise, keeps edges of buildings reasonably).
        filled = np.where(valid, DSM, 0.0)
        wsm = ndimage.gaussian_filter(valid.astype(float), 1.0)
        DSM_s = ndimage.gaussian_filter(filled, 1.0) / np.maximum(wsm, 1e-6)
        DSM = np.where(valid, 0.7 * DSM_s + 0.3 * np.nan_to_num(DSM), np.nan)
        ground_cover = float(valid.mean())
        log(f"DSM grid {nx}x{nz} cells, {ground_cover * 100:.0f}% of the footprint is supported by measured points.")

        # ---------------------------------------------------------------- dense heights (plane-sweep stereo)
        dense = False
        try:
            f = 2                                                # refine on a grid twice as fine
            nx2, nz2, cell2 = nx * f, nz * f, cell / f
            gx2 = x0 + np.arange(nx2) * cell2
            gz2 = z1 - np.arange(nz2) * cell2
            GX2, GZ2 = np.meshgrid(gx2, gz2)
            prior_f = np.where(valid, DSM, np.nanmedian(DSM))
            prior2 = cv2.resize(prior_f.astype(np.float32), (nx2, nz2), interpolation=cv2.INTER_LINEAR).astype(np.float64)
            valid2 = cv2.resize(valid.astype(np.uint8), (nx2, nz2), interpolation=cv2.INTER_NEAREST).astype(bool)
            hr = 0.02 * max(W, H)                                # real relief of a site is ~1-2% of its footprint
            res = cls.plane_sweep(images, cams, project_dir / "frames", a, up, c, x0, z1, cell2, nx2, nz2,
                                  prior2, valid2, height_range=hr, log=log)
            if res is not None:
                DSM = np.where(valid2, res, np.nan)
                valid, GX, GZ, cell, nx, nz = valid2, GX2, GZ2, cell2, nx2, nz2
                dense = True
        except Exception as exc:  # dense refinement is an upgrade, never a reason to fail the job
            log(f"Dense height refinement skipped ({exc}); using sparse terrain.")

        # ---------------------------------------------------------------- clean-up: floating slivers / height outliers
        try:
            dfill = np.where(valid, DSM, np.nanmedian(DSM)).astype(np.float32)
            sm = cv2.resize(dfill, (max(nx // 4, 8), max(nz // 4, 8)), interpolation=cv2.INTER_AREA)
            local = cv2.resize(ndimage.median_filter(sm, size=9, mode="nearest"), (nx, nz), interpolation=cv2.INTER_LINEAR)
            dev = np.abs(dfill - local)
            mad = float(np.median(dev[valid])) * 1.4826 + 1e-9
            valid = valid & (dev < 6.0 * mad + 0.004 * max(W, H))
            lab_cc, ncc = ndimage.label(valid)
            if ncc > 1:
                sizes = ndimage.sum(valid, lab_cc, index=np.arange(1, ncc + 1))
                keep_ids = [i + 1 for i, s_ in enumerate(sizes) if s_ >= 0.25 * sizes.max()]
                valid = np.isin(lab_cc, keep_ids)
            DSM = np.where(valid, DSM, np.nan)
            log(f"Clean-up: kept {int(valid.sum())} ground cells in {len(keep_ids) if ncc > 1 else 1} connected area(s).")
        except Exception as exc:
            log(f"Clean-up skipped ({exc}).")

        # ---------------------------------------------------------------- orthomosaic
        # Size the orthomosaic to the real image detail: one texel ~ one source pixel on the ground (GSD).
        depths, focals = [], []
        for im in images:
            cam = cams[im["camera_id"]]
            Z = (pts @ im["R"][2]) + im["t"][2]
            Z = Z[Z > 0]
            if len(Z):
                depths.append(float(np.median(Z)))
                focals.append(float(cam["K"][0, 0]))
        gsd_sfm = float(np.median(np.array(depths) / np.array(focals))) if depths else max(W, H) / cls.TEXTURE_LONG_SIDE
        long_px = int(np.clip(max(W, H) / max(gsd_sfm, 1e-9), 2048, cls.MAX_TEXTURE))
        tex_w = long_px if W >= H else int(long_px * W / H)
        tex_h = int(tex_w * H / W) if W >= H else long_px
        tex_w, tex_h = max(tex_w, 256), max(tex_h, 256)
        log(f"Image detail on the ground: 1 source pixel = {gsd_sfm:.5f} model units; orthomosaic sized {tex_w}x{tex_h}px to match.")
        tx = (x0 + (np.arange(tex_w) + 0.5) * (W / tex_w)).astype(np.float32)
        tz = (z1 - (np.arange(tex_h) + 0.5) * (H / tex_h)).astype(np.float32)
        TX, TZ = np.meshgrid(tx, tz)
        gxs = np.clip((TX - x0) / cell, 0, nx - 1)
        gzs = np.clip((z1 - TZ) / cell, 0, nz - 1)
        dsm_filled = np.where(valid, DSM, np.nanmedian(DSM))
        TY = ndimage.map_coordinates(dsm_filled, [gzs, gxs], order=1, mode="nearest")
        world = np.empty((tex_h * tex_w, 3), np.float32)                                      # local -> world (float32: memory)
        for k in range(3):
            world[:, k] = (TX * a[k] + TY * up[k] + TZ * c[k]).reshape(-1)
        del TX, TY, TZ, gxs, gzs

        # Choose, per coarse cell, the frame that sees it most directly and most centrally.
        step = 8
        lo_idx = np.arange(0, tex_h * tex_w).reshape(tex_h, tex_w)[::step, ::step]
        Plo = world[lo_idx.ravel()]
        best_w = np.full(len(Plo), -1.0)
        best_i = np.zeros(len(Plo), dtype=np.int32)
        frames_dir = project_dir / "frames"
        names, Ks, Ds, sizes = [], [], [], []
        for k, im in enumerate(images):
            cam = cams[im["camera_id"]]
            Xc = Plo @ im["R"].T + im["t"]
            z = Xc[:, 2]
            uv = cv2.projectPoints(Plo.reshape(-1, 1, 3), cv2.Rodrigues(im["R"])[0], im["t"], cam["K"], cam["D"])[0].reshape(-1, 2)
            u, v = uv[:, 0] / cam["w"], uv[:, 1] / cam["h"]
            inside = (z > 0) & (u > 0.04) & (u < 0.96) & (v > 0.04) & (v < 0.96)
            ray = Xc / np.maximum(np.linalg.norm(Xc, axis=1, keepdims=True), 1e-12)
            wgt = np.where(inside, (ray[:, 2] ** 4) * (1.2 - np.hypot(u - 0.5, v - 0.5)), -1.0)
            better = wgt > best_w
            best_w[better] = wgt[better]
            best_i[better] = k
            names.append(im["name"])
        lab_lo = best_i.reshape(lo_idx.shape)
        lab = cv2.resize(lab_lo.astype(np.int32).astype(np.float32), (tex_w, tex_h), interpolation=cv2.INTER_NEAREST).astype(np.int32)
        lab = ndimage.median_filter(lab, size=9)             # remove 1-texel label speckle -> fewer seams
        supported = ndimage.zoom((best_w >= 0).reshape(lo_idx.shape).astype(np.uint8), (tex_h / lo_idx.shape[0], tex_w / lo_idx.shape[1]), order=0)
        supported = supported[:tex_h, :tex_w]

        num = np.zeros((tex_h, tex_w, 3), np.float32)
        den = np.zeros((tex_h, tex_w), np.float32)
        wflat = world
        sig = max(tex_w / 160.0, 6.0)                         # feather width ~ 0.6% of the map: hides tone seams
        for k in np.unique(lab):
            im = images[int(k)]
            path = frames_dir / im["name"]
            bgr = cv2.imread(str(path)) if path.exists() else None
            if bgr is None:
                continue
            cam = cams[im["camera_id"]]
            sx, sy = bgr.shape[1] / cam["w"], bgr.shape[0] / cam["h"]
            small = cv2.resize((lab == k).astype(np.float32), (tex_w // 4, tex_h // 4), interpolation=cv2.INTER_AREA)
            small = cv2.GaussianBlur(small, (0, 0), sig / 4.0)
            wmap = cv2.resize(small, (tex_w, tex_h), interpolation=cv2.INTER_LINEAR)
            idx = np.flatnonzero(wmap.ravel() > 0.01)
            if len(idx) == 0:
                continue
            uv = cv2.projectPoints(wflat[idx].reshape(-1, 1, 3), cv2.Rodrigues(im["R"])[0], im["t"], cam["K"], cam["D"])[0].reshape(-1, 2)
            mx = np.full(tex_h * tex_w, -1, np.float32)
            my = np.full(tex_h * tex_w, -1, np.float32)
            mx[idx] = uv[:, 0] * sx
            my[idx] = uv[:, 1] * sy
            mx, my = mx.reshape(tex_h, tex_w), my.reshape(tex_h, tex_w)
            samp = cv2.remap(bgr, mx, my, cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
            inb = ((mx > 2) & (mx < bgr.shape[1] - 3) & (my > 2) & (my < bgr.shape[0] - 3)).astype(np.float32)
            w_ = wmap * inb
            num += samp.astype(np.float32) * w_[..., None]
            den += w_
        tex = np.clip(num / np.maximum(den[..., None], 1e-6), 0, 255).astype(np.uint8)
        tex[den < 1e-3] = 0
        # Fill any texels no frame could provide so the mesh never shows black holes.
        empty = (tex.sum(axis=2) == 0)
        if empty.any() and (~empty).any():
            tex = cv2.inpaint(tex, empty.astype(np.uint8) * 255, 3, cv2.INPAINT_TELEA)
        ortho_path = out / "orthomosaic.jpg"
        cv2.imwrite(str(ortho_path), tex, [cv2.IMWRITE_JPEG_QUALITY, 92])
        log(f"Orthomosaic {tex_w}x{tex_h}px written ({len(np.unique(lab))} frames contribute).")

        # ---------------------------------------------------------------- DSM preview + mesh
        d = np.where(valid, DSM, np.nan)
        lo_, hi_ = np.nanpercentile(d, [2, 98])
        dsm_img = np.nan_to_num((np.clip(d, lo_, hi_) - lo_) / max(hi_ - lo_, 1e-9), nan=0.0)
        dsm_col = cv2.applyColorMap((dsm_img * 255).astype(np.uint8), cv2.COLORMAP_TURBO)
        dsm_col[~valid] = 25
        cv2.imwrite(str(out / "dsm_heightmap.png"), dsm_col)

        scale = 10.0 / max(W, H)                              # viewer-friendly size; relative units
        vid = -np.ones(DSM.shape, dtype=np.int64)
        vid[valid] = np.arange(int(valid.sum()))
        verts = np.column_stack([(GX[valid] - (x0 + W / 2)) * scale,
                                 (DSM[valid] - np.nanmin(DSM)) * scale * cls.VERTICAL_EXAGGERATION,
                                 (GZ[valid] - (z0 + H / 2)) * scale])
        np.column_stack([(GX[valid] - x0) / W, (GZ[valid] - z0) / H])
        v00, v01, v10, v11 = vid[:-1, :-1], vid[:-1, 1:], vid[1:, :-1], vid[1:, 1:]
        quad = (v00 >= 0) & (v01 >= 0) & (v10 >= 0) & (v11 >= 0)
        # Drop cells that sit on a cliff (height jump >> neighbours) = unreliable interpolation across a gap.
        dz = np.maximum.reduce([np.abs(DSM[:-1, :-1] - DSM[:-1, 1:]), np.abs(DSM[:-1, :-1] - DSM[1:, :-1])])
        if not dense:
            quad &= np.nan_to_num(dz, nan=1e9) < 8 * np.nanmedian(np.abs(np.diff(DSM, axis=1))) + 1e-9
        f1 = np.column_stack([v00[quad], v10[quad], v01[quad]])
        f2 = np.column_stack([v01[quad], v10[quad], v11[quad]])
        faces = np.vstack([f1, f2])
        mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        mesh.remove_unreferenced_vertices()
        # Re-map UVs after vertex removal (vertex order is preserved by trimesh; recompute from positions).
        # (vertex x/z positions are unaffected by the vertical exaggeration)
        uv_full = np.column_stack([(mesh.vertices[:, 0] / scale + (x0 + W / 2) - x0) / W,
                                   (mesh.vertices[:, 2] / scale + (z0 + H / 2) - z0) / H])
        pil = Image.fromarray(cv2.cvtColor(tex, cv2.COLOR_BGR2RGB))
        mesh.visual = trimesh.visual.TextureVisuals(uv=uv_full, image=pil)

        glb = out / "model.glb"
        mesh.export(str(glb))
        obj = out / "model.obj"
        try:
            mesh.export(str(obj))
        except Exception:
            obj = glb
        ply = out / "model_mesh.ply"
        plain = trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces, process=False)
        plain.visual.vertex_colors = _vertex_colors(tex, uv_full)
        plain.export(str(ply))
        shutil_copy = out / "cleaned_mesh.ply"
        plain.export(str(shutil_copy))
        dims = (mesh.bounds[1] - mesh.bounds[0]).tolist()
        extra = {"ground_size_sfm": [float(W), float(H)], "gsd_sfm_units": gsd_sfm}
        if geo_ok:
            mpu = float(georef["metres_per_unit"])
            extra.update({"metres_per_scene_unit": mpu * max(W, H) / 10.0, "ground_size_m": [round(W * mpu, 1), round(H * mpu, 1)],
                          "gsd_cm": round(gsd_sfm * mpu * 100.0, 2), "north_up": True})
        return {**extra,
            "status": "completed", "method": "aerial_dsm_orthomosaic", "texture_type": "orthomosaic",
            "source_cloud_type": "sparse_sfm_dsm", "unseen_regions": "left_empty",
            "vertex_count": int(len(mesh.vertices)), "face_count": int(len(mesh.faces)),
            "dimensions": dims, "ground_support_fraction": round(ground_cover, 3),
            "grid": [int(nx), int(nz)], "dense_heights": dense, "vertical_exaggeration": cls.VERTICAL_EXAGGERATION, "texture_size": [int(tex_w), int(tex_h)],
            "glb_path": str(glb), "obj_path": str(obj), "mesh_ply_path": str(ply),
            "orthomosaic_path": str(ortho_path), "dsm_path": str(out / "dsm_heightmap.png"),
        }


def _vertex_colors(tex_bgr: np.ndarray, uv: np.ndarray) -> np.ndarray:
    h, w = tex_bgr.shape[:2]
    px = np.clip((uv[:, 0] * (w - 1)).astype(int), 0, w - 1)
    py = np.clip(((1.0 - uv[:, 1]) * (h - 1)).astype(int), 0, h - 1)
    rgb = tex_bgr[py, px][:, ::-1]
    return np.column_stack([rgb, np.full(len(rgb), 255, np.uint8)]).astype(np.uint8)
