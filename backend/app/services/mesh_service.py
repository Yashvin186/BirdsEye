import subprocess
from app.core.presets import get_preset
from pathlib import Path
from typing import Dict, Any, Optional
import numpy as np
import trimesh
import plyfile
from scipy.spatial import cKDTree

from app.services.colmap_service import ColmapService


class MeshService:
    # Poisson surface reconstruction invents (extrapolates) surface wherever the input has no
    # points. These constants decide how aggressively that invented surface is removed.
    POISSON_DEPTH = None                  # None = choose from the point spacing (see _auto_depth)
    POISSON_CELL_SPACINGS = 1.5           # target Poisson cell size in multiples of the point spacing
    POISSON_MIN_DEPTH, POISSON_MAX_DEPTH = 7, 10
    MAX_FACES = 350_000                   # face budget: keeps OBJ/GLB exports and the browser viewer responsive
    FALLBACK_EXTENT_PAD = 0.25            # padding around the 1-99 percentile box when no sparse model exists
    BRIDGE_EDGE_FACTOR = 10.0             # edge longer than this x the 90th-percentile edge = bridge
    MAX_EDGE_SPACINGS = 12.0              # triangles with an edge longer than this many point spacings are bridges
    MIN_COMPONENT_FRACTION = 0.01         # islands smaller than 1% of the largest piece are noise
    SMOOTH_ITERATIONS = 10               # Taubin smoothing (volume preserving) to calm stereo noise
    POISSON_TRIM_DISTANCE_FACTOR = 6.0   # drop surface farther than N x median point spacing from any real point
    POISSON_TRIM_DENSITY_QUANTILE = 0.02  # additionally drop the weakest-supported 2% of vertices

    @staticmethod
    def _load_camera_centers(project_dir: Path) -> Optional[np.ndarray]:
        """Camera positions from the selected SfM model (written by ColmapService), if available."""
        cams_json = project_dir / "outputs" / "cameras.json"
        if not cams_json.exists():
            return None
        try:
            import json
            with open(cams_json, "r", encoding="utf-8") as f:
                cams = json.load(f)
            centers = np.array([c["position"] for c in cams], dtype=np.float64)
            return centers if centers.ndim == 2 and len(centers) > 0 else None
        except Exception:
            return None

    @classmethod
    def poisson_mesh_from_points(
        cls,
        points: np.ndarray,
        output_ply: Path,
        camera_centers: Optional[np.ndarray] = None,
        fill_unseen_regions: bool = False,
        depth: Optional[int] = None,
        max_faces: Optional[int] = None,
        max_depth: Optional[int] = None,
        log_callback=None
    ) -> Dict[str, Any]:
        """
        Screened-Poisson surface reconstruction (Open3D) from a point cloud.

        fill_unseen_regions=False (default): surface that is not supported by real observations
            (far from any point / very low Poisson density) is REMOVED, so regions the drone never
            saw stay empty instead of being faked.
        fill_unseen_regions=True: keep Poisson's closed surface. Unseen regions are then
            *extrapolated, not measured* - useful for a visually complete model, never for measurement.
        """
        try:
            import open3d as o3d
        except ImportError as e:
            raise RuntimeError(
                "Poisson fallback needs Open3D. Install it with: pip install open3d"
            ) from e

        pts = np.asarray(points, dtype=np.float64)
        pts = pts[np.all(np.isfinite(pts), axis=1)]
        if len(pts) < 500:
            raise ValueError(f"Too few points for Poisson surface reconstruction ({len(pts)} < 500).")

        # Typical spacing between neighbouring points (robust to outliers via median).
        tree = cKDTree(pts)
        sample = pts[np.random.default_rng(0).choice(len(pts), size=min(len(pts), 20000), replace=False)]
        nn_d, _ = tree.query(sample, k=2, workers=-1)
        spacing = float(np.median(nn_d[:, 1]))
        if not np.isfinite(spacing) or spacing <= 0:
            raise ValueError("Point cloud is degenerate (zero point spacing).")

        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(pts)
        pcd.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=spacing * 4.0, max_nn=40)
        )

        # Normals must point OUT of the surface, i.e. toward the side the camera saw it from.
        normals = np.asarray(pcd.normals).copy()
        if camera_centers is not None and len(camera_centers) > 0:
            _, nearest_cam = cKDTree(camera_centers).query(pts, workers=-1)
            to_cam = camera_centers[nearest_cam] - pts
            flip = np.einsum("ij,ij->i", normals, to_cam) < 0
            normals[flip] *= -1.0
            pcd.normals = o3d.utility.Vector3dVector(normals)
            orient_note = "oriented toward the drone cameras"
        else:
            pcd.orient_normals_consistent_tangent_plane(30)
            orient_note = "oriented by tangent-plane propagation (no camera poses available)"

        if depth or cls.POISSON_DEPTH:
            poisson_depth = int(depth or cls.POISSON_DEPTH)
        else:
            # A Poisson cell much smaller than the point spacing just reproduces noise (and makes
            # huge meshes); much larger smears real detail. Size the octree from the data instead.
            lo_p, hi_p = np.percentile(pts, [1, 99], axis=0)
            extent = float(np.max(hi_p - lo_p))
            poisson_depth = int(np.clip(
                round(np.log2(max(extent, 1e-9) / (cls.POISSON_CELL_SPACINGS * spacing))),
                cls.POISSON_MIN_DEPTH, int(max_depth or cls.POISSON_MAX_DEPTH)
            ))
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd, depth=poisson_depth)
        densities = np.asarray(densities)
        raw_faces = len(mesh.triangles)

        trimmed = False
        if not fill_unseen_regions and len(mesh.vertices) > 0:
            verts = np.asarray(mesh.vertices)
            dist_to_obs, _ = tree.query(verts, workers=-1)
            too_far = dist_to_obs > spacing * cls.POISSON_TRIM_DISTANCE_FACTOR
            low_support = densities < np.quantile(densities, cls.POISSON_TRIM_DENSITY_QUANTILE)
            mesh.remove_vertices_by_mask(too_far | low_support)
            trimmed = True

        mesh.remove_degenerate_triangles()
        mesh.remove_duplicated_triangles()
        mesh.remove_duplicated_vertices()
        mesh.remove_unreferenced_vertices()

        if len(mesh.triangles) == 0:
            raise ValueError("Poisson reconstruction produced no surface after trimming unsupported regions.")

        # Drop stretched triangles (bridges across gaps) and small floating islands.
        tris = np.asarray(mesh.triangles)
        v = np.asarray(mesh.vertices)
        e = np.stack([np.linalg.norm(v[tris[:, a]] - v[tris[:, b]], axis=1)
                      for a, b in ((0, 1), (1, 2), (2, 0))], axis=1).max(axis=1)
        mesh.remove_triangles_by_mask(e > spacing * cls.MAX_EDGE_SPACINGS)
        mesh.remove_unreferenced_vertices()
        if len(mesh.triangles) > 0:
            labels, counts, _ = mesh.cluster_connected_triangles()
            labels, counts = np.asarray(labels), np.asarray(counts)
            small = counts[labels] < max(50, counts.max() * cls.MIN_COMPONENT_FRACTION)
            mesh.remove_triangles_by_mask(small)
            mesh.remove_unreferenced_vertices()
        if len(mesh.triangles) == 0:
            raise ValueError("Poisson surface vanished after removing stretched/isolated triangles.")

        # Smooth stereo noise without shrinking, then cap the face count.
        if cls.SMOOTH_ITERATIONS > 0:
            mesh = mesh.filter_smooth_taubin(number_of_iterations=cls.SMOOTH_ITERATIONS)
        face_cap = int(max_faces or cls.MAX_FACES)
        if len(mesh.triangles) > face_cap:
            mesh = mesh.simplify_quadric_decimation(target_number_of_triangles=face_cap)
            mesh.remove_degenerate_triangles()
            mesh.remove_unreferenced_vertices()
        mesh.compute_vertex_normals()

        output_ply.parent.mkdir(parents=True, exist_ok=True)
        o3d.io.write_triangle_mesh(str(output_ply), mesh)

        if log_callback:
            log_callback(
                f"Poisson surface (depth {poisson_depth}, normals {orient_note}): {raw_faces:,} raw faces -> "
                f"{len(mesh.triangles):,} faces"
                + (" after removing surface with no supporting observations." if trimmed
                   else " (unseen regions closed by extrapolation - approximate, not measured).")
            )

        return {
            "faces": len(mesh.triangles),
            "raw_faces": raw_faces,
            "point_spacing": spacing,
            "trimmed_unsupported": trimmed,
        }

    @staticmethod
    def decimate(mesh, target_faces: int, log_callback=None):
        """Quadric decimation to the preset's face budget (keeps shape, drops redundant triangles)."""
        try:
            import open3d as o3d
            o = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(np.asarray(mesh.vertices)),
                                          o3d.utility.Vector3iVector(np.asarray(mesh.faces)))
            before = len(mesh.faces)
            o = o.simplify_quadric_decimation(target_number_of_triangles=int(target_faces))
            o.remove_degenerate_triangles(); o.remove_unreferenced_vertices()
            out = trimesh.Trimesh(np.asarray(o.vertices), np.asarray(o.triangles), process=False)
            if log_callback:
                log_callback(f"Mesh decimated {before:,} -> {len(out.faces):,} faces (quality-preset budget).")
            return out
        except Exception as exc:
            if log_callback:
                log_callback(f"[NOTICE] Decimation skipped: {exc}")
            return mesh

    @classmethod
    def clean_mesh_geometry(cls, mesh, model_dir, min_component_faces: int = 15, log_callback=None):
        """Remove far-field sheets, long bridging triangles and tiny islands from a trimesh mesh."""
        from app.services.subject_service import SubjectService
        start = len(mesh.faces)
        if start == 0:
            return mesh
        try:
            volume = SubjectService.build_trust_volume(SubjectService.read_sparse_points(Path(model_dir)),
                                                       margin=SubjectService.DEFAULT_MARGIN)
        except Exception:
            volume = None
        keep = np.ones(start, dtype=bool)
        if volume is None:
            # No usable sparse model: fall back to the mesh's own robust extent (1st-99th percentile
            # of its vertices, padded). Sky/far-terrain sheets lie far outside it.
            vv = np.asarray(mesh.vertices, dtype=np.float64)
            lo, hi = np.percentile(vv, [1, 99], axis=0)
            pad = (hi - lo) * cls.FALLBACK_EXTENT_PAD
            volume = {"mu": np.zeros(3), "axes": np.eye(3), "lo": lo - pad, "hi": hi + pad}
        if volume is not None:
            inside = SubjectService.inside(volume, np.asarray(mesh.vertices))
            far = ~inside[mesh.faces].all(axis=1)
            if (~far).sum() >= max(100, 0.02 * start):      # never crop the mesh down to nothing
                keep &= ~far
        v, f = np.asarray(mesh.vertices), np.asarray(mesh.faces)
        edge = np.max([np.linalg.norm(v[f[:, a]] - v[f[:, b]], axis=1) for a, b in ((0, 1), (1, 2), (2, 0))], axis=0)
        if keep.any():
            limit = cls.BRIDGE_EDGE_FACTOR * float(np.percentile(edge[keep], 90))
            keep &= edge <= limit
        if keep.sum() == 0:
            return mesh
        mesh = mesh.submesh([np.where(keep)[0]], append=True)
        comps = trimesh.graph.connected_components(mesh.face_adjacency, min_len=1)
        if len(comps) > 1:
            biggest = max(len(c) for c in comps)
            min_faces = max(min_component_faces, int(cls.MIN_COMPONENT_FRACTION * biggest))
            good = [i for c in comps if len(c) >= min_faces for i in c]
            if 0 < len(good) < len(mesh.faces):
                mesh = mesh.submesh([good], append=True)
        if log_callback:
            log_callback(f"Mesh cleanup: {start:,} -> {len(mesh.faces):,} faces "
                         f"(removed far-field sheets, stretched bridge triangles and floating islands).")
        return mesh

    @classmethod
    def generate_mesh_from_point_cloud(
        cls,
        project_dir: Path,
        primary_sparse_model: Optional[Path] = None,
        preferred_cloud_path: Optional[Path] = None,
        min_component_faces: int = 15,
        fill_unseen_regions: bool = False,
        quality_preset: str = "balanced",
        log_callback=None
    ) -> Dict[str, Any]:
        """
        Reconstructs a 3D surface mesh from photogrammetric outputs.
        Consumes the validated primary sparse model and preferred cloud path.
        Never uses convex hull as a scene reconstruction fallback.
        """
        preset = get_preset(quality_preset)
        outputs_dir = project_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        try:
            colmap_exe = ColmapService.get_colmap_executable()
        except RuntimeError:
            colmap_exe = None   # no COLMAP program: skip its Delaunay mesher and use Poisson
            if log_callback:
                log_callback("COLMAP program not installed: using the built-in Poisson mesher.")

        # 1. Determine primary sparse model directory
        if primary_sparse_model and Path(primary_sparse_model).exists():
            sparse_dir = Path(primary_sparse_model)
        else:
            sparse_root = project_dir / "colmap" / "sparse"
            submodels = [d for d in sparse_root.iterdir() if d.is_dir() and ((d / "cameras.txt").exists() or (d / "cameras.bin").exists())] if sparse_root.exists() else []
            sparse_dir = submodels[0] if submodels else (sparse_root / "0")

        # 2. Determine and validate source point cloud
        if preferred_cloud_path and Path(preferred_cloud_path).exists() and Path(preferred_cloud_path).stat().st_size > 0:
            source_cloud_path = Path(preferred_cloud_path)
            cloud_type = "dense_mvs" if "dense" in source_cloud_path.name.lower() else "sparse_sfm"
        elif (outputs_dir / "dense_cloud_filtered.ply").exists() and (outputs_dir / "dense_cloud_filtered.ply").stat().st_size > 0:
            source_cloud_path = outputs_dir / "dense_cloud_filtered.ply"
            cloud_type = "dense_mvs"
        elif (outputs_dir / "dense_cloud.ply").exists() and (outputs_dir / "dense_cloud.ply").stat().st_size > 0:
            source_cloud_path = outputs_dir / "dense_cloud.ply"
            cloud_type = "dense_mvs"
        else:
            source_cloud_path = outputs_dir / "sparse_cloud.ply"
            cloud_type = "sparse_sfm"

        if not source_cloud_path.exists() or source_cloud_path.stat().st_size == 0:
            err_msg = f"No valid point cloud found for meshing at {source_cloud_path}"
            if log_callback:
                log_callback(f"[ERROR] {err_msg}")
            return {
                "status": "failed",
                "reason": err_msg,
                "obj_path": None,
                "mtl_path": None,
                "glb_path": None,
                "raw_mesh_path": None,
                "cleaned_mesh_path": None,
                "mesh_ply_path": None,
                "vertex_count": 0,
                "face_count": 0,
                "dimensions": [],
                "bounds": [],
                "source_cloud_type": cloud_type,
                "texture_type": "none"
            }

        # Load reference point cloud for RGB vertex colors and bounds
        try:
            cloud_data = plyfile.PlyData.read(str(source_cloud_path))
            c_verts = cloud_data["vertex"]
            c_pts = np.vstack([c_verts["x"], c_verts["y"], c_verts["z"]]).T
            has_color = all(prop in c_verts.data.dtype.names for prop in ("red", "green", "blue"))
            if has_color:
                c_cols = np.vstack([c_verts["red"], c_verts["green"], c_verts["blue"]]).T
            else:
                c_cols = np.full((len(c_pts), 3), [160, 180, 160], dtype=np.uint8)
        except Exception as e:
            err_msg = f"Failed to parse source point cloud {source_cloud_path}: {e}"
            if log_callback:
                log_callback(f"[ERROR] {err_msg}")
            return {
                "status": "failed",
                "reason": err_msg,
                "obj_path": None,
                "mtl_path": None,
                "glb_path": None,
                "raw_mesh_path": None,
                "cleaned_mesh_path": None,
                "mesh_ply_path": None,
                "vertex_count": 0,
                "face_count": 0,
                "dimensions": [],
                "bounds": [],
                "source_cloud_type": cloud_type,
                "texture_type": "none"
            }

        raw_mesh_ply = outputs_dir / "raw_mesh.ply"
        cleaned_mesh_ply = outputs_dir / "cleaned_mesh.ply"
        model_mesh_ply = outputs_dir / "model_mesh.ply"
        model_obj = outputs_dir / "model.obj"
        model_mtl = outputs_dir / "model.mtl"
        model_glb = outputs_dir / "model.glb"

        mesh_generated = False
        mesh_method: Optional[str] = None
        poisson_info: Dict[str, Any] = {}

        dense_dir = project_dir / "colmap" / "dense"
        # 3. Surface Reconstruction: Attempt COLMAP 3D Delaunay graph-cut mesher
        # Prefer dense Delaunay meshing if dense workspace is available
        if colmap_exe and dense_dir.exists() and (dense_dir / "images").exists() and (dense_dir / "stereo").exists():
            try:
                if log_callback:
                    log_callback("Running COLMAP 3D Delaunay graph-cut mesher on dense workspace...")
                cmd = [
                    colmap_exe, "delaunay_mesher",
                    "--input_type", "dense",
                    "--input_path", str(dense_dir),
                    "--output_path", str(raw_mesh_ply),
                    "--DelaunayMeshing.max_proj_dist", "40",
                    "--DelaunayMeshing.max_side_length_percentile", "95"
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode == 0 and raw_mesh_ply.exists() and raw_mesh_ply.stat().st_size > 0:
                    mesh_generated = True
                    mesh_method = "colmap_delaunay_dense"
                    if log_callback:
                        log_callback(f"COLMAP dense 3D Delaunay surface mesh generated ({raw_mesh_ply.stat().st_size:,} bytes).")
                else:
                    err_msg = proc.stderr.strip() or proc.stdout.strip()
                    if log_callback:
                        log_callback(f"[NOTE] Dense delaunay_mesher output: {err_msg}")
            except Exception as e:
                if log_callback:
                    log_callback(f"[WARNING] COLMAP dense delaunay_mesher error: {e}")

        # Fall back to sparse Delaunay graph-cut mesher if dense mesher was not applicable or did not produce mesh
        if colmap_exe and not mesh_generated and sparse_dir.exists() and ((sparse_dir / "cameras.txt").exists() or (sparse_dir / "cameras.bin").exists()):
            try:
                if log_callback:
                    log_callback(f"Running COLMAP 3D Delaunay graph-cut visibility mesher on sparse model '{sparse_dir.name}'...")

                cmd = [
                    colmap_exe, "delaunay_mesher",
                    "--input_type", "sparse",
                    "--input_path", str(sparse_dir),
                    "--output_path", str(raw_mesh_ply),
                    "--DelaunayMeshing.max_proj_dist", "40",
                    "--DelaunayMeshing.max_side_length_percentile", "95"
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode == 0 and raw_mesh_ply.exists() and raw_mesh_ply.stat().st_size > 0:
                    mesh_generated = True
                    mesh_method = "colmap_delaunay_sparse"
                    if log_callback:
                        log_callback(f"COLMAP sparse 3D Delaunay surface mesh generated ({raw_mesh_ply.stat().st_size:,} bytes).")
                else:
                    err_msg = proc.stderr.strip() or proc.stdout.strip()
                    if log_callback:
                        log_callback(f"[NOTE] COLMAP sparse delaunay_mesher output: {err_msg}")
            except Exception as e:
                if log_callback:
                    log_callback(f"[WARNING] COLMAP sparse delaunay_mesher error: {e}")

        # 3b. Poisson fallback. COLMAP's Delaunay mesher frequently yields nothing on aerial footage
        # (it needs good visibility data), which is what produced "Faces: 0". Poisson works from any
        # oriented point cloud, including the fused MVS/AI cloud selected above. Unsupported
        # (never-observed) surface is trimmed unless fill_unseen_regions is requested.
        if not mesh_generated:
            try:
                if log_callback:
                    log_callback("COLMAP Delaunay mesher produced no mesh. Falling back to Poisson surface reconstruction on the point cloud...")
                poisson_info = cls.poisson_mesh_from_points(
                    points=c_pts,
                    output_ply=raw_mesh_ply,
                    camera_centers=cls._load_camera_centers(project_dir),
                    fill_unseen_regions=fill_unseen_regions,
                    max_faces=preset.mesh_faces,
                    max_depth=preset.poisson_max_depth,
                    log_callback=log_callback
                )
                mesh_generated = raw_mesh_ply.exists() and raw_mesh_ply.stat().st_size > 0
                if mesh_generated:
                    mesh_method = "poisson_extrapolated" if fill_unseen_regions else "poisson_trimmed"
            except Exception as e:
                if log_callback:
                    log_callback(f"[WARNING] Poisson fallback failed: {e}")

        # 4. Handle Meshing Failure without Fake Fallback
        if not mesh_generated or not raw_mesh_ply.exists():
            err_msg = "No surface could be recovered: COLMAP Delaunay meshing and the Poisson fallback both failed (see log above). Convex-hull fallback is disabled to prevent misleading geometry."
            if log_callback:
                log_callback(f"[NOTICE] {err_msg}")
                log_callback("Surface mesh generation marked failed. Valid point-cloud outputs are preserved.")
            return {
                "status": "failed",
                "reason": err_msg,
                "obj_path": None,
                "mtl_path": None,
                "glb_path": None,
                "raw_mesh_path": None,
                "cleaned_mesh_path": None,
                "mesh_ply_path": None,
                "vertex_count": 0,
                "face_count": 0,
                "dimensions": [],
                "bounds": [],
                "source_cloud_type": cloud_type,
                "texture_type": "none"
            }

        # 5. Load and Clean Reconstructed Mesh
        mesh = trimesh.load(str(raw_mesh_ply), process=False)
        if len(mesh.vertices) == 0 or len(mesh.faces) == 0:
            err_msg = "Reconstructed mesh contains 0 vertices or 0 faces."
            if log_callback:
                log_callback(f"[ERROR] {err_msg}")
            return {
                "status": "failed",
                "reason": err_msg,
                "obj_path": None,
                "mtl_path": None,
                "glb_path": None,
                "raw_mesh_path": None,
                "cleaned_mesh_path": None,
                "mesh_ply_path": None,
                "vertex_count": 0,
                "face_count": 0,
                "dimensions": [],
                "bounds": [],
                "source_cloud_type": cloud_type,
                "texture_type": "none"
            }

        # Clean degenerate faces and unreferenced vertices (compatible with Trimesh 3.x and 4.x)
        if hasattr(mesh, "remove_degenerate_faces"):
            mesh.remove_degenerate_faces()
        elif hasattr(mesh, "nondegenerate_faces"):
            mesh.update_faces(mesh.nondegenerate_faces())

        if hasattr(mesh, "remove_duplicate_faces"):
            mesh.remove_duplicate_faces()
        elif hasattr(mesh, "unique_faces"):
            mesh.update_faces(mesh.unique_faces())

        if hasattr(mesh, "remove_unreferenced_vertices"):
            mesh.remove_unreferenced_vertices()

        # Geometry sanity filters shared by every mesher (Delaunay and Poisson alike):
        # 1) far-field: drop faces outside the SfM-verified volume (sky / distant terrain sheets),
        # 2) bridges: drop triangles whose longest edge is far beyond the mesh's own edge scale,
        # 3) islands: drop components that are tiny relative to the main surface.
        mesh = cls.clean_mesh_geometry(mesh, sparse_dir, min_component_faces, log_callback)
        if len(mesh.faces) > preset.mesh_faces:
            mesh = cls.decimate(mesh, preset.mesh_faces, log_callback)

        # 6. Transfer RGB Colors from source cloud & compute normals
        if log_callback:
            log_callback("Transferring aerial RGB colors to mesh vertices and calculating surface normals...")

        mesh.fix_normals()
        c_tree = cKDTree(c_pts)
        _, indices = c_tree.query(mesh.vertices, k=1)
        v_cols = c_cols[indices]
        v_cols_rgba = np.column_stack([v_cols, np.full(len(v_cols), 255, dtype=np.uint8)])
        mesh.visual.vertex_colors = v_cols_rgba

        # 7. Export Deliverables
        mesh.export(str(cleaned_mesh_ply), file_type="ply")
        mesh.export(str(model_mesh_ply), file_type="ply")

        # Material definition: clearly labelled as vertex-color terrain material
        with open(model_mtl, "w", encoding="utf-8") as f:
            f.write("# Birds Eye Vertex-Colored Terrain Material\n")
            f.write("newmtl TerrainMaterial\n")
            f.write("Kd 0.85 0.85 0.85\n")
            f.write("Ka 0.20 0.20 0.20\n")
            f.write("Ks 0.05 0.05 0.05\n")
            f.write("d 1.0\n")
            f.write("illum 2\n")

        # Export OBJ with vertex colors and normals
        try:
            with open(model_obj, "w", encoding="utf-8") as f:
                f.write("# Birds Eye Reconstructed 3D Scene (Vertex-Colored Mesh)\n")
                f.write("mtllib model.mtl\nusemtl TerrainMaterial\n")
                for v, c in zip(mesh.vertices, v_cols):
                    cr, cg, cb = c[0] / 255.0, c[1] / 255.0, c[2] / 255.0
                    f.write(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f} {cr:.3f} {cg:.3f} {cb:.3f}\n")
                if hasattr(mesh, "vertex_normals") and len(mesh.vertex_normals) == len(mesh.vertices):
                    for vn in mesh.vertex_normals:
                        f.write(f"vn {vn[0]:.4f} {vn[1]:.4f} {vn[2]:.4f}\n")
                    for face in mesh.faces:
                        f.write(f"f {face[0]+1}//{face[0]+1} {face[1]+1}//{face[1]+1} {face[2]+1}//{face[2]+1}\n")
                else:
                    for face in mesh.faces:
                        f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")
        except Exception:
            mesh.export(str(model_obj), file_type="obj")

        # Export GLB (glTF binary)
        try:
            mesh.export(str(model_glb), file_type="glb")
        except Exception:
            pass

        vertex_count = len(mesh.vertices)
        face_count = len(mesh.faces)
        ext = mesh.extents.tolist()
        bounds = mesh.bounds.tolist()

        if log_callback:
            log_callback(f"Vertex-colored surface mesh finalized: {vertex_count:,} vertices, {face_count:,} faces ({ext[0]:.1f} × {ext[1]:.1f} × {ext[2]:.1f} relative units).")

        return {
            "status": "completed",
            "reason": None,
            "source_cloud": str(source_cloud_path),
            "source_cloud_type": cloud_type,
            "mesh_method": mesh_method,
            # "extrapolated" = surface exists where the video never looked (approximate, not measured)
            "unseen_regions": "extrapolated" if mesh_method == "poisson_extrapolated" else "left_empty",
            "texture_type": "vertex_color",
            "has_texture_atlas": False,
            "obj_path": str(model_obj),
            "mtl_path": str(model_mtl),
            "glb_path": str(model_glb) if model_glb.exists() else None,
            "raw_mesh_path": str(raw_mesh_ply) if raw_mesh_ply.exists() else None,
            "cleaned_mesh_path": str(cleaned_mesh_ply),
            "mesh_ply_path": str(model_mesh_ply),
            "vertex_count": vertex_count,
            "face_count": face_count,
            "dimensions": ext,
            "bounds": bounds
        }
