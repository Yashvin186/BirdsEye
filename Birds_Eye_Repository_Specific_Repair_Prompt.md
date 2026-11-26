# Birds Eye — Reconstruction Pipeline Repair Plan
## Repository-specific instructions for Antigravity

**Project:** Birds Eye — Single-Pass Drone Video to Accurate 3D Model Generation System  
**SIH problem statement:** 26158  
**Purpose:** Repair the existing implementation that currently produces fragmented or misleading 3D geometry. Preserve the current UI and project workflow.

---

# PART A — Prompt to give Antigravity

Read this file completely before editing. Work in the existing repository. Do not rebuild the app from scratch, redesign the UI first, or add an unrelated AI model.

The current source code already includes a FastAPI backend, a COLMAP SfM service, a dense reconstruction service, a mesh service, a job manager, and a Three.js viewer. Audit and repair those existing components.

## 1. First reproduce and diagnose

Inspect these files first:

- `backend/app/services/frame_service.py`
- `backend/app/services/colmap_service.py`
- `backend/app/services/dense_service.py`
- `backend/app/services/mesh_service.py`
- `backend/app/core/job_manager.py`
- `backend/app/services/report_service.py`
- `frontend/src/components/ModelViewer.tsx` (or the actual path in this repository)
- `backend/app/config.py` and `.env.example`

The uploaded source archive appears to contain the project files flattened at its root, while the README documents a `backend/` and `frontend/` structure. **Do not assume either layout. Inspect the actual checked-out repository and use the real paths.**

Before changing code:
1. Trace the current upload → frames → COLMAP database/matching → sparse model → dense reconstruction → mesh/export → viewer loading path.
2. Run or reproduce the issue with the actual input video if it is available.
3. Record the current job ID, settings, accepted frame count, COLMAP model directories, registered camera count, sparse point count, dense-stage outcome, mesh source, mesh component count, output paths, and subprocess logs.
4. Inspect `frame_manifest.json` and `contact_sheet.jpg`.
5. Inspect the sparse cloud, any true MVS cloud, the exported mesh, and the file the viewer actually loads.
6. State which failure is demonstrated by the evidence. Do not guess and do not claim that a fix worked until the pipeline has been rerun.

## 2. Critical defect: do not call synthetic interpolation a dense MVS result

In `dense_service.py`, inspect the CPU fallback after COLMAP patch-match stereo. It currently derives additional points from `outputs/sparse_cloud.ply` using a PCA projection, Delaunay triangulation, triangle centroids, and edge midpoints. That creates interpolated samples from a sparse cloud; it is **not** image-based Multi-View Stereo.

Change the behavior as follows:

- A dense result may be marked `completed` only when actual COLMAP dense stages succeed and a valid fused cloud is produced.
- Check the return code of `image_undistorter`; if it fails, stop that dense attempt and preserve its logs.
- Check the patch-match and stereo-fusion return codes and verify that the expected output files are present, non-empty, parseable, and contain a nonzero number of finite points.
- Never create `dense_cloud.ply` by relabeling, interpolating, upsampling, or recoloring `sparse_cloud.ply`.
- If this COLMAP build does not support the required dense operation, report `unsupported` or `failed` with a useful reason. Do not label the synthetic fallback as dense MVS.
- A CPU fallback is acceptable only if it is a genuine documented image-based depth/MVS implementation and is validated as such. Otherwise disable the dense stage with an explicit warning.
- Keep the sparse cloud as a separate output, clearly labelled **Sparse SfM Point Cloud**.

The current configured executable is named `COLMAP-3.9.1-windows-no-cuda`. Check its actual capabilities. Do not assume GPU PatchMatch is available. Do not claim CPU dense reconstruction unless the installed COLMAP version supports the required stages.

## 3. Critical defect: remove the convex-hull fallback for real terrain reconstruction

In `mesh_service.py`, inspect the fallback that calls `trimesh.convex.convex_hull(s_pts)` when COLMAP meshing fails.

A convex hull encloses the point set. It does not recover the actual visible surfaces of a temple, bridge, vegetation, or uneven terrain. It can bridge gaps and create broad, false surfaces.

Change the behavior as follows:

- Do not use a convex hull as the normal fallback for a reconstructed scene.
- If no suitable dense cloud is available or the chosen mesher fails, return a clear mesh failure and preserve the valid sparse/dense point-cloud outputs.
- If a fallback surface algorithm is retained, it must be explicitly labelled as an approximate visualization, never as a faithful reconstructed mesh. Do not mark the overall reconstruction as fully completed on that basis.
- Prefer a suitable surface reconstruction method for the available input, such as supported COLMAP Delaunay meshing on its valid workspace, or a documented point-cloud mesher. Choose based on the actual data and installed tool support, not by silently substituting a convex hull.
- Keep raw and cleaned meshes separate. Cleaning must not delete legitimate bridge/temple components simply to force a single connected component.
- Validate vertices, faces, normals, degenerate triangles, bounding box, and connected components before export.

## 4. Critical defect: choose the correct source cloud and sparse model

In `mesh_service.py`:

- `preferred_cloud_path` is currently accepted but the implementation reads `outputs/sparse_cloud.ply` directly. Implement the argument properly.
- Pass the selected primary sparse model directory from the SfM result into meshing rather than assuming `project_dir / "colmap" / "sparse" / "0"`.
- Ensure that the camera trajectory, image observations, sparse cloud, dense workspace, and mesh all refer to the **same selected COLMAP model**.
- Do not assume model index `0` is always the primary model. The SfM service chooses a model dynamically.
- If true dense MVS succeeded, prefer the true dense cloud for a suitable meshing method. If the selected mesher requires COLMAP's dense workspace or camera visibility information, pass those exact inputs. Do not pretend that a generic PLY cloud is interchangeable with every mesher's required workspace.
- If the dense cloud is missing or invalid, fail mesh generation with an explicit reason instead of quietly switching to the sparse cloud.
- Preserve filenames and output metadata so the frontend can distinguish sparse cloud, dense cloud, raw mesh, cleaned mesh, textured mesh, and any approximate preview.

## 5. Critical defect: make job status honest

In `job_manager.py`, inspect how stage statuses and the final job status are determined.

Current behavior can allow the job to finish as `completed` after the dense stage is skipped and a fallback mesh is generated. Replace this with explicit result states and rules:

- `completed`: the required stages for the chosen output profile succeeded and the required outputs passed validation.
- `partial`: sparse reconstruction succeeded, but optional dense/mesh/texture stages failed or were unsupported. Show which outputs are usable.
- `failed`: the required reconstruction stage failed, camera registration is unusable, or no valid required output exists.
- `cancelled`: cancellation was actually requested and handled.
- Never mark a stage completed merely because a function returned a dictionary. Check its status and outputs.
- A skipped optional stage must remain `skipped`; it must not be represented as successful.
- A valid sparse cloud can be a useful partial result, but it must not be presented as a complete textured 3D reconstruction.
- Do not use file existence alone as a quality test. Validate file format, geometry, nonzero finite points/vertices, and the output type.

Update the frontend to display `Partial` / `Needs Attention` when appropriate without replacing the current visual design. Do not show fabricated progress or success.

## 6. Validate the camera reconstruction before dense processing

In `colmap_service.py`:

- Count registered images from the actual selected COLMAP model and compare them to the accepted frame count.
- Report all reconstructed submodels and their camera/point counts.
- Do not select a primary model solely by the byte size of `points3D.bin`; file size is not a reliable substitute for reading model statistics. Select using validated registered-image and point counts, with a documented deterministic rule.
- Preserve other submodels for diagnosis. Do not silently merge unrelated models.
- Check `model_converter` return codes and verify exported PLY files are valid.
- Ensure image-name parsing follows the COLMAP text format and counts only registered image records.
- Report registration percentage and warn/fail when too few frames register to support a meaningful reconstruction. Use configurable thresholds with documented rationale rather than claiming a universal threshold.
- Store the exact selected sparse model path in the job output and pass it to every downstream stage.
- Preserve complete stdout/stderr logs for failed commands. Use subprocess timeouts/cancellation if feasible, without losing useful diagnostics.

## 7. Audit frame extraction rather than blindly changing its FPS

In `frame_service.py`:

- Review `sampling_fps`, `max_frames`, blur rejection, brightness rejection, and the near-duplicate test.
- Inspect the actual contact sheet and manifest for the test video before changing thresholds.
- Ensure accepted frames span the video and preserve useful viewpoint change and overlap. If many useful views are rejected, adjust the logic based on manifest evidence.
- The existing spatial image correlation test is not a camera-motion estimator. Do not use it as proof that two frames are geometrically redundant.
- Preserve original source timestamps and stable ordering.
- If the frame limit is reached, record that the remainder of the video was not evaluated.
- Keep thresholds configurable. Avoid blanket lowering of the blur threshold or increasing frame count without evidence; too many near-identical frames can also harm efficiency.
- Do not apply aggressive cropping, resizing, masking, or enhancement without comparing feature matching and reconstruction results.

## 8. Texture claims must be accurate

In `mesh_service.py`, the current code transfers nearest-neighbor vertex colors from the sparse cloud and writes a generic MTL file. This is not the same as baking a real multi-view texture atlas.

- If the output contains only vertex colors, label it **vertex-colored mesh**.
- Do not claim that texture baking or texture mapping succeeded unless actual texture images and UV/material references were generated and validated.
- For real texture baking, use a supported multi-view texture workflow that projects source images onto visible mesh surfaces.
- Validate that the viewer loads the associated material and texture images. Do not treat an OBJ with a generic material as a fully textured model.

## 9. Viewer must load the intended output and disclose its type

Inspect the model selection in `ModelViewer.tsx`. It currently prefers `model_mesh.ply` over `model.obj` and prefers `dense_cloud.ply` over `sparse_cloud.ply` for the point display.

- Verify that the selected mesh is a validated mesh from the current job, not a stale file from a prior run.
- Do not load a failed or approximate mesh under the same label as a valid reconstructed surface.
- Show the source type: sparse cloud, true dense MVS cloud, vertex-colored mesh, or textured mesh.
- Show warnings when the dense cloud or texture is unavailable.
- Verify coordinate axes, scale label, bounds, normals, and the viewer's actual file parsing. COLMAP reconstruction coordinates are generally relative unless external scale/georeferencing information is supplied; do not label relative extents as metres unless scale is known.
- Keep the current viewer controls and layout unless a minimal correction is required.

## 10. Quality checks and acceptance criteria

Add validation based on actual available outputs. At minimum record:

- Input video metadata and selected frame count.
- Registered camera count / selected frame count.
- Number of COLMAP sparse submodels.
- Sparse point count.
- Dense MVS status and point count, if genuine MVS ran.
- Mesh vertex/face counts and connected components.
- Number of non-finite vertices, degenerate faces, and invalid normals where computable.
- Bounding-box extents, explicitly marked as relative units unless scale is known.
- Whether actual texture images/UVs exist and load successfully.
- Stage durations, command return codes, warnings, and output paths.

Do not use point count, face count, or a successful viewer render as the only quality criteria. Do not claim accurate reconstruction without ground truth or known-distance/GCP validation.

## 11. Required implementation sequence

**Phase 1 — Audit and evidence**
- Reproduce current behavior.
- Identify which output file produced the screenshot's geometry.
- Report the earliest proven cause and relevant code locations.

**Phase 2 — Fix upstream correctness**
1. Correct selected COLMAP model and registration accounting.
2. Make dense MVS success/failure truthful.
3. Remove the convex-hull-as-reconstruction fallback.
4. Make meshing consume the correct validated source and model workspace.
5. Make job status and output metadata truthful.
6. Correct viewer selection and labels.

**Phase 3 — Run and compare**
- Delete or isolate stale outputs in a new job directory; do not delete the user's original input.
- Run the real uploaded video end-to-end.
- Inspect the contact sheet, sparse cloud, dense cloud if supported, and mesh.
- Compare measured metrics and screenshots before/after.
- If the environment cannot run dense MVS, report that limitation and deliver a correct sparse result rather than a fake dense model.

**Phase 4 — Deliver**
Return:
1. Root cause(s), with evidence.
2. Exact files changed.
3. Exact commands to run the application and reconstruction.
4. Actual before/after measurements.
5. Which output is a real SfM cloud, real MVS cloud, approximate preview, vertex-colored mesh, or textured mesh.
6. Any remaining hardware/software limitations.

Do not finish by only describing a plan. Implement the smallest safe changes, run tests, and report honestly what could and could not be verified.

---

# PART B — Known code issues to verify in the current repository

These are directly visible in the supplied source snapshot. Verify that the current working tree still matches it before editing.

| File | Observed behavior | Required correction |
|---|---|---|
| `dense_service.py` | CPU fallback adds centroids/midpoints to a PCA/Delaunay triangulation of the sparse SfM cloud and returns it as `dense_cloud.ply`. | Do not report this as dense MVS. Only mark genuine image-based dense reconstruction complete after successful COLMAP stages and output validation. |
| `mesh_service.py` | Falls back to `trimesh.convex.convex_hull(s_pts)`. | Do not use convex hull as a faithful scene reconstruction. Report mesh failure or clearly label an approximate preview. |
| `mesh_service.py` | Accepts `preferred_cloud_path` but reads `outputs/sparse_cloud.ply` unconditionally. | Honor the selected source cloud and validate it. |
| `mesh_service.py` | Hardcodes `colmap/sparse/0` for camera data. | Pass the exact primary sparse model selected by SfM. |
| `colmap_service.py` | Chooses a primary submodel based on the file size of `points3D.bin` / `points3D.txt`. | Use validated model statistics and a deterministic documented rule. |
| `job_manager.py` | Mesh stage can be marked completed after a fallback; overall job can become completed even if dense MVS was skipped. | Distinguish complete, partial, failed, skipped, and unsupported stages based on actual outputs. |
| `mesh_service.py` | Transfers nearest sparse vertex colors and writes a generic MTL. | Call this vertex coloring, not real multi-view texture baking. |
| `ModelViewer.tsx` | Prefers `model_mesh.ply` for mesh display and `dense_cloud.ply` for point display. | Ensure files are from the current job and metadata accurately states whether they are true dense outputs. |
| `config.py` | Contains machine-specific absolute Windows paths. | Confirm they match the current machine; prefer environment-configurable paths with clear diagnostics. |

---

# PART C — Practical technical boundary

A single video pass can be sufficient for a useful reconstruction only when it provides adequate overlap, parallax, sharp imagery, and stable visual features. Moving water, reflections, distant sky, vegetation, thin cables, and occluded surfaces can remain incomplete.

The application must not promise that every surface is recoverable. It should produce the best defensible reconstruction supported by the footage, show missing/uncertain regions honestly, and distinguish relative model coordinates from georeferenced measurements.

**First action:** inspect the actual code and job logs, identify why the displayed mesh was created from the selected point cloud, and fix that cause before changing the UI or adding features.
