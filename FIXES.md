# Birds Eye — fixes and capture guide

## Round 2: why the model looked like giant overlapping sheets (and what changed)

**Cause.** With a single forward pass the baseline between frames is short, so depth error grows with distance squared. The distant mountains and river came out as huge stretched sheets (about 70% of the dense points in your clip) that dominated the mesh and the viewer framing. On a machine without an NVIDIA GPU the dense stage was skipped entirely, so you only saw the sparse points.

| Area | Change |
|---|---|
| `subject_service.py` (new) | **Subject isolation.** Keeps only the dense points inside an oriented box around the SfM-verified sparse points (reprojection error <= 1 px, track >= 3). Far background is removed. Skipped with a notice if the crop looks untrustworthy. UI checkbox, default ON. |
| `cpu_dense_service.py` (new) | **CPU stereo fallback** (OpenCV rectify + SGBM, two baselines per frame (+37% points on the test clip, fewer holes), multi-pair voxel consistency, texture gate). Runs automatically when COLMAP MVS is unavailable. Noisier than GPU MVS. UI checkbox, default ON. |
| `dense_service.py` | `postprocess_cloud`: isolation, then statistical outlier removal. |
| `mesh_service.py` | Poisson octree depth chosen from point spacing (7-10) instead of fixed 9; stretched-triangle and small-island removal; Taubin smoothing; quadric decimation to <= 350k faces. On your clip: 1.06M faces with lumps became 165k faces, clean. |
| `job_manager.py`, schema, UI | New options `isolate_subject`, `cpu_stereo_fallback`. |
| `report_service.py` | Reports dense method and isolation stats. |
| `ModelViewer.tsx` | Meshes use the same robust centering as clouds, so mesh and cloud line up. |

Tests: `backend/tests/test_subject_and_mesh.py` (new). Failures remaining in this sandbox (`test_ai_depth`, `test_normal_app_workflow`, `test_reconstruction_repair`) need COLMAP, model weights or a sample video that were not available here.

## Capture advice for a better model
- A straight forward pass gives almost no depth information. Fly a slow **arc or orbit** around the subject, camera tilted ~45 degrees, and add a second lower oblique pass.
- 70-80% overlap between frames, no zoom changes, avoid motion blur.
- Anything never filmed (back sides, undersides) cannot be measured; see below.

### Round 7: "is the object complete?" (viewpoint coverage)
Your test clip moves only ~8 degrees around the temple, so only one side exists in the data; no software can reconstruct the rest. The app now measures this from the solved camera poses (`coverage_service.py`) and reports it in the stage log, job warnings, `quality_report.json` / `.md` and a banner in the 3D viewer ("Partial view: N of 360 degrees filmed") instead of leaving the user guessing. Verdicts: `single_side` (< 120 deg), `partial_orbit` (120-300 deg), `full_orbit` (>= 300 deg).

**How to film a complete model:** fly a slow circle around the subject with the camera aimed at it and tilted ~45 degrees down, then a second lower circle. Keep 70-80% overlap, constant zoom, no fast turns. Use the **High** quality preset for the final run.

### Round 6: viewer features (inspired by AirPano's interactive tours, for video-based models)
New bar at the bottom-left of the 3D viewer, tested by clicking each in headless Chromium:
- **Auto-rotate** turntable (stops when you grab the model)
- **Fly-through**: replays the drone's flight path as a camera move (the video counterpart of a panorama tour)
- **Mini-map**: top-down plan with the drone path (green) and your viewpoint (yellow)
- **Copy view link**: link carries the exact camera position; opening it restores the view
- **Fullscreen**
Also fixed: the top toolbars overlapped on narrow windows; the sidebar and Diagnostics dialog said COLMAP "Missing" even when the built-in engine was running.

### Round 5: full-app audit (every button's backend call, run end to end)
I ran the real server and drove every API the UI uses with a script (create, upload, run, status, results, downloads, events, cancel, delete). 23 checks pass. On the bundled clip the whole job (9 frames, CPU only, no COLMAP program) completes in about 30 s and produces OBJ/GLB/PLY files and a report.

| Defect found | Fix |
|---|---|
| A second job could be started on the same project while one ran; both rewrote `database.db` and crashed each other | Server rejects it with HTTP 409; also for delete, upload and sample-load while a job runs |
| Without the COLMAP program the whole pipeline failed at the first stage | Built-in **pycolmap engine** (`pip install pycolmap`) does features, matching and SfM, run in a child process so a C++ abort can never kill the web server |
| Stale `database.db-wal/-shm` left by a killed run made the next run fail with "database is locked" | Removed together with the database |
| Without COLMAP, the dense and mesh stages raised instead of using the fallbacks | Dense reports "unsupported" so CPU stereo runs; meshing uses Poisson |
| A file path object in the job state made `GET /api/jobs/{id}` return 500 | Paths stored as strings |
| `load_sample` accepted `../` and silently loaded a different video when the name was wrong | Bare file name only; 404 if missing |
| Report said "Pipeline Status: running" and a confusing point count for subject isolation | Status "completed"; isolation shown as a percentage |

### Round 4: speed, zoom clarity, audit
| Defect found | Fix |
|---|---|
| Every skipped video frame was fully decoded and colour-converted | `grab()` skips unneeded frames; only sampled frames are retrieved |
| Full-size frames (e.g. 4K) went into SIFT and dense stereo | Frames saved at the preset's size; SIFT image size and feature count set explicitly |
| Dense stereo hard-capped at 1200 px (soft when zoomed) and undistorter unbounded | Resolution comes from the preset (1000 / 1600 / 2400 px) in undistorter, PatchMatch, fusion and CPU stereo |
| Mesh face budget and Poisson depth were fixed; COLMAP's mesh was never decimated | Per-preset face budget (150k / 350k / 700k) and Poisson depth limit (9 / 10 / 11) for both meshers |
| AI-depth used 12 frames at stride 4 regardless of speed needs | Per-preset frames and stride |
| `enable_texturing` did nothing | Deprecated and ignored (not shown in UI); surfaces are photo vertex-coloured, UV texture baking is not implemented |
| One setting for everything | New **Quality preset** (Fast / Balanced / High) in the UI and API (`quality_preset`) |

Choose **Fast** to check that the flight worked, **High** for the final model.

### Round 3 (city/building footage)
- `mesh_service.clean_mesh_geometry` now runs on **every** mesh (COLMAP Delaunay too, not only Poisson): faces outside the SfM-verified volume (sky/far-terrain sheets) are dropped, then triangles with an edge >10x the typical edge, then tiny islands. Without a sparse model it falls back to the mesh's own 1-99 percentile box (weaker).
- The AI-depth (Depth Anything) fused cloud is also cropped to the verified volume, and sampled every 4 px instead of 8 so surfaces are not blocky.

## Round 1 fixes

## What was changed

| Area | Problem | Fix |
|---|---|---|
| `frame_service.py` | Near-duplicate test used `TM_CCORR_NORMED`, which is not mean-centred: *unrelated* photos score ~0.986, above the 0.985 default threshold, so the filter was close to random and could throw away frames that had moved a lot. | Uses zero-mean `TM_CCOEFF_NORMED` (unrelated ≈ 0, identical = 1). Handles flat frames. |
| `colmap_service.py` | GPU→CPU retry in feature **matching** overwrote the flag name (`cmd[4]`) instead of its value, so the retry command was invalid and could never succeed. | Flips the value after `--SiftMatching.use_gpu`. |
| `colmap_service.py` | Only point counts were reported, which hides the cause of smeared clouds. | Reports mean reprojection error and mean track length, and warns on low registration, split models, high error, short tracks (stage log + `job.warnings` + quality report). |
| `mesh_service.py` | If COLMAP's Delaunay mesher produced nothing the result was `Faces: 0`; the README's Poisson stage did not exist. | Poisson fallback (Open3D) on the selected cloud, normals oriented toward the drone cameras. |
| `mesh_service.py` | Poisson invents surface wherever nothing was observed. | Default: surface with no supporting observations is **removed** (unseen regions stay empty). Optional `fill_unseen_regions`: keep Poisson's closed surface, labelled *extrapolated*. |
| `ai_depth_service.py` | Merge with the MVS cloud crashed silently (COLMAP's `fused.ply` has normals, the AI cloud does not) and fell back to AI-only. | Both rebuilt on a common x,y,z,r,g,b layout before merging. |
| `ai_depth_service.py` | AI points were stacked on top of measured points → doubled "ghost" layers; views with a guessed scale were still used; sky mask used an absolute threshold on a model output with no fixed range. | AI points only kept where the measured cloud has a gap; views with < 8 supporting sparse points are skipped; sky mask is per-image relative. |
| `job_manager.py` | Looked up a result key that didn't exist, so the AI cloud was never registered as an output. | Key added; `fill_unseen_regions` passed to meshing. |
| UI | AI-depth label claimed it fills "missing surfaces". | Label corrected; new checkbox for `fill_unseen_regions`. |

`open3d` was added to both `requirements.txt` files. New tests: `backend/tests/test_reconstruction_fixes.py`.

## Check these in your next job folder (`workspace/proj_xxxx/`)

1. `frames/frame_manifest.csv` — count rows whose `decision_reason` starts with *Stationary* or *Blurry*. A large share means frames were being thrown away.
2. Stage log for **SfM** — registered frames / total, number of submodels, mean reprojection error. These new warnings tell you whether the cameras were solved well. If registration is low or error > ~1.5 px, no meshing or AI step can fix the geometry; the capture or frame sampling has to change.
3. `outputs/quality_report.json` — now includes `mesh.method` and `mesh.unseen_regions`.

## Parts the video never saw

Photogrammetry can only reconstruct what at least two frames both saw. Nothing in software can *measure* a hidden side. Options, from most to least reliable:

1. **Capture it.** Add passes: an orbit around the subject at ~45° camera tilt, plus a lower oblique pass; 70–80% overlap between consecutive frames; fly slowly (motion blur and low overlap are the usual cause of fragmented models). Keep one camera setting (no zoom changes).
2. **Leave it empty (default).** Honest result; the quality report says so.
3. **Close it by extrapolation** (`fill_unseen_regions`, UI checkbox). Looks complete, is not measured. Never use it for measurement, and say so when presenting it.
4. **AI depth** only helps pixels that *were* visible (water glare, plain roofs). It cannot add hidden sides.

## Limits of this patch

Round 1 was tested on synthetic data. Round 2 was run on your clip with pycolmap (SfM, 25/25 frames registered) plus the CPU stereo and Poisson stages; it was **not** run with the real COLMAP binary or CUDA MVS.

## Round 8 – Input-video analysis & sample orbit clip
- Taj Mahal clip analysis: cinematic edit (fade in/out, forward fly-in, subject small/hazy, re-encoded) → cameras span only ~26° around the subject, so only one side can exist and fine detail is lost. This is an input problem, not a pipeline bug; the coverage banner now says so.
- `tools/make_sample_orbit_video.py` generates a two-lap 360° orbit clip; `samples/sample_orbit.mp4` is a ready-made output. Processed result: 349° coverage (12/12 sectors, "full_orbit"), closed model viewed from all four sides.
- Filming guide: orbit ≥300° at constant radius with camera aimed at subject (~45° down), second lower lap, 70–80% overlap, constant zoom, no cuts/fades/edits, original 1080p/4K file, slow steady speed, avoid sky-only frames and reflective/moving objects.

## Round 9 – Aerial-survey mode (single-pass drone over a place)
- Tested on a REAL drone survey (OpenDroneMap "aukerman" dataset, 77 frames, park site: building, parking lot, road, paths, pond) converted to a video: 76/76 frames registered, 0.76 px reprojection error, 36k sparse points.
- Problem found: the object pipeline (subject isolation, Poisson shell, CPU stereo) cropped away the ground and reported "only one side filmed".
- New `services/aerial_service.py`: auto-detects nadir survey flights (`scene_mode`: auto|aerial|object), levels the model to the fitted ground plane, builds a DSM from SfM points, an orthomosaic (best-overhead frame per cell, feathered blending), and a textured GLB/OBJ/PLY + `dsm_heightmap.png` + `orthomosaic.jpg` (4096 px). ~45 s, no GPU/COLMAP-dense needed.
- Job manager skips dense/AI-depth in survey mode and reports status "completed"; report says "Aerial survey".
- Limits (stated honestly): height comes from sparse SfM points (relief ~cm-dm level, 2x vertical exaggeration in viewer), scale is relative without GCPs/GPS, vertical walls and areas under canopy are not modelled.
- Tests: tests/test_aerial.py. Sample: samples/real_aerial_survey.mp4.

## Round 10 – Dense heights for aerial mode (CPU plane-sweep stereo)
- Sparse-only terrain looked like a photo draped on a smooth sheet. `AerialService.plane_sweep` now refines the height model on a 2x finer grid: for each ground cell it tests 40 candidate heights (±2% of footprint) against 30 overlapping frames (locally normalised intensity agreement), anchored to the sparse terrain, parabolic sub-level refinement, median+Gaussian smoothing. Cells with no trustworthy agreement fall back to the sparse terrain. No GPU/CUDA required (~75 s on CPU).
- Result on the real survey: ~380k vertices / 757k faces; tree line, shrub patch, pond depression, path ridges and the building roof now have real relief.
- Fixed a bug where an over-wide search range produced garbage heights (range is now 2% of footprint).
- Limits: still a height field (one height per ground position) - no vertical walls or overhangs; texture-less grass is regularised toward the sparse terrain; scale is relative.

## Round 11 – GPS georeferencing, 2D map viewer, fine-detail texture, capture planner, AI-depth fixes
- **GPS georeferencing** (`services/geo_service.py`): optional drone `.SRT` flight log (upload card, `POST /api/projects/{id}/telemetry`, or a sample's same-name `.SRT`). Parses DJI new/old SRT formats, samples GPS at each frame's start time, converts to local ENU metres and fits a robust similarity transform (Umeyama + RANSAC). Verified on the real survey (EXIF GPS written to an SRT): 1 model unit = 24.4 m, RMSE 1.1 m over 76/76 frames on a 163 m path. Aerial models are then north-up with real-metre size; the 3D viewer's measure tool/size/elevation labels convert to metres (the display-only 2x height exaggeration is undone). Report: `georeferencing.status = "GPS-scaled (metres)"`, rmse, ground size, GSD. NOT survey-grade (no GCPs); absolute position is consumer-GPS quality.
  - Bug fixed during testing: GPS must be sampled at the SRT block START (frame time), not its midpoint (half-frame error = ~10 m on this data).
- **2D Map tab** (`components/viewer/MapViewer.tsx`): orthomosaic with pan/zoom, height-map layer + overlay, distance measuring (metres when GPS-scaled), scale bar, north arrow, coordinates, site size + cm/pixel, download.
- **Fine detail**: orthomosaic is sized to the real ground sample distance (1 texel ~ 1 source pixel, cap 6144 px); GSD (cm/pixel) is reported.
- **Capture planner** (`coverage_service` + job manager): reports the biggest missing viewing arc and, with GPS, the compass side to fly ("fly one more pass on the north-east side..."); aerial mode advises an oblique pass for walls/facades.
- **AI depth (Depth Anything V2)** fixes: weights were never shipped and README had no source -> added `tools/download_depth_model.py` + clear error; ONNX input/output names were hard-coded to one export (now read from the model; tested with a differently-named model); intrinsics now scaled to the frame size actually used; RANSAC seeded (deterministic). The weights could not be downloaded in the build sandbox, so the full AI stage is untested here.
- Aerial 3D clean-up: height outliers (vs local median) and weakly-supported disconnected islands (<25% of the main surface) are dropped from the 3D mesh (they had only a few supporting points and produced a floating sliver ~10 m off). The 2D orthomosaic still shows the full imaged area.
- End-to-end on the real survey via the app (sample + .SRT): completed in 450 s on a CPU-only sandbox; 75/75 frames, 0.62 px reprojection error, GPS scale RMSE 1.2 m, site 276 x 184 m, 9.4 cm/pixel.

## Round 12 - Edited / multi-shot clips (the Taj Mahal drone video)
- Root cause of the smeared, stacked sheets: the clip is a MONTAGE of 12 separate shots (wide approach, low side view, marble close-up against blue sky, the wide approach again...). Frames from different shots are not one camera path, so SfM/dense stereo mixed unrelated viewpoints.
- `FrameService.detect_shots`: splits a video into continuous shots (colour-histogram jump OR too few epipolar-consistent ORB matches between consecutive samples). Verified on the clip: cuts found at 0.7, 11.3, 13.7, 15.7, 22.0, 24.3, 26.3, 31.0 s.
- Default `auto_shot_select`: reconstruct only from the longest continuous shot (needs >= 8 samples), log which shots were skipped. Result for the Taj clip: one coherent landscape (gate, garden axis, Taj, river, trees) instead of stacked sheets.
- Aerial/height-field mode also catches forward-moving oblique flyovers (parallel optical axes). Limits: facade/walls are stretched (height field), only 18 frames registered from the chosen shot.
- Tests: tests/test_shots.py

## Round 13 - workflow redesign from references
- Capture QA (capture_qa_service.py): overlap proxy, tracking breaks, blur, telemetry coverage; report + log, never blocks.
- Output QA + delivery package (delivery_service.py): holes/stretch checks, master+lite GLB, README with units, zip.
- UI: "What did you film?" mission selector (scene_mode) + capture guide. Report: capture/output QA, survey area.
- docs/DESIGN.md: corrected workflow and reference mapping. Tests: test_qa_delivery.py.

## Round 14 - Explore Any Place (demo)
- Sidebar button "Explore Any Place (Demo)": type a place -> 3D terrain + satellite + extruded buildings (MapLibre), presets, orbit, street/satellite, terrain exaggeration, distance + area measuring (metric/imperial, per-segment, elevation range). Needs internet; labelled demo, not pipeline output.

## Round 15 - simpler UI for presentation
- Tabs renamed as a numbered flow: 1 Upload Video, 2 Processing, 3 3D Model & Measure, 4 Map, 5 Report & Download. Header Diagnostics button removed (still in sidebar "Details"). Result opens automatically when processing finishes.

## Round 16 - folder-of-frames input
- POST /api/projects/{id}/import_folder + "Or use a folder of frames" panel: reads jpg/png frames in place (no upload), natural sort, even thinning to max images, native resolution (<=1920 px), all frames used (no re-sampling, no shot-cut split, relaxed blur floor). Tested on 240 frames -> 80 used -> full model in ~70 s (synthetic orbit; real Tanks and Temples not available in sandbox).

## Round 17 - code audit
- pyflakes clean of real defects (unused imports/variables removed); tsc + vite build clean.
- Environment-dependent tests (AI depth weights, CUDA COLMAP, sample clip) now skip with a reason instead of failing: 47 passed, 9 skipped, 0 failed.

## Round 18 - measurable models
- Viewer: measure two points, type the real length, "Set scale" -> all distances in metres (saved per project). Fixes unlabeled relative units.
- Folder import reads EXIF GPS from photos -> telemetry -> automatic metric scale.
- datasets/synthetic_temple_known_size (80 frames + ground_truth.json + README) and tools/evaluate_accuracy.py: camera error median 0.39 m, surface error median 0.41 m (synthetic).

## Round 19 - viewer fixes
- Switching Dense Cloud <-> Surface Mesh could leave the old model on screen (a slower earlier download overwrote the newer one, and restyling hit stale geometry). Loads are now cancelled when superseded, and restyling only applies to the currently selected file.
- Hints on the two settings that hurt measuring accuracy (AI depth completion, closing unseen surfaces): keep OFF.

## Round 20
- Size/elevation readouts and measure markers now follow 'Set scale' immediately; markers sized to the model (were huge on small models). Verified in a browser.
