import shutil
import json
import subprocess
from pathlib import Path
import cv2

from app.config import settings
from app.schemas.project import VideoMetadata


class VideoService:
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        keepcharacters = (' ', '.', '_', '-')
        cleaned = "".join(c for c in filename if c.isalnum() or c in keepcharacters).rstrip()
        return cleaned if cleaned else "video.mp4"

    @classmethod
    def get_project_dir(cls, project_id: str) -> Path:
        # Enforce path containment inside workspace
        project_dir = (settings.BIRDS_EYE_WORKSPACE / project_id).resolve()
        if not str(project_dir).startswith(str(settings.BIRDS_EYE_WORKSPACE.resolve())):
            raise ValueError("Unsafe project path detected")
        return project_dir

    @classmethod
    def inspect_and_save(cls, project_id: str, uploaded_file_path: Path, original_filename: str) -> VideoMetadata:
        project_dir = cls.get_project_dir(project_id)
        input_dir = project_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=True)

        target_file = input_dir / "source_video.mp4"
        shutil.copy2(uploaded_file_path, target_file)

        size_bytes = target_file.stat().st_size
        if size_bytes == 0:
            target_file.unlink(missing_ok=True)
            raise ValueError("Uploaded video file is empty (0 bytes).")

        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if size_bytes > max_bytes:
            target_file.unlink(missing_ok=True)
            raise ValueError(f"Uploaded file exceeds maximum limit of {settings.MAX_UPLOAD_SIZE_MB} MB.")

        # OpenCV decodability validation
        cap = cv2.VideoCapture(str(target_file))
        if not cap.isOpened():
            target_file.unlink(missing_ok=True)
            raise ValueError("OpenCV could not open or decode the video file. Ensure valid MP4/MOV format.")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)]).strip()

        # Read first frame to ensure actual frames can be decoded
        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None or width == 0 or height == 0:
            target_file.unlink(missing_ok=True)
            raise ValueError("Video header opened, but frames could not be decoded. Corrupted stream.")

        duration_sec = round(frame_count / fps, 2) if (fps > 0 and frame_count > 0) else 0.0

        warnings = []
        if duration_sec > settings.MAX_VIDEO_DURATION_SEC:
            warnings.append(f"Video duration ({duration_sec}s) exceeds recommended limit of {settings.MAX_VIDEO_DURATION_SEC}s.")
        if duration_sec < 2.0:
            warnings.append("Video duration is under 2 seconds; SfM may fail due to insufficient camera motion.")
        if width < 640 or height < 480:
            warnings.append("Low video resolution may degrade 3D feature matching precision.")
        if fps < 10.0:
            warnings.append("Video frame rate is low (<10 FPS); frame overlap may be poor.")

        aspect_ratio = f"{width}:{height}"
        if height > 0:
            gcd = 1
            for i in range(1, min(width, height) + 1):
                if width % i == 0 and height % i == 0:
                    gcd = i
            aspect_ratio = f"{width // gcd}:{height // gcd}"

        # Probe for GPS metadata using FFmpeg if available
        has_gps = False
        lat, lon, alt = None, None, None
        ffmpeg_exe = settings.FFMPEG_EXE
        if ffmpeg_exe and Path(ffmpeg_exe).exists():
            ffprobe_exe = Path(ffmpeg_exe).parent / "ffprobe.exe"
            if ffprobe_exe.exists():
                try:
                    cmd = [
                        str(ffprobe_exe),
                        "-v", "quiet",
                        "-print_format", "json",
                        "-show_format",
                        "-show_streams",
                        str(target_file)
                    ]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                    if res.returncode == 0:
                        probe_data = json.loads(res.stdout)
                        tags = probe_data.get("format", {}).get("tags", {})
                        if "location" in tags:
                            tags["location"]
                            has_gps = True
                except Exception:
                    pass

        metadata = VideoMetadata(
            filename="source_video.mp4",
            original_filename=cls.sanitize_filename(original_filename),
            size_bytes=size_bytes,
            duration_seconds=duration_sec,
            fps=round(fps, 2),
            frame_count=frame_count,
            width=width,
            height=height,
            codec=codec if codec else "H264",
            aspect_ratio=aspect_ratio,
            has_audio=False,
            has_gps=has_gps,
            gps_latitude=lat,
            gps_longitude=lon,
            gps_altitude=alt,
            warnings=warnings
        )

        # Save metadata JSON into project dir
        meta_file = input_dir / "video_metadata.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            f.write(metadata.model_dump_json(indent=2))

        return metadata
