# Bird's-Eye / AIRVEU3D - workflow redesign

Basis: MUGIN "How to use drones for 3D modeling", UAVCoach "Drone 3D model", Cross3R (arXiv 2605.07978).
NOT read: the IEEE paper (arnumber 10942597) and the YouTube video were not retrievable, so nothing here is based on them.

## Corrected workflow (vs. the original poster)
1. Capture planning (UI) - mission type (terrain / structure / auto), capture guide: one continuous shot, >75 % overlap, steady altitude/angle, nadir grid for terrain, 45 deg orbit for walls.
2. Frame extraction + shot-cut detection (single continuous path only).
3. **Capture QA** (new) - sharpness, forward overlap (feature-hull proxy), tracking breaks, telemetry coverage -> good / marginal / poor + advice (`outputs/capture_qa.json`). Never blocks the run.
4. SfM (COLMAP/pycolmap).
5. Georeferencing from .SRT right after SfM (scale, north-up, RMSE) - not between depth and dense.
6. Dense / plane-sweep DSM (terrain) or MVS/Poisson (object).
7. Mesh + texture (orthomosaic for terrain).
8. **Output QA** (new) - open-edge (hole) share, stretched texture share, degenerate faces.
9. **Delivery package** (new) - master GLB, lite GLB (2048 px), orthomosaic, georeference, QA reports, README with units/limits, zip.
Dropped: video stabilisation (it alters geometry; SfM models the camera itself).

## Reference idea -> status
| Idea | Status |
|---|---|
| Overlap > 75 %, grid/orbit patterns | Guide in UI; overlap measured by Capture QA (proxy, thresholds calibrated lower) |
| Avoid relying on video / blur | Blur share reported |
| Post-flight QA, check holes/warps/stretch | Capture QA + Output QA |
| Master + lite exports with units note | Delivery package |
| External anchoring (GPS) | .SRT georeferencing (already) |
| Cross3R feed-forward reconstruction | NOT integrated: needs GPU and trained weights, not video/SfM based |

## Honest limits
Overlap is a proxy; GPS is consumer-grade; heights not validated against ground truth; unseen sides are never invented.

## Droneer Site manual (photo-based product) - what we borrowed
Workflow there: create project -> import photos -> aerial triangulation -> 2D (DOM/DSM GeoTIFF) / 3D (cloud, OBJ) -> view layers + quality report (calibration rate, GSD, reprojection RMS, features/image, survey area).
Ours already mirrors this for video: frames replace photos; layers (cameras, elevation, 2D map), quality report with registration %, GSD, reprojection error, survey area (added). Not done: ROI cropping, GCP import (manual ground control), GeoTIFF export, POS photo files (we use video .SRT instead). The site-introduction video is an edited product promo with cuts and screen recordings, so it is not usable as reconstruction input.
