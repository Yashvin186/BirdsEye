import shutil
import platform
import subprocess
from pathlib import Path
from typing import Dict, Any
import cv2

from app.config import settings
from app.schemas.capabilities import CapabilitiesResponse, DependencyInfo, PipelineStageCapability


def get_disk_free_gb(path: Path) -> float:
    try:
        usage = shutil.disk_usage(path if path.exists() else path.parent)
        return round(usage.free / (1024 ** 3), 2)
    except Exception:
        return 0.0


def check_ffmpeg() -> DependencyInfo:
    configured_path = settings.FFMPEG_EXE
    exe = None
    if configured_path and Path(configured_path).exists():
        exe = configured_path
    else:
        exe = shutil.which("ffmpeg")

    if not exe:
        return DependencyInfo(
            name="FFmpeg",
            available=False,
            details="FFmpeg not found. OpenCV video decoder will be used as fallback."
        )

    try:
        proc = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=5)
        first_line = proc.stdout.splitlines()[0] if proc.stdout else "Available"
        return DependencyInfo(
            name="FFmpeg",
            available=True,
            version=first_line[:60],
            path=str(exe),
            details="Available for video inspection, frame slicing and audio probe."
        )
    except Exception as e:
        return DependencyInfo(name="FFmpeg", available=False, details=str(e))


def check_colmap() -> DependencyInfo:
    configured_exe = settings.COLMAP_EXE
    exe = shutil.which(configured_exe) or (configured_exe if Path(configured_exe).exists() else None)
    
    # Check standard local paths if not found
    if not exe:
        project_root = settings.BIRDS_EYE_WORKSPACE.parent
        candidates = [
            project_root / "bin" / "colmap" / "COLMAP-3.9.1-windows-cuda" / "COLMAP.bat",
            project_root / "bin" / "colmap" / "COLMAP-3.9.1-windows-cuda" / "bin" / "colmap.exe",
            project_root / "bin" / "colmap" / "COLMAP-3.9.1-windows-no-cuda" / "COLMAP.bat",
            project_root / "bin" / "colmap" / "COLMAP-3.9.1-windows-no-cuda" / "bin" / "colmap.exe",
            project_root / "bin" / "colmap" / "COLMAP.bat",
            project_root / "bin" / "colmap" / "colmap.bat",
            project_root / "bin" / "colmap" / "colmap.exe",
            Path("C:/colmap/colmap.bat"),
            Path("C:/colmap/colmap.exe"),
            Path("C:/Program Files/COLMAP/colmap.bat"),
            Path("D:/colmap/colmap.bat"),
            Path("D:/colmap/colmap.exe"),
        ]
        for c in candidates:
            if c.exists():
                exe = str(c)
                break

    if not exe:
        return DependencyInfo(
            name="COLMAP",
            available=False,
            details="COLMAP was not found on PATH or standard directories. SfM and MVS stages require COLMAP."
        )

    try:
        proc = subprocess.run([exe, "-h"], capture_output=True, text=True, timeout=5)
        output = proc.stdout or proc.stderr
        lines = [l.strip() for l in output.splitlines() if l.strip()]
        version = lines[0] if lines else "COLMAP"
        if len(lines) > 1 and "with cuda" in lines[1].lower():
            version = f"{lines[0]} (with CUDA)"
            has_cuda = True
        else:
            has_cuda = "with cuda" in output.lower() and "without cuda" not in output.lower()

        cuda_note = "CUDA enabled (dense MVS supported)." if has_cuda else "Built without CUDA (dense patch_match_stereo unsupported; sparse SfM and Delaunay meshing supported)."
        return DependencyInfo(
            name="COLMAP",
            available=True,
            version=version,
            path=str(exe),
            details=f"COLMAP CLI is callable. {cuda_note}"
        )
    except Exception as e:
        return DependencyInfo(name="COLMAP", available=False, details=f"Failed to execute COLMAP: {e}")


def check_colmap_dense_capable() -> tuple[bool, str]:
    """Tests if the configured COLMAP executable can execute patch_match_stereo."""
    colmap_info = check_colmap()
    if not colmap_info.available or not colmap_info.path:
        return False, "COLMAP executable is not available."
    try:
        proc = subprocess.run([colmap_info.path, "patch_match_stereo", "-h"], capture_output=True, text=True, timeout=5)
        combined = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0 or "requires cuda" in combined.lower():
            return False, "Current COLMAP build requires CUDA for dense patch_match_stereo, but is compiled without CUDA."
        return True, "COLMAP dense patch-match stereo is supported."
    except Exception as e:
        return False, f"Error probing COLMAP dense capability: {e}"


def get_power_status() -> Dict[str, Any]:
    """Detects whether the machine is running on AC charger or laptop battery."""
    on_battery = False
    battery_pct = 100
    charger_connected = True
    status_text = "Plugged into AC power (NVIDIA GPU ready)"

    if platform.system() == "Windows":
        try:
            import ctypes
            class SYSTEM_POWER_STATUS(ctypes.Structure):
                _fields_ = [
                    ('ACLineStatus', ctypes.c_byte),
                    ('BatteryFlag', ctypes.c_byte),
                    ('BatteryLifePercent', ctypes.c_byte),
                    ('SystemStatusFlag', ctypes.c_byte),
                    ('BatteryLifeTime', ctypes.c_ulong),
                    ('BatteryFullLifeTime', ctypes.c_ulong),
                ]
            s = SYSTEM_POWER_STATUS()
            if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)):
                # ACLineStatus: 0 = Offline (battery), 1 = Online (AC/charger), 255 = Unknown
                if s.ACLineStatus == 0:
                    on_battery = True
                    charger_connected = False
                    battery_pct = int(s.BatteryLifePercent) if s.BatteryLifePercent <= 100 else 100
                    status_text = f"Running on Battery ({battery_pct}%) - CPU mode recommended"
                elif s.ACLineStatus == 1:
                    on_battery = False
                    charger_connected = True
                    battery_pct = int(s.BatteryLifePercent) if s.BatteryLifePercent <= 100 else 100
                    status_text = f"Charger connected ({battery_pct}%) - NVIDIA GPU ready"
        except Exception:
            pass

    return {
        "on_battery": on_battery,
        "charger_connected": charger_connected,
        "battery_percent": battery_pct,
        "status_text": status_text
    }


def check_gpu() -> DependencyInfo:
    # Check OpenCV CUDA
    try:
        cuda_count = cv2.cuda.getCudaEnabledDeviceCount()
        if cuda_count > 0:
            return DependencyInfo(
                name="GPU / CUDA",
                available=True,
                details=f"OpenCV CUDA devices detected: {cuda_count}"
            )
    except Exception:
        pass

    # Windows CIM / WMI Video Controller check
    if platform.system() == "Windows":
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
                capture_output=True, text=True, timeout=5
            )
            gpus = [g.strip() for g in res.stdout.splitlines() if g.strip()]
            if gpus:
                gpu_names = ", ".join(gpus)
                has_nvidia = any("nvidia" in g.lower() for g in gpus)
                return DependencyInfo(
                    name="GPU",
                    available=has_nvidia,
                    details=f"Hardware detected: {gpu_names}. {'CUDA compatible' if has_nvidia else 'No NVIDIA CUDA detected (CPU fallbacks will be used)'}"
                )
        except Exception:
            pass

    return DependencyInfo(
        name="GPU / CUDA",
        available=False,
        details="No dedicated CUDA GPU detected. Dense patch-match stereo requires CUDA in standard COLMAP builds."
    )


def check_opencv() -> DependencyInfo:
    return DependencyInfo(
        name="OpenCV",
        available=True,
        version=cv2.__version__,
        details="Video decoding, frame extraction, Laplacian blur scoring, color analysis."
    )


def check_mesh_tools() -> DependencyInfo:
    try:
        import trimesh
        tr_ver = getattr(trimesh, '__version__', 'installed')
        return DependencyInfo(
            name="Trimesh & PLY Tools",
            available=True,
            version=f"trimesh {tr_ver}",
            details="Point cloud parsing, normal estimation, Poisson/surface meshing, OBJ/PLY/GLB export."
        )
    except Exception as e:
        return DependencyInfo(
            name="Trimesh & PLY Tools",
            available=False,
            details=str(e)
        )


def evaluate_system_capabilities() -> CapabilitiesResponse:
    colmap_info = check_colmap()
    ffmpeg_info = check_ffmpeg()
    opencv_info = check_opencv()
    gpu_info = check_gpu()
    mesh_info = check_mesh_tools()

    free_gb = get_disk_free_gb(settings.BIRDS_EYE_WORKSPACE)

    dense_supported, dense_reason = check_colmap_dense_capable()

    stages = [
        PipelineStageCapability(
            stage_id="validating",
            title="Video Validation & Intake",
            available=True,
            primary_engine="OpenCV + FFmpeg",
            status_note="Ready: Accepts MP4, MOV, validates frames, duration, and codecs."
        ),
        PipelineStageCapability(
            stage_id="extracting_frames",
            title="Frame Extraction",
            available=True,
            primary_engine="OpenCV VideoCapture / FFmpeg",
            status_note="Ready: Extracts frames at configurable intervals with timestamps."
        ),
        PipelineStageCapability(
            stage_id="preprocessing",
            title="Quality Filtering & Preprocessing",
            available=True,
            primary_engine="OpenCV & NumPy",
            status_note="Ready: Computes Laplacian sharpness, detects blur/duplicates, builds contact sheet."
        ),
        PipelineStageCapability(
            stage_id="feature_matching",
            title="Feature Detection & Matching",
            available=colmap_info.available,
            primary_engine="COLMAP SIFT Feature Extractor & Matcher",
            status_note="Ready" if colmap_info.available else "Blocked: Requires COLMAP CLI executable."
        ),
        PipelineStageCapability(
            stage_id="sfm",
            title="Structure-from-Motion (SfM)",
            available=colmap_info.available,
            primary_engine="COLMAP Incremental Mapper",
            status_note="Ready" if colmap_info.available else "Blocked: Requires COLMAP CLI executable."
        ),
        PipelineStageCapability(
            stage_id="dense_reconstruction",
            title="Multi-View Stereo (Dense Cloud)",
            available=dense_supported,
            primary_engine="COLMAP Patch-Match Stereo",
            status_note="Ready: CUDA-enabled COLMAP dense MVS available." if dense_supported else (
                f"Unsupported with current executable: {dense_reason} Sparse SfM point cloud will be preserved."
            )
        ),
        PipelineStageCapability(
            stage_id="ai_depth",
            title="AI Depth Densification",
            available=True,
            primary_engine="Depth Anything V2 (ONNX)",
            status_note="Ready: Monocular relative depth estimation and metric surface completion."
        ),
        PipelineStageCapability(
            stage_id="meshing_texturing",
            title="Surface Mesh & Texture",
            available=mesh_info.available,
            primary_engine="COLMAP Delaunay Mesher / Trimesh",
            status_note="Ready: Reconstructs 3D surface mesh from validated sparse SfM / dense MVS cloud."
        ),
        PipelineStageCapability(
            stage_id="georeferencing_evaluation",
            title="Georeferencing & Quality Report",
            available=True,
            primary_engine="NumPy & Quality Evaluator",
            status_note="Ready: Evaluates registration metrics, reprojection error, and reports scale status honestly."
        ),
        PipelineStageCapability(
            stage_id="packaging",
            title="Packaging & 3D Viewer Asset Prep",
            available=True,
            primary_engine="Internal Exporter",
            status_note="Ready: Prepares PLY, OBJ, and JSON reports for interactive Three.js viewer and download."
        ),
    ]

    from app.services.pycolmap_engine import PyColmapEngine
    sfm_engine = "colmap" if colmap_info.available else ("pycolmap" if PyColmapEngine.available() else "none")

    setup_recs = []
    if sfm_engine == "pycolmap":
        setup_recs.append("COLMAP program not found: SfM runs on the built-in pycolmap engine and dense uses CPU stereo. Install COLMAP (CUDA build) for the sharpest dense models.")
    elif not colmap_info.available:
        setup_recs.append("Install COLMAP (https://colmap.github.io/install.html) and add to PATH or configure COLMAP_EXE in .env.")
    elif not dense_supported:
        setup_recs.append("Current COLMAP executable was built without CUDA. To enable dense MVS, install a CUDA-enabled COLMAP Windows release matching your NVIDIA GPU.")
    if not gpu_info.available:
        setup_recs.append("No NVIDIA GPU detected.")
    if free_gb < 10.0:
        setup_recs.append(f"Low workspace disk space ({free_gb} GB free). Video reconstruction requires at least 10 GB free.")

    return CapabilitiesResponse(
        os_name=f"{platform.system()} {platform.release()} ({platform.machine()})",
        python_version=platform.python_version(),
        disk_free_gb=free_gb,
        workspace_path=str(settings.BIRDS_EYE_WORKSPACE),
        colmap=colmap_info,
        ffmpeg=ffmpeg_info,
        opencv=opencv_info,
        gpu=gpu_info,
        mesh_tools=mesh_info,
        power_status=get_power_status(),
        stages=stages,
        sfm_engine=sfm_engine,
        ready_for_pipeline=sfm_engine != "none",
        setup_recommendations=setup_recs
    )
