"""
pycolmap engine: runs COLMAP's feature extraction, matching and incremental SfM in-process.

Used automatically when the COLMAP *program* is not installed but the `pycolmap` pip package is
(`pip install pycolmap`). It produces exactly the files the rest of the pipeline reads (database.db,
text sparse models), so every later stage behaves the same. Dense MVS still needs the COLMAP program
with CUDA; without it the pipeline uses the CPU stereo fallback.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.presets import get_preset


def _import():
    try:
        import pycolmap  # noqa: WPS433
        return pycolmap
    except Exception:
        return None


def _run_isolated(step: str, project_dir: Path, args: Dict[str, Any], log_callback=None) -> Dict[str, Any]:
    """
    Run one pycolmap step in a child process. COLMAP's C++ core calls abort() on some errors
    (e.g. a locked database); in-process that would kill the whole web server, so it is isolated here
    and surfaced as an ordinary RuntimeError instead.
    """
    import json
    import subprocess
    import sys
    cmd = [sys.executable, "-m", "app.services.pycolmap_worker", step, str(project_dir), json.dumps(args)]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[2]))
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-6:]
        raise RuntimeError(f"pycolmap {step} failed (code {proc.returncode}): {' | '.join(tail)}")
    for line in (proc.stdout or "").splitlines():
        if line.startswith("RESULT "):
            return json.loads(line[7:])
    return {}


class PyColmapEngine:
    @staticmethod
    def available() -> bool:
        return _import() is not None

    @staticmethod
    def version() -> Optional[str]:
        pc = _import()
        return getattr(pc, "__version__", "unknown") if pc else None

    @classmethod
    def _extract(cls, project_dir: Path, quality_preset: str, use_gpu: bool, log_callback=None) -> Dict[str, Any]:
        pc = _import()
        preset = get_preset(quality_preset)
        colmap_dir = project_dir / "colmap"
        colmap_dir.mkdir(parents=True, exist_ok=True)
        db_path = colmap_dir / "database.db"
        for suffix in ("", "-wal", "-shm"):          # stale WAL/SHM files from a killed run lock the new database
            stale = db_path.with_name(db_path.name + suffix)
            if stale.exists():
                stale.unlink()
        names = sorted(p.name for p in (project_dir / "frames").glob("frame_*.jpg"))

        reader = pc.ImageReaderOptions()
        reader.camera_model = "SIMPLE_RADIAL"
        ext = pc.FeatureExtractionOptions()
        ext.max_image_size = preset.sift_dim
        ext.sift.max_num_features = preset.sift_features
        device = pc.Device.cuda if use_gpu else pc.Device.cpu
        if log_callback:
            log_callback(f"pycolmap: extracting SIFT features from {len(names)} frames "
                         f"(max {preset.sift_dim}px, {preset.sift_features} features, {'GPU' if use_gpu else 'CPU'})...")
        try:
            pc.extract_features(db_path, project_dir / "frames", image_names=names,
                                camera_mode=pc.CameraMode.SINGLE, reader_options=reader,
                                extraction_options=ext, device=device)
        except Exception:
            if not use_gpu:
                raise
            if log_callback:
                log_callback("[WARNING] pycolmap GPU extraction failed, retrying on CPU.")
            pc.extract_features(db_path, project_dir / "frames", image_names=names,
                                camera_mode=pc.CameraMode.SINGLE, reader_options=reader,
                                extraction_options=ext, device=pc.Device.cpu)
        return {"database_path": str(db_path), "database_size_bytes": db_path.stat().st_size}

    @classmethod
    def _match(cls, project_dir: Path, strategy: str, use_gpu: bool, log_callback=None) -> Dict[str, Any]:
        pc = _import()
        db_path = project_dir / "colmap" / "database.db"
        device = pc.Device.cuda if use_gpu else pc.Device.cpu
        for attempt_device in ([device, pc.Device.cpu] if use_gpu else [device]):
            try:
                if strategy == "sequential":
                    pairing = pc.SequentialPairingOptions()
                    pairing.overlap = 10
                    pairing.quadratic_overlap = True
                    pairing.loop_detection = False
                    pc.match_sequential(db_path, pairing_options=pairing, device=attempt_device)
                else:
                    pc.match_exhaustive(db_path, device=attempt_device)
                break
            except Exception:
                if attempt_device == pc.Device.cpu:
                    raise
                if log_callback:
                    log_callback("[WARNING] pycolmap GPU matching failed, retrying on CPU.")
        return {"matcher": f"pycolmap_{strategy}", "database_path": str(db_path)}

    @classmethod
    def _map(cls, project_dir: Path, sparse_dir: Path, log_callback=None) -> List[Path]:
        """Incremental SfM. Returns the written model directories (text format)."""
        pc = _import()
        db_path = project_dir / "colmap" / "database.db"
        opts = pc.IncrementalPipelineOptions()
        # Same relaxed initialisation the COLMAP-binary path uses: single forward drone passes have
        # small triangulation angles and the defaults then refuse to start at all.
        opts.mapper.init_min_tri_angle = 1.5
        opts.mapper.init_max_forward_motion = 1.0
        opts.mapper.abs_pose_min_num_inliers = 15
        opts.mapper.abs_pose_min_inlier_ratio = 0.1
        opts.min_num_matches = 10
        if log_callback:
            log_callback("pycolmap: running incremental mapper...")
        recs = pc.incremental_mapping(db_path, project_dir / "frames", sparse_dir, opts)
        written: List[Path] = []
        for k, rec in recs.items():
            mdir = sparse_dir / str(k)
            mdir.mkdir(parents=True, exist_ok=True)
            rec.write_text(str(mdir))
            written.append(mdir)
        return written

    # Public API: isolated in child processes.
    @classmethod
    def extract_features(cls, project_dir: Path, quality_preset: str, use_gpu: bool, log_callback=None) -> Dict[str, Any]:
        if log_callback:
            log_callback("pycolmap: extracting SIFT features (isolated process)...")
        return _run_isolated("extract", project_dir, {"preset": quality_preset, "use_gpu": use_gpu})

    @classmethod
    def match(cls, project_dir: Path, strategy: str, use_gpu: bool, log_callback=None) -> Dict[str, Any]:
        if log_callback:
            log_callback(f"pycolmap: {strategy} feature matching (isolated process)...")
        return _run_isolated("match", project_dir, {"strategy": strategy, "use_gpu": use_gpu})

    @classmethod
    def map(cls, project_dir: Path, sparse_dir: Path, log_callback=None) -> List[Path]:
        if log_callback:
            log_callback("pycolmap: running incremental mapper (isolated process)...")
        res = _run_isolated("map", project_dir, {"sparse_dir": str(sparse_dir)})
        return [Path(p) for p in res.get("models", [])]
