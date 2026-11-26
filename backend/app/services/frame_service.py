import csv
import json
import math
import shutil
from pathlib import Path
from typing import List, Dict, Any
import cv2
from app.core.presets import get_preset
import numpy as np

from app.schemas.pipeline import PipelineConfigRequest


class FrameService:
    @staticmethod
    def calculate_sharpness(image_gray: np.ndarray) -> float:
        """Calculates Laplacian variance as a sharpness metric."""
        return float(cv2.Laplacian(image_gray, cv2.CV_64F).var())

    @staticmethod
    def calculate_brightness(image_gray: np.ndarray) -> float:
        """Calculates average brightness (0-255)."""
        return float(np.mean(image_gray))

    @staticmethod
    def compute_histogram(image_bgr: np.ndarray) -> np.ndarray:
        """Computes normalized color histogram for similarity comparison."""
        hist = cv2.calcHist([image_bgr], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
        return cv2.normalize(hist, hist).flatten()

    @staticmethod
    def compute_spatial_similarity(img1_gray: np.ndarray, img2_gray: np.ndarray) -> float:
        """
        Zero-mean normalized cross-correlation (-1..1) between two downsampled grayscale
        images, used to detect a stationary camera.

        NOTE: this deliberately uses TM_CCOEFF_NORMED (mean-subtracted). The previous
        TM_CCORR_NORMED is NOT mean-centred, so any two positive-valued photos score
        ~0.98-0.99 regardless of content. That made the 0.985 "near-duplicate" threshold
        meaningless and could discard frames that had moved a lot.
        """
        s1 = cv2.resize(img1_gray, (160, 90), interpolation=cv2.INTER_AREA)
        s2 = cv2.resize(img2_gray, (160, 90), interpolation=cv2.INTER_AREA)
        score = float(cv2.matchTemplate(s1, s2, cv2.TM_CCOEFF_NORMED)[0][0])
        if not np.isfinite(score):
            # Constant (zero-variance) image(s): correlation is undefined.
            # Identical flat frames are duplicates; otherwise treat as different.
            return 1.0 if np.array_equal(s1, s2) else 0.0
        return score


    @classmethod
    def detect_shots(cls, video_path, video_fps: float, log_callback=None) -> List[Dict[str, Any]]:
        """Split the video into continuous shots. Photogrammetry needs ONE continuous camera path; edited clips
        (cuts between different cameras/positions, fades, repeated shots) mix unrelated viewpoints and produce
        smeared, stacked surfaces. A cut = colour histogram jumps OR consecutive frames no longer share enough
        matching feature points (catches cuts between two similar-looking wide shots)."""
        cap = cv2.VideoCapture(str(video_path))
        step = max(1, int(round(video_fps / 3.0)))               # ~3 samples per second is plenty to see a cut
        orb = cv2.ORB_create(900)
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        samples = []                                              # (frame_idx, hist, kp, des)
        idx = 0
        while True:
            if not cap.grab():
                break
            if idx % step == 0:
                ok, fr = cap.retrieve()
                if ok and fr is not None:
                    k = 480.0 / max(fr.shape[:2])
                    sm = cv2.resize(fr, (int(fr.shape[1] * k), int(fr.shape[0] * k)), interpolation=cv2.INTER_AREA)
                    g = cv2.cvtColor(sm, cv2.COLOR_BGR2GRAY)
                    hsv = cv2.cvtColor(sm, cv2.COLOR_BGR2HSV)
                    h = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256])
                    cv2.normalize(h, h)
                    kp, des = orb.detectAndCompute(g, None)
                    samples.append((idx, h, kp, des))
            idx += 1
        cap.release()
        if len(samples) < 2:
            return [{"start_frame": 0, "end_frame": max(idx - 1, 0), "samples": len(samples)}]
        cuts = []
        for i in range(1, len(samples)):
            _, h0, k0, d0 = samples[i - 1]
            _, h1, k1, d1 = samples[i]
            corr = cv2.compareHist(h0, h1, cv2.HISTCMP_CORREL)
            inl = 0
            if d0 is not None and d1 is not None and len(d0) > 20 and len(d1) > 20:
                m = bf.match(d0, d1)
                if len(m) >= 12:
                    a = np.float32([k0[x.queryIdx].pt for x in m])
                    b = np.float32([k1[x.trainIdx].pt for x in m])
                    F, mask = cv2.findFundamentalMat(a, b, cv2.FM_RANSAC, 2.0, 0.99)
                    inl = int(mask.sum()) if mask is not None else 0
            if corr < 0.55 or inl < 25:
                cuts.append(i)
        shots, start = [], 0
        for c in cuts + [len(samples)]:
            if c - start >= 1:
                shots.append({"start_frame": samples[start][0],
                              "end_frame": (samples[c][0] - 1) if c < len(samples) else idx - 1,
                              "samples": c - start,
                              "start_sec": round(samples[start][0] / video_fps, 1),
                              "end_sec": round(((samples[c][0] if c < len(samples) else idx) - 1) / video_fps, 1)})
            start = c
        if log_callback:
            log_callback(f"Shot analysis: {len(shots)} continuous shot(s) found" +
                         (" - " + ", ".join(f"{s['start_sec']}-{s['end_sec']}s" for s in shots[:12]) if len(shots) > 1 else "."))
        return shots

    @classmethod
    def extract_and_preprocess(
        cls,
        project_dir: Path,
        config: PipelineConfigRequest,
        log_callback=None
    ) -> Dict[str, Any]:
        input_video = project_dir / "input" / "source_video.mp4"
        if not input_video.exists():
            raise FileNotFoundError("Source video file not found in project workspace.")

        frames_dir = project_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        # Clear any prior frames
        for f in frames_dir.glob("frame_*.jpg"):
            f.unlink()

        preset = get_preset(getattr(config, 'quality_preset', None))
        max_frames = min(config.max_frames, preset.max_frames)
        cap = cv2.VideoCapture(str(input_video))
        if not cap.isOpened():
            raise ValueError("Failed to open source video with OpenCV.")

        video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        
        # Determine sampling step
        target_fps = config.sampling_fps
        base_step = max(1, int(round(video_fps / target_fps))) if target_fps > 0 else 1
        # Ensure sampling covers the whole flight timeline if max_frames is constrained
        if total_frames > 0 and max_frames > 0:
            stride_to_cover = max(1, int(math.floor(total_frames / max_frames)))
            step = max(base_step, stride_to_cover)
        else:
            step = base_step

        if (project_dir / "input" / "image_sequence.json").exists():
            step = 1   # imported image folder: every provided frame is already a deliberate view

        if log_callback:
            log_callback(f"Starting frame extraction: Video FPS={video_fps:.2f}, Target FPS={target_fps}, Step={step}, Max={max_frames}")

        # Edited / multi-shot clips: reconstruct from the single longest continuous shot only.
        shots, selected = [], None
        if getattr(config, "auto_shot_select", True) and not (project_dir / "input" / "image_sequence.json").exists():
            try:
                shots = cls.detect_shots(input_video, video_fps, log_callback)
                if len(shots) > 1:
                    best = max(shots, key=lambda s: s["samples"])
                    if best["samples"] >= 8:
                        selected = best
                        if log_callback:
                            log_callback(f"Edited clip with {len(shots)} separate shots: using the longest continuous one "
                                         f"({best['start_sec']}-{best['end_sec']} s, {best['samples']} samples). Other shots are skipped "
                                         "because frames from different shots cannot be solved as one camera path.")
            except Exception as exc:
                if log_callback:
                    log_callback(f"[NOTE] Shot analysis skipped: {exc}")
        range_start = selected["start_frame"] if selected else 0
        range_end = selected["end_frame"] if selected else None
        if range_start:
            for _ in range(range_start):
                if not cap.grab():
                    break
        frame_idx = range_start
        extracted_candidates = 0
        accepted_frames: List[Dict[str, Any]] = []
        all_records: List[Dict[str, Any]] = []

        last_accepted_thumb_gray = None
        contact_sheet_thumbnails = []

        while True:
            # grab() advances the decoder without converting/copying the picture: frames that are
            # not sampled are never needed, so only retrieve() the ones we keep.
            if range_end is not None and frame_idx > range_end:
                break
            if not cap.grab():
                break
            if (frame_idx - range_start) % step == 0:
                ret, frame = cap.retrieve()
                if not ret or frame is None:
                    frame_idx += 1
                    continue
                if preset.frame_dim and max(frame.shape[:2]) > preset.frame_dim:
                    k = preset.frame_dim / float(max(frame.shape[:2]))
                    frame = cv2.resize(frame, (int(round(frame.shape[1] * k)), int(round(frame.shape[0] * k))),
                                       interpolation=cv2.INTER_AREA)
                extracted_candidates += 1
                timestamp_sec = round(frame_idx / video_fps, 3)
                h, w = frame.shape[:2]

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                sharpness = round(cls.calculate_sharpness(gray), 2)
                brightness = round(cls.calculate_brightness(gray), 2)

                # Quality checks
                is_accepted = True
                rejection_reason = "Accepted"

                # Check blur
                blur_floor = 15.0 if (project_dir / "input" / "image_sequence.json").exists() else config.blur_threshold  # curated image sets: only drop truly broken frames
                if sharpness < blur_floor:
                    is_accepted = False
                    rejection_reason = f"Blurry (Laplacian {sharpness} < {blur_floor})"
                # Check darkness
                elif brightness < 25.0:
                    is_accepted = False
                    rejection_reason = f"Too dark (Brightness {brightness} < 25.0)"
                # Check overexposure
                elif brightness > 235.0:
                    is_accepted = False
                    rejection_reason = f"Overexposed (Brightness {brightness} > 235.0)"
                # Check near-duplicate / stationary camera using spatial correlation
                elif last_accepted_thumb_gray is not None:
                    similarity = cls.compute_spatial_similarity(last_accepted_thumb_gray, gray)
                    if similarity > config.similarity_threshold:
                        is_accepted = False
                        rejection_reason = f"Stationary / near-duplicate (Spatial correlation {similarity:.3f} > {config.similarity_threshold})"

                saved_filename = None
                if is_accepted:
                    accepted_seq = len(accepted_frames) + 1
                    saved_filename = f"frame_{accepted_seq:06d}.jpg"
                    frame_path = frames_dir / saved_filename
                    cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 93])

                    last_accepted_thumb_gray = gray

                    # Create thumbnail for contact sheet
                    thumb = cv2.resize(frame, (240, 135))
                    contact_sheet_thumbnails.append(thumb)

                record = {
                    "source_frame_index": frame_idx,
                    "accepted_index": len(accepted_frames) + 1 if is_accepted else None,
                    "filename": saved_filename,
                    "timestamp_sec": timestamp_sec,
                    "width": w,
                    "height": h,
                    "sharpness": sharpness,
                    "brightness": brightness,
                    "accepted": is_accepted,
                    "decision_reason": rejection_reason
                }
                all_records.append(record)
                if is_accepted:
                    accepted_frames.append(record)

                if len(accepted_frames) >= max_frames:
                    if log_callback:
                        log_callback(f"Reached maximum frame limit ({max_frames}). Stopping extraction.")
                    break

            frame_idx += 1

        cap.release()

        # Save manifest JSON
        manifest_json_path = frames_dir / "frame_manifest.json"
        with open(manifest_json_path, "w", encoding="utf-8") as f:
            json.dump({
                "total_video_frames": total_frames,
                "candidates_evaluated": extracted_candidates,
                "accepted_count": len(accepted_frames),
                "rejected_count": extracted_candidates - len(accepted_frames),
                "shots": shots, "selected_shot": selected,
                "records": all_records
            }, f, indent=2)

        # Save manifest CSV
        manifest_csv_path = frames_dir / "frame_manifest.csv"
        with open(manifest_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["source_frame_index", "accepted_index", "filename", "timestamp_sec", "width", "height", "sharpness", "brightness", "accepted", "decision_reason"])
            for r in all_records:
                writer.writerow([
                    r["source_frame_index"], r["accepted_index"], r["filename"],
                    r["timestamp_sec"], r["width"], r["height"],
                    r["sharpness"], r["brightness"], r["accepted"], r["decision_reason"]
                ])

        # Generate contact sheet in frames directory and mirror to outputs
        contact_sheet_path = frames_dir / "contact_sheet.jpg"
        if contact_sheet_thumbnails:
            cls._create_contact_sheet(contact_sheet_thumbnails, contact_sheet_path)
            outputs_dir = project_dir / "outputs"
            outputs_dir.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(contact_sheet_path, outputs_dir / "contact_sheet.jpg")
            except Exception as e:
                if log_callback:
                    log_callback(f"[NOTE] Contact sheet copy to outputs: {e}")

        if len(accepted_frames) < 3:
            raise ValueError(
                f"Only {len(accepted_frames)} frames passed quality filtering out of {extracted_candidates} candidates. "
                "Structure-from-Motion photogrammetry requires at least 3 overlapping frames. "
                "Try lowering the blur threshold or adjusting the sampling rate."
            )

        if log_callback:
            log_callback(f"Preprocessing completed: {len(accepted_frames)} frames accepted ({extracted_candidates - len(accepted_frames)} rejected).")

        return {
            "candidates_evaluated": extracted_candidates,
            "accepted_count": len(accepted_frames),
            "rejected_count": extracted_candidates - len(accepted_frames),
            "manifest_json": str(manifest_json_path),
            "manifest_csv": str(manifest_csv_path),
            "contact_sheet": str(contact_sheet_path) if contact_sheet_thumbnails else None,
            "shots": shots, "selected_shot": selected,
        }

    @classmethod
    def _create_contact_sheet(cls, thumbnails: List[np.ndarray], output_path: Path):
        count = len(thumbnails)
        cols = 5
        rows = math.ceil(count / cols)
        th_h, th_w = thumbnails[0].shape[:2]

        sheet = np.zeros((rows * th_h, cols * th_w, 3), dtype=np.uint8)
        for i, thumb in enumerate(thumbnails):
            r = i // cols
            c = i % cols
            sheet[r * th_h:(r + 1) * th_h, c * th_w:(c + 1) * th_w] = thumb

        cv2.imwrite(str(output_path), sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])
