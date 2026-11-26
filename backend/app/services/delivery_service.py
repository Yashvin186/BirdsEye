"""
Output QA + delivery package.

Output QA follows the review checklist in the photogrammetry guides ("check holes, warped geometry, stretched
textures before delivering"):
  * holes    - share of mesh edges that belong to only one triangle (open boundary). A height-field terrain
               legitimately has an outer border; we subtract the expected border and report the rest.
  * stretch  - texture stretch per triangle = (3D area / UV area) relative to the median; share of triangles > 4x
  * degenerate triangles
Delivery package (outputs/delivery/ + birdseye_delivery.zip): master GLB, lite GLB (2048 px JPEG texture, for
phones/web), orthomosaic, DSM, georeference.json, QA reports and a README that states units and limits honestly.
"""
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict

import numpy as np


class DeliveryService:
    LITE_TEXTURE = 2048

    @classmethod
    def output_qa(cls, glb: Path) -> Dict[str, Any]:
        import trimesh
        try:
            scene = trimesh.load(str(glb), force="mesh")
        except Exception as exc:
            return {"available": False, "reason": f"model unreadable: {exc}"}
        f = np.asarray(scene.faces)
        v = np.asarray(scene.vertices)
        if len(f) == 0:
            return {"available": False, "reason": "model has no faces"}
        edges = np.sort(np.vstack([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1)
        _, cnt = np.unique(edges, axis=0, return_counts=True)
        boundary = int((cnt == 1).sum())
        # expected outer border of a grid-like surface ~ 4*sqrt(faces/2)
        expected = 4.0 * np.sqrt(len(f) / 2.0)
        hole_edges = max(0.0, boundary - 1.5 * expected)
        hole_pct = 100.0 * hole_edges / max(len(cnt), 1)

        a3 = 0.5 * np.linalg.norm(np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]), axis=1)
        degenerate = int((a3 < 1e-12).sum())
        stretch_pct = None
        uv = getattr(getattr(scene, "visual", None), "uv", None)
        if uv is not None and len(uv) == len(v):
            u = np.asarray(uv)
            d1, d2 = u[f[:, 1]] - u[f[:, 0]], u[f[:, 2]] - u[f[:, 0]]
            auv = 0.5 * np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0])
            ok = (auv > 1e-12) & (a3 > 1e-12)
            if ok.sum() > 10:
                ratio = a3[ok] / auv[ok]
                med = np.median(ratio)
                stretch_pct = 100.0 * float(((ratio > 4 * med) | (ratio < med / 4)).mean())
        issues = []
        if hole_pct > 2.0:
            issues.append(f"About {hole_pct:.1f} % of mesh edges are open (holes / missing surface).")
        if stretch_pct is not None and stretch_pct > 5.0:
            issues.append(f"{stretch_pct:.1f} % of triangles have visibly stretched texture (steep or poorly observed surfaces).")
        if degenerate > 0.001 * len(f):
            issues.append(f"{degenerate} degenerate triangles.")
        verdict = "good" if not issues else ("review" if (hole_pct < 8 and (stretch_pct or 0) < 15) else "poor")
        return {
            "available": True, "verdict": verdict, "faces": int(len(f)), "vertices": int(len(v)),
            "hole_edge_percent": round(hole_pct, 2),
            "stretched_texture_percent": None if stretch_pct is None else round(stretch_pct, 2),
            "degenerate_faces": degenerate, "issues": issues,
        }

    @classmethod
    def _lite_glb(cls, glb: Path, dest: Path) -> bool:
        import trimesh
        try:
            m = trimesh.load(str(glb), force="mesh")
            img = getattr(getattr(m.visual, "material", None), "image", None)
            if img is None:
                shutil.copyfile(glb, dest)
                return True
            img = img.convert("RGB")
            img.thumbnail((cls.LITE_TEXTURE, cls.LITE_TEXTURE))
            m.visual = trimesh.visual.TextureVisuals(uv=m.visual.uv, image=img)
            m.export(str(dest))
            return True
        except Exception:
            return False

    @classmethod
    def build(cls, project_dir: Path, job: Dict[str, Any], log=None) -> Dict[str, Any]:
        log = log or (lambda s: None)
        out = Path(project_dir) / "outputs"
        glb = out / "model.glb"
        res: Dict[str, Any] = {"available": False}
        if not glb.exists():
            res["reason"] = "No model.glb was produced, so there is nothing to package."
            return res
        qa = cls.output_qa(glb)
        (out / "output_qa.json").write_text(json.dumps(qa, indent=2), encoding="utf-8")
        log(f"Output QA: {qa.get('verdict', 'n/a')} " + "; ".join(qa.get("issues", [])))

        d = out / "delivery"
        if d.exists():
            shutil.rmtree(d)
        d.mkdir()
        shutil.copyfile(glb, d / "model_master.glb")
        lite_ok = cls._lite_glb(glb, d / "model_lite.glb")
        for name in ("orthomosaic.jpg", "dsm.tif", "dsm.npy", "georeference.json", "capture_qa.json", "output_qa.json", "quality_report.md"):
            if (out / name).exists():
                shutil.copyfile(out / name, d / name)
        geo = job.get("georef_result") or {}
        mesh = job.get("mesh_result") or {}
        if geo.get("status") == "gps_aligned":
            units = (f"Scale: GPS-derived. 1 model unit = {geo['metres_per_unit']:.4f} m (alignment RMSE {geo['rmse_m']:.1f} m; "
                     "consumer GPS - not survey grade). Model is oriented north-up.")
        else:
            units = "Scale: RELATIVE (no drone telemetry). Distances in the model are not in metres."
        vex = mesh.get("vertical_exaggeration")
        readme = [
            "BIRD'S-EYE / AIRVEU3D delivery package", "=" * 40, "",
            "model_master.glb  - full-quality textured model (desktop viewers, Blender, QGIS 3D)",
            "model_lite.glb    - texture reduced to 2048 px for phones / web" + ("" if lite_ok else " (not produced)"),
            "orthomosaic.jpg   - top-down textured map (terrain surveys)" if (d / "orthomosaic.jpg").exists() else "",
            "georeference.json - scale, origin and orientation" if (d / "georeference.json").exists() else "",
            "capture_qa.json / output_qa.json - quality checks made before and after reconstruction", "",
            units,
        ]
        if vex and vex != 1:
            readme.append(f"Heights in the GLB are exaggerated {vex:g}x for visibility; divide by {vex:g} for true heights.")
        cq = job.get("capture_qa") or {}
        if cq.get("available"):
            readme.append(f"Capture QA: {cq['verdict']}. " + " ".join(cq.get("advice", [])))
        if qa.get("available"):
            readme.append(f"Output QA: {qa['verdict']}. " + " ".join(qa.get("issues", [])))
        readme += ["", "Limits: only surfaces seen by at least two frames exist in the model; unseen sides are NOT invented.",
                   "Not a certified survey product. Verify critical measurements on site."]
        (d / "README.txt").write_text("\n".join(x for x in readme if x is not None), encoding="utf-8")
        zpath = out / "birdseye_delivery.zip"
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for fp in sorted(d.iterdir()):
                z.write(fp, fp.name)
        res.update({"available": True, "output_qa": qa, "lite_glb": lite_ok, "zip": str(zpath),
                    "zip_mb": round(zpath.stat().st_size / 1e6, 1)})
        return res
