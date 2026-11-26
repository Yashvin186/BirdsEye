# Single-Pass Drone Video to Accurate 3D Model Generation System

## Implementation Specification for Antigravity AI

**Project name:** Birds Eye --- Single-Pass Drone 3D Reconstruction\
**Document type:** Product and engineering specification\
**Version:** 1.0\
**Primary goal:** Build a working software pipeline that accepts one
continuous drone video and produces a reconstructed, textured, viewable,
and exportable 3D model of the captured terrain or site.

------------------------------------------------------------------------

## 1. Instructions to Antigravity AI

Build a functional, end-to-end application from this specification. Do
not build only a mock UI, static demo, or hard-coded visualization.
Implement the video-processing pipeline, reconstruction commands,
progress tracking, result validation, 3D viewer, and export workflow.

Before coding:

1.  Inspect the existing repository and preserve any useful code.
2.  Identify the operating system, installed Python version, GPU
    availability, and whether COLMAP is installed.
3.  Propose a short implementation plan and then implement in small,
    testable stages.
4.  Create a `README.md`, `.env.example`, dependency files, and clear
    setup instructions.
5.  Do not invent reconstruction results or display sample output as if
    it came from the uploaded video.
6.  If an optional tool or model is unavailable, show a clear setup
    message and keep the rest of the application usable.
7.  Do not silently replace a failed reconstruction stage with
    fabricated geometry.
8.  Keep expensive processing on the backend. The frontend should submit
    jobs and display progress/results.
9.  Use real subprocess exit codes, output-file checks, and logs to
    decide whether a stage succeeded.
10. Implement a small sample/test mode only if it is clearly labelled as
    a demo and separated from real reconstruction.

The first deliverable is a working MVP that can process a suitable video
on a local machine. Do not promise survey-grade accuracy from video
alone.

------------------------------------------------------------------------

## 2. Product Overview

### 2.1 Problem statement

Traditional photogrammetry often relies on several overlapping flight
passes and images captured from multiple viewpoints. A single continuous
drone video may contain redundant frames, motion blur, changing
exposure, weak parallax, and insufficient views of some surfaces. These
factors can cause camera-pose errors, incomplete geometry, scale
ambiguity, and distortion.

This application must extract useful frames, estimate camera motion,
reconstruct sparse and dense scene geometry, generate a textured mesh
where supported, optionally align the result to geographic coordinates,
and provide a 3D viewer with quality information and export options.

### 2.2 Target workflow

**Drone video → frame extraction and preprocessing → feature detection
and matching → Structure-from-Motion (SfM) → Multi-View Stereo (MVS) /
depth estimation → dense point cloud → mesh generation and texturing →
scale/georeferencing and evaluation → interactive viewer and export.**

### 2.3 Expected outputs

-   Extracted keyframes and a processing report.
-   Estimated camera poses and sparse point cloud.
-   Dense point cloud when dense reconstruction succeeds.
-   Surface mesh and texture when mesh reconstruction succeeds.
-   Georeferenced model when usable GPS/GCP/reference data are supplied.
-   Interactive 3D preview with orbit, pan, zoom, and quality
    information.
-   Exportable files such as PLY, OBJ + MTL + texture images, and GLB
    where conversion is supported.
-   Logs, stage status, warnings, and a final reconstruction summary.

The application must clearly distinguish **completed outputs**,
**optional outputs**, and **stages that failed or were skipped**.

------------------------------------------------------------------------

## 3. Scope and Technical Boundaries

### 3.1 MVP must include

1.  Upload/select a single continuous drone video.
2.  Validate the file and inspect video metadata.
3.  Extract and filter frames.
4.  Correct lens distortion when camera calibration is available;
    otherwise record that calibration is unknown.
5.  Detect and match visual features between frames.
6.  Run COLMAP Structure-from-Motion.
7.  Run dense reconstruction using COLMAP Multi-View Stereo when
    supported by the input and environment.
8.  Generate a point cloud and a surface mesh where possible.
9.  Apply texture where supported by the selected meshing tool.
10. Estimate scale and georeference the result only when adequate
    reference information is available.
11. Display a 3D model in the browser.
12. Provide export, download, progress, logs, and a quality report.

### 3.2 Optional / advanced features

-   Learned per-frame depth estimation as an auxiliary or fallback
    visualization path.
-   Ground Control Point (GCP) alignment.
-   GPS/RTK camera priors.
-   Orthomosaic generation.
-   Multi-GPU processing.
-   Advanced mesh cleanup, decimation, and texture baking.
-   Batch processing of multiple projects.

Do not make optional features mandatory for the first working build.

### 3.3 Accuracy disclaimer

A single-pass video does not guarantee complete terrain coverage or
metrically accurate dimensions. Absolute scale and geographic position
are generally ambiguous without reliable GPS/RTK, known camera
parameters, known distances, surveyed GCPs, or other reference data.
Monocular depth models can provide useful relative depth but should not
be treated as survey-grade measurements by default.

The UI must report the available reference data and the resulting
confidence/limitations. Never label a model "accurate" solely because a
mesh was generated.

------------------------------------------------------------------------

## 4. Recommended Technology Stack

Use a local-first architecture so the user can run expensive
reconstruction tasks on their own machine.

### Frontend

-   React + TypeScript.
-   Vite for development/build.
-   Tailwind CSS for responsive styling.
-   Lucide React for icons.
-   Three.js, preferably through React Three Fiber or a clearly
    structured Three.js viewer, for interactive 3D display.
-   A lightweight chart/progress component for stage status and quality
    metrics.

### Backend

-   Python 3.11 or another version verified compatible with the selected
    dependencies.
-   FastAPI for REST endpoints.
-   Uvicorn as the development server.
-   OpenCV for video metadata, frame extraction, image filtering, and
    preprocessing.
-   COLMAP CLI for feature extraction, matching, sparse reconstruction,
    and dense reconstruction.
-   Open3D for point-cloud inspection and supported geometry processing.
-   A mesh tool compatible with the environment (for example, Open3D for
    supported operations and/or PyMeshLab/another maintained meshing
    tool) for surface generation and cleanup.
-   Pillow for image handling where required.
-   Optional PyTorch + a compatible pretrained depth model for
    supplemental depth estimation.
-   Pydantic for request/response validation.

### Storage and job handling

-   Local filesystem for uploaded video, intermediate data, outputs, and
    logs.
-   SQLite or a small JSON-backed job store for MVP job metadata; use
    SQLite if reliable job history is needed.
-   Background worker/process management so long-running COLMAP commands
    do not block API requests.
-   Do not require a cloud database for the MVP.

### External system requirements

-   COLMAP must be installed separately where not available through a
    compatible package.
-   Dense reconstruction may require CUDA/GPU support depending on
    COLMAP build and settings. Detect capabilities and provide
    actionable errors.
-   FFmpeg may be used for video inspection/transcoding if available,
    but provide a clear dependency check.
-   Do not download large model weights automatically without informing
    the user and documenting the download.

Pin compatible dependency versions in the lock/dependency file after
testing. Do not assume all packages work with every Python version or
GPU driver.

------------------------------------------------------------------------

## 5. High-Level Architecture

``` text
┌──────────────────────────────┐
│ React Web Application        │
│ Upload • Jobs • Viewer       │
│ Quality Report • Downloads   │
└──────────────┬───────────────┘
               │ REST API
┌──────────────▼───────────────┐
│ FastAPI Backend              │
│ Validation • Job Manager     │
│ Progress • Logs • File APIs  │
└──────────────┬───────────────┘
               │
┌──────────────▼─────────────────────────────────────────────┐
│ Reconstruction Worker                                      │
│ 1. Video inspection                                        │
│ 2. Frame extraction & preprocessing                        │
│ 3. Feature detection & matching                            │
│ 4. Structure-from-Motion (COLMAP)                           │
│ 5. MVS / depth estimation                                  │
│ 6. Dense point cloud                                       │
│ 7. Mesh generation & texturing                             │
│ 8. Scale/georeferencing & evaluation                       │
│ 9. Output validation                                       │
└──────────────┬─────────────────────────────────────────────┘
               │
┌──────────────▼───────────────┐
│ Project Workspace            │
│ Input • Frames • COLMAP DB   │
│ Sparse • Dense • Mesh        │
│ Textures • Logs • Report     │
└──────────────────────────────┘
```

### Processing job lifecycle

Use explicit states:

`queued → validating → extracting_frames → preprocessing → feature_matching → sfm → dense_reconstruction → meshing_texturing → georeferencing_evaluation → packaging → completed`

A job may enter `failed` from any stage. Optional stages may be marked
`skipped` with a reason. Do not mark a job completed if required outputs
are missing or corrupt.

For each stage store: - Stage name and status. - Start/end timestamps
and duration. - Progress percentage if available. - Relevant log
excerpt. - Output files created. - Warnings and failure reason.

Progress must reflect actual work where possible. Do not simulate a
progress bar that advances regardless of processing.

------------------------------------------------------------------------

## 6. End-to-End Reconstruction Pipeline

### Stage 0 --- Project creation and video validation

**Input:** One drone video file.

**Tasks:** 1. Accept common formats such as MP4 and MOV; support
additional formats only when the installed decoder supports them. 2.
Enforce configurable upload size and duration limits. 3. Reject empty,
corrupted, unsupported, or unreadable files with a clear error. 4. Read
duration, frame rate, frame count if available, resolution, codec, and
orientation. 5. Extract available metadata such as GPS coordinates,
timestamps, and camera information when present. Metadata extraction
must be best-effort and report missing fields. 6. Create a unique
project ID and a safe project workspace. 7. Store the original file name
as metadata, but use safe generated names for filesystem paths. 8. Ask
the user for optional camera information: camera model, focal length,
sensor details, known calibration, and approximate flight height if
known. 9. Allow optional GPS/RTK log, GCP coordinates, or known-distance
references to be supplied separately. 10. Display a preflight checklist
and warn about low resolution, very short duration, very low frame rate,
or likely weak overlap. These warnings should not claim certainty before
inspection.

**Output:** Project metadata and a validated video file.

### Stage 1 --- Frame extraction and preprocessing

**Poster stage:** "Frame Extraction & Preprocessing --- Sampling,
quality checks, distortion correction."

**Tasks:** 1. Use OpenCV or FFmpeg to decode the video. 2. Extract
candidate frames using configurable time intervals or frame sampling. 3.
Avoid extracting every frame by default; adjacent video frames can be
nearly identical and increase processing time. 4. Support configurable
settings such as: - Sampling interval / target frames per second. -
Maximum number of candidate frames. - Minimum image width/height. -
Optional resizing for memory constraints. 5. Compute a blur/sharpness
score, for example variance of the Laplacian. 6. Detect near-duplicate
frames using image similarity or perceptual hashing. 7. Filter
unreadable, excessively blurred, very dark, overexposed, or
near-duplicate frames with documented thresholds. 8. Preserve the source
timestamp/frame index for every accepted frame. 9. If camera calibration
parameters are available, apply lens-distortion correction. If they are
unknown, do not invent calibration values; optionally estimate them
during SfM and mark the calibration source. 10. Save the accepted frames
and a CSV/JSON manifest with timestamps, quality scores, dimensions, and
filtering decisions. 11. Create a contact sheet of accepted frames for
visual inspection.

**Output:** Clean, ordered image set and frame manifest.

**Important:** Frame filtering must not remove so many images that
camera tracking becomes impossible. Provide user-adjustable settings and
report how many frames were kept/rejected.

### Stage 2 --- Feature detection and matching

**Poster stage:** "Feature Detection & Matching --- Identify common
visual frames across frames."

**Tasks:** 1. Use COLMAP feature extraction and matching as the primary
classical photogrammetry route. 2. Use a consistent camera model and
sensible default feature settings; expose advanced settings only in an
optional panel. 3. Match features across temporally nearby frames and
appropriate additional pairs. 4. For a continuous video, begin with
sequential matching where suitable; allow loop/overlap or exhaustive
matching as an advanced alternative for appropriate datasets. 5. Store
the COLMAP database and logs in the project workspace. 6. Record key
metrics when available: number of images registered, keypoints, matches,
verified geometric matches, and disconnected components. 7. Flag low
feature counts, repeated textures, low parallax, poor image overlap, and
excessive blur where detectable. 8. If matching fails, stop dependent
stages and present the actionable error and log location.

**Output:** COLMAP database and match statistics.

### Stage 3 --- Structure-from-Motion (SfM)

**Poster stage:** "Estimate camera poses and sparse 3D points."

**Tasks:** 1. Run COLMAP mapper/incremental SfM using the feature
database and extracted frames. 2. Estimate camera intrinsics/extrinsics
and sparse 3D scene points. 3. Save the sparse reconstruction in COLMAP
format. 4. Export a sparse point cloud (PLY) and camera/registration
summary where supported. 5. Record: - Number of input frames. - Number
and percentage of registered images. - Sparse 3D point count. -
Reprojection error if available. - Camera model and calibration status.
6. If several reconstructions/components are created, identify the best
candidate using documented criteria such as registered image count and
reconstruction quality. Do not silently merge disconnected components.
7. If SfM fails or registers too few frames, do not proceed as if a
valid model exists. Show troubleshooting guidance for overlap, texture,
blur, exposure, and camera settings.

**Output:** Sparse point cloud, camera poses, and SfM report.

### Stage 4 --- Multi-View Stereo (MVS) and depth generation

**Poster stage:** "Estimate depth and fuse dense geometry."

**Tasks:** 1. Run COLMAP image undistortion for the selected sparse
model. 2. Run dense stereo/depth-map estimation using COLMAP patch-match
stereo when supported by the installed build and hardware. 3. Fuse depth
maps into a dense point cloud. 4. Save depth maps and intermediate files
when practical, but allow a storage-saving configuration. 5. If COLMAP
MVS is unavailable or fails due to hardware/build constraints, report
this clearly. 6. Optional: run a learned depth model per frame as a
supplementary depth preview or experimental fallback. Keep learned depth
outputs separate from photogrammetric MVS results. Do not represent a
monocular depth estimate as a calibrated dense reconstruction. 7. Record
dense point count, depth-stage status, runtime, and memory/GPU errors
where available.

**Output:** Dense point cloud when successful; optional depth maps and
clearly labelled auxiliary estimates.

### Stage 5 --- Mesh generation and texturing

**Poster stage:** "Create a surface and apply image textures."

**Tasks:** 1. Use the dense point cloud as the primary input to surface
reconstruction. 2. Estimate and document point-cloud normals if required
by the chosen meshing algorithm. 3. Generate a mesh using a method
compatible with the data, such as Poisson reconstruction or
ball-pivoting when its assumptions are satisfied. 4. Provide a
configurable cleanup step for isolated components, outliers, and
non-finite vertices. 5. Avoid aggressive smoothing that erases terrain
features. 6. Generate or bake a texture from the source images using a
supported texturing tool/workflow. If a reliable texture cannot be
generated, still provide an untextured mesh and explain why. 7. Keep raw
and processed outputs separate. 8. Save mesh statistics: vertices,
faces, connected components, bounding box, and texture status. 9.
Generate a lightweight preview model for browser rendering if the
original model is too large. 10. Do not fabricate a mesh when dense
geometry is absent. If only a sparse cloud exists, show that result as a
point-cloud preview and mark meshing as unavailable.

**Output:** Cleaned mesh and texture assets where successful.

### Stage 6 --- Scale, georeferencing, and evaluation

**Poster stage:** "Use available reference support(s), if any."

**Tasks:** 1. Inspect available EXIF/video metadata and optional GPS/RTK
data. 2. If sufficient camera GPS priors, GCPs, surveyed coordinates, or
known-distance references are provided, use an appropriate, documented
alignment/scaling method. 3. Support an optional GCP input format with
point identifiers and known coordinates; validate coordinate systems and
units. 4. Where applicable, transform model coordinates to the declared
coordinate reference system using a well-defined geospatial
library/tool. Record the CRS and transformation. 5. If there are no
reliable external references, label the model as having **unknown
absolute scale/georeferencing**. Relative shape may still be useful. 6.
Evaluate using available metrics: - Registered image percentage. -
Reprojection error where available. - Sparse/dense point counts. - Mesh
statistics. - Coverage/completeness indicators that can be computed. -
Alignment residuals when GCP/reference points are available. 7. If
ground-truth geometry exists, compute suitable comparison metrics such
as point-to-reference distances or RMSE. If no ground truth exists, do
not invent accuracy/RMSE values. 8. Produce a quality report with
limitations and recommended next steps.

**Output:** Scaled/georeferenced model only when justified by inputs,
plus evaluation report.

### Stage 7 --- Interactive 3D viewer and export

**Poster stage:** "Inspect, measure (where supported), export model."

**Viewer requirements:** 1. Load the generated point cloud or mesh in a
browser-based Three.js viewer. 2. Support orbit, pan, zoom, reset
camera, fit-to-model, and toggle axes/grid. 3. Show a loading indicator
and handle large-file failures gracefully. 4. Provide display modes when
available: textured mesh, solid mesh, wireframe, and point cloud. 5.
Show model metadata: dimensions/units if known, point/vertex/face
counts, reconstruction status, and georeferencing status. 6. Add simple
measurement tools only when a coordinate scale is known. If scale is
unknown, label measurements as relative model units. 7. Provide a file
list with download links for completed outputs. 8. Allow export to: -
PLY for point clouds. - OBJ + MTL + texture files for textured meshes. -
GLB when a valid conversion path is available. - Original COLMAP sparse
model and selected processing reports for reproducibility. 9. Preserve
textures and material references in exports. Validate that each
downloadable file exists and is non-empty. 10. Add a clear warning that
model measurements are not survey-grade unless the reconstruction has
been appropriately calibrated and independently validated.

**Output:** Interactive viewer, downloadable model files, and summary
report.

------------------------------------------------------------------------

## 7. System Design: Three Layers

### Layer 1 --- Input and preprocessing

Components: - Drone video upload/selection. - Video metadata
inspection. - Video stabilization only if implemented as a controlled
optional step; avoid changing geometry in a way that harms
photogrammetry. - Lens distortion correction using known calibration or
COLMAP camera estimation. - Frame extraction. - Quality filtering and
near-duplicate detection.

Data passed to Layer 2: - Accepted frame directory. - Frame manifest. -
Camera/calibration metadata. - Project configuration.

### Layer 2 --- Reconstruction engine

Components: - Feature matching. - Structure-from-Motion (SfM). -
Optional learned per-frame depth generation. - Multi-View Stereo
(MVS). - Dense reconstruction / point-cloud fusion. - Mesh generation. -
Geospatial alignment where supported.

Data passed to Layer 3: - Sparse and dense point clouds. - Mesh and
texture files. - Camera poses. - Reconstruction metrics. - Warnings and
processing logs.

### Layer 3 --- Output and visualization

Components: - 3D model optimization for browser performance. -
Interactive 3D viewer. - Measurement tools with scale-aware labels. -
Export and integration. - Final quality report and downloadable logs.

------------------------------------------------------------------------

## 8. User Interface Requirements

Create a clean, modern, responsive interface branded **Birds Eye**. Use
navy, white, and cyan/blue accents inspired by the project poster. Keep
the UI readable and avoid overloading the screen with advanced
photogrammetry parameters.

### Screen A --- Home / Projects

-   Project title and short explanation.
-   Create new reconstruction button.
-   Recent projects with creation date, source video, status, and output
    availability.
-   System readiness panel showing Python/backend status, COLMAP
    availability, GPU/CUDA status where detectable, and disk-space
    warning if feasible.

### Screen B --- New Project / Upload

-   Drag-and-drop video upload and browse button.
-   File size/type validation.
-   Video metadata preview.
-   Optional camera, GPS, GCP, and known-distance inputs.
-   Frame sampling controls with safe defaults.
-   Start reconstruction button disabled until required validation
    passes.

### Screen C --- Processing

-   Ordered pipeline stepper showing all stages.
-   Current stage, elapsed time, progress when available, warnings, and
    log preview.
-   Cancel job option with safe process termination.
-   Failed stage view with retry guidance.
-   Do not show fake percentage progress for a command that provides no
    meaningful progress. In that case show "Running" and stage elapsed
    time.

### Screen D --- Results

-   Embedded 3D viewer.
-   Tabs/panels for model, sparse cloud, dense cloud, camera poses, and
    report where available.
-   Quality summary: registered frames, point counts, reprojection error
    when available, mesh counts, georeferencing status.
-   Export/download panel.
-   Warnings and limitations visible without hiding them in logs.

### Screen E --- Project Details / Logs

-   Input metadata and processing configuration.
-   Per-stage timestamps and statuses.
-   Download logs and report.
-   Output files list with size and format.
-   Delete project action with confirmation.

### Responsive behavior

-   Usable on desktop and tablet; support narrow screens without
    horizontal overflow.
-   On mobile, simplify the viewer controls and stack panels vertically.
-   Provide accessible labels, keyboard focus, loading/error states, and
    clear empty states.

------------------------------------------------------------------------

## 9. Backend API Contract

Implement REST endpoints with validated schemas. Exact response shapes
can be refined during coding, but maintain the following behavior.

### `GET /api/health`

Returns backend status and detected dependencies, including COLMAP
availability and optional GPU status.

### `GET /api/capabilities`

Returns available processing features and limitations based on installed
tools.

### `POST /api/projects`

Creates project metadata and returns a unique project ID.

### `POST /api/projects/{project_id}/video`

Uploads the video, validates it, and returns file metadata.

### `POST /api/projects/{project_id}/reconstruction`

Validates the configuration, queues a reconstruction job, and returns a
job ID.

### `GET /api/jobs/{job_id}`

Returns overall status, current stage, stage progress if known,
timestamps, warnings, and failure details.

### `GET /api/jobs/{job_id}/events`

Provides job updates using Server-Sent Events (SSE) or another simple,
documented streaming approach. Polling can be used as a fallback.

### `POST /api/jobs/{job_id}/cancel`

Requests safe cancellation of a running job and cleans up child
processes without deleting completed outputs unexpectedly.

### `GET /api/projects/{project_id}/results`

Returns available outputs, file metadata, quality report, and
georeferencing status.

### `GET /api/projects/{project_id}/files/{file_id}`

Serves a validated output file for preview/download. Prevent path
traversal and only expose files within the project output directory.

### `GET /api/projects`

Lists recent projects.

### `DELETE /api/projects/{project_id}`

Deletes a project only after confirmation and validates that the
resolved path remains within the configured workspace.

Use appropriate HTTP status codes and consistent JSON errors, for
example:

``` json
{
  "error": {
    "code": "COLMAP_NOT_FOUND",
    "message": "COLMAP is not installed or is not available on PATH.",
    "details": "Install a compatible COLMAP build and restart the backend."
  }
}
```

Never return arbitrary filesystem paths or secrets to the browser.

------------------------------------------------------------------------

## 10. Suggested Project Structure

``` text
birds-eye-3d/
├── README.md
├── SPEC.md
├── .env.example
├── .gitignore
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── app/
│       ├── components/
│       │   ├── VideoUploader.tsx
│       │   ├── PipelineStepper.tsx
│       │   ├── JobProgress.tsx
│       │   ├── QualityReport.tsx
│       │   ├── ModelViewer.tsx
│       │   └── ExportPanel.tsx
│       ├── pages/
│       │   ├── ProjectsPage.tsx
│       │   ├── NewProjectPage.tsx
│       │   ├── ProcessingPage.tsx
│       │   └── ResultsPage.tsx
│       ├── services/api.ts
│       └── types/
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── schemas.py
│       ├── api/
│       │   ├── health.py
│       │   ├── projects.py
│       │   ├── jobs.py
│       │   └── files.py
│       ├── services/
│       │   ├── video_inspection.py
│       │   ├── frame_extraction.py
│       │   ├── frame_quality.py
│       │   ├── camera_calibration.py
│       │   ├── colmap_runner.py
│       │   ├── dense_reconstruction.py
│       │   ├── meshing.py
│       │   ├── georeferencing.py
│       │   ├── evaluation.py
│       │   ├── export.py
│       │   └── report.py
│       ├── workers/
│       │   ├── job_manager.py
│       │   └── reconstruction_worker.py
│       └── tests/
├── workspace/
│   └── .gitkeep
└── docs/
    ├── pipeline.md
    └── troubleshooting.md
```

The workspace should be configurable outside source control. Do not
commit videos, dense point clouds, texture files, model weights, or
large intermediate outputs.

------------------------------------------------------------------------

## 11. Project Workspace and Output Layout

Each project should have an isolated directory:

``` text
workspace/<project_id>/
├── input/
│   └── source_video.mp4
├── frames/
│   ├── frame_000001.jpg
│   ├── frame_000002.jpg
│   ├── frame_manifest.csv
│   └── contact_sheet.jpg
├── colmap/
│   ├── database.db
│   ├── sparse/
│   └── dense/
├── outputs/
│   ├── sparse_cloud.ply
│   ├── dense_cloud.ply
│   ├── model_mesh.ply
│   ├── model.obj
│   ├── model.mtl
│   ├── textures/
│   ├── model.glb
│   ├── cameras.json
│   ├── quality_report.json
│   └── quality_report.md
└── logs/
    ├── pipeline.log
    └── stage_logs/
```

Only files that were actually produced should appear as available
outputs. Optional formats may be absent. The UI must not create fake
links for missing files.

------------------------------------------------------------------------

## 12. Configuration

Provide a validated configuration object/file for values such as:

-   Workspace path.
-   Maximum upload size and maximum video duration.
-   Frame sampling interval or target rate.
-   Maximum candidate frames.
-   Minimum accepted image resolution.
-   Blur and duplicate filtering thresholds.
-   COLMAP executable path.
-   Matching strategy.
-   Dense reconstruction enabled/disabled.
-   CPU/GPU settings supported by the installed build.
-   Mesh reconstruction method and cleanup options.
-   Optional depth-model selection.
-   Optional GCP file and coordinate reference system.
-   Retention/cleanup policy for temporary files.

Choose conservative defaults and document their trade-offs. Validate all
user-supplied paths and numeric settings. Avoid hard-coded absolute
paths.

------------------------------------------------------------------------

## 13. Quality Report Schema

Generate `quality_report.json` and a readable `quality_report.md`.
Include at least:

``` json
{
  "project_id": "generated-project-id",
  "status": "completed",
  "input": {
    "filename": "source_video.mp4",
    "duration_seconds": null,
    "fps": null,
    "width": null,
    "height": null
  },
  "frames": {
    "candidate_count": null,
    "accepted_count": null,
    "rejected_count": null
  },
  "sfm": {
    "registered_images": null,
    "registration_percentage": null,
    "sparse_point_count": null,
    "reprojection_error": null
  },
  "dense_reconstruction": {
    "status": "not_run",
    "point_count": null
  },
  "mesh": {
    "status": "not_run",
    "vertex_count": null,
    "face_count": null,
    "textured": false
  },
  "georeferencing": {
    "status": "unknown",
    "crs": null,
    "reference_source": null,
    "alignment_rmse": null
  },
  "outputs": [],
  "warnings": [],
  "limitations": []
}
```

Use `null` or an explicit unavailable status for metrics that cannot be
measured. Never fill unknown metrics with made-up values. The schema can
be extended as implementation proceeds, but preserve these concepts.

------------------------------------------------------------------------

## 14. Error Handling and Recovery

Handle the following cases explicitly:

-   Invalid or corrupt video.
-   Unsupported codec.
-   No usable frames after filtering.
-   COLMAP missing or incompatible.
-   Feature matching produces too few verified matches.
-   SfM fails or registers too few images.
-   Multiple disconnected reconstruction components.
-   Dense reconstruction unavailable due to build/GPU/memory
    limitations.
-   Mesh generation fails or produces empty geometry.
-   Texture generation unavailable.
-   Missing or inconsistent GPS/GCP/camera metadata.
-   Disk full or insufficient write permissions.
-   User cancels processing.
-   Backend restarts while a job is running.
-   Output file is missing, empty, or corrupt.
-   Frontend loses connection to the backend.

For each error: 1. Mark the correct stage as failed or skipped. 2.
Preserve logs and valid outputs from earlier stages. 3. Give the user a
plain-language explanation and a practical next step. 4. Do not proceed
through dependent stages with invalid inputs. 5. Allow retry from the
failed stage where safe; if dependencies or inputs changed, restart the
affected stages. 6. Ensure child processes are terminated safely when
cancellation is requested.

------------------------------------------------------------------------

## 15. Security and Reliability

-   Validate file extensions and inspect actual file content where
    practical; do not trust filename alone.
-   Generate internal file names and project IDs; never use unsanitized
    upload names as paths.
-   Prevent path traversal in upload, download, and delete endpoints.
-   Limit upload size, video duration, concurrent jobs, and configurable
    resource usage.
-   Keep API errors free of secrets and sensitive environment variables.
-   Keep `.env` files, API tokens, and private paths out of source
    control.
-   Do not expose arbitrary files from the host machine through the file
    API.
-   Use safe subprocess argument arrays rather than shell string
    interpolation.
-   Store logs per project and avoid logging secrets.
-   Validate generated files before publishing them to the results list.
-   Document that uploaded videos may contain people, private property,
    or location metadata and should be handled accordingly.

------------------------------------------------------------------------

## 16. Testing Plan

### Unit tests

-   Video metadata parsing and invalid input handling.
-   Frame sampling and timestamp mapping.
-   Blur/duplicate filtering.
-   Configuration validation.
-   Output manifest and quality-report generation.
-   File path validation and traversal prevention.
-   API request/response schemas.

### Integration tests

-   Backend health and dependency detection.
-   Upload a short test video.
-   Run frame extraction and verify non-empty frames and manifest.
-   Run COLMAP feature extraction/matching when COLMAP is installed.
-   Run SfM on a small, suitable sample dataset.
-   Run dense reconstruction and mesh generation only when environment
    capability checks pass.
-   Validate viewer-compatible files and downloads.
-   Verify that a failed stage is reported correctly and does not
    produce fake success outputs.

### UI tests / manual checks

-   Upload validation and error messages.
-   Job progress and refresh behavior.
-   Failed and cancelled jobs.
-   Empty results and partial results.
-   3D viewer loading, camera controls, and fit-to-model.
-   Downloading PLY and OBJ/texture assets when available.
-   Responsive layout and no horizontal overflow.
-   No console errors or unhandled promise rejections in core flows.

------------------------------------------------------------------------

## 17. Acceptance Criteria

The MVP is accepted when all required criteria below pass:

1.  The app starts using documented setup commands.
2.  The health endpoint reports backend status and COLMAP availability.
3.  A valid drone video can be uploaded and its metadata displayed.
4.  An invalid or unsupported file is rejected with a useful error.
5.  The frame extraction stage saves real frames, a manifest, and a
    contact sheet.
6.  Preprocessing reports how many frames were accepted and rejected.
7.  Feature matching runs through COLMAP when the dependency is
    available and records its result.
8.  SfM runs on suitable footage and produces a real sparse
    reconstruction, or reports a specific failure.
9.  Dense reconstruction runs when supported and produces a real dense
    point cloud, or reports why it was skipped/failed.
10. Mesh and texture outputs are created only when their input stages
    succeed.
11. Georeferencing is only marked successful when valid reference
    information and a successful alignment exist.
12. The quality report includes available metrics and clearly marks
    unavailable values.
13. The browser viewer displays the actual generated point cloud or
    mesh, not a hard-coded model.
14. Available outputs can be downloaded and non-existent outputs are not
    advertised.
15. Stage logs and warnings are visible from the project UI.
16. Cancelling a job stops its processing subprocesses safely.
17. A failed stage does not falsely mark the entire pipeline as
    successful.
18. The app remains usable when optional GPU, depth-model, texture, or
    georeferencing features are unavailable.
19. The core UI works at desktop and narrow mobile widths.
20. Setup, known limitations, troubleshooting, and test instructions are
    documented.

------------------------------------------------------------------------

## 18. Implementation Milestones

Implement in this order so each phase can be verified before adding
complexity.

### Milestone 1 --- App skeleton and environment checks

-   Create React frontend and FastAPI backend.
-   Implement health/capabilities endpoints.
-   Add project workspace management and dependency checks.
-   Add a README with installation and run commands.

**Done when:** Frontend connects to backend and displays environment
readiness.

### Milestone 2 --- Upload and frame extraction

-   Implement project creation, upload, metadata inspection, frame
    extraction, quality filtering, manifest, and contact sheet.

**Done when:** A user can upload a video and inspect accepted frames.

### Milestone 3 --- COLMAP SfM

-   Implement process runner, safe logs, feature extraction, matching,
    mapper, sparse output export, and SfM report.

**Done when:** A suitable dataset produces a real sparse model, with
failure states tested.

### Milestone 4 --- Dense reconstruction and mesh

-   Implement undistortion, MVS, dense fusion, point-cloud validation,
    meshing, and optional texturing.

**Done when:** The application creates a real dense cloud and mesh where
the environment and footage support them.

### Milestone 5 --- Georeferencing and evaluation

-   Add optional GPS/GCP/known-distance workflows and quality report
    generation.

**Done when:** The report distinguishes relative model coordinates from
validated geographic/metric coordinates.

### Milestone 6 --- Viewer and exports

-   Add interactive 3D viewer, result file list, downloads, and model
    optimization.

**Done when:** Generated results can be inspected and exported.

### Milestone 7 --- Hardening

-   Add cancellation, retries, cleanup, tests, responsive fixes,
    security checks, and troubleshooting documentation.

**Done when:** The acceptance criteria are met and core failures are
handled without misleading success states.

------------------------------------------------------------------------

## 19. COLMAP Integration Guidance

Use the installed COLMAP CLI rather than reimplementing photogrammetry
algorithms. Antigravity should inspect the installed COLMAP version and
available command names/help before constructing commands because CLI
syntax can differ across releases.

Typical processing concepts are:

1.  Feature extraction into a COLMAP database.
2.  Sequential or selected-pair feature matching.
3.  Sparse mapping / incremental reconstruction.
4.  Image undistortion for dense reconstruction.
5.  Patch-match stereo.
6.  Stereo fusion into a dense point cloud.
7.  Export or conversion of reconstruction artifacts as required.

Construct subprocess calls as argument lists, capture stdout/stderr,
record the exact command and version in the project log, enforce
timeouts where appropriate, and validate expected output files after
every command. Never assume a command succeeded just because the process
started.

The exact CLI commands and options must be confirmed against the
installed build during implementation. Provide a diagnostic message that
shows the missing executable or failed stage without exposing unrelated
system details.

------------------------------------------------------------------------

## 20. Final Instruction to Antigravity

Treat this document as the source of truth for the MVP. Build the
pipeline in the specified order and prioritize a real, reproducible
end-to-end result over visual polish. Do not substitute mock data for
processing. Use safe defaults, expose meaningful configuration, record
every stage, and report technical limitations honestly.

Start by inspecting the environment and repository, then implement
Milestone 1 and continue milestone by milestone. At the end, provide: -
A summary of implemented features. - Exact commands to install
dependencies and run the frontend/backend. - Required external software
installation instructions. - Environment variables and configuration
details. - Tests run and their actual results. - Known limitations and
next recommended improvements.

**Success means:** a user can provide a suitable single-pass drone
video, run the real reconstruction pipeline, inspect the resulting 3D
geometry in a viewer, download available model files, and understand the
quality and limitations of the result.
