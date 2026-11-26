"""Download the Depth Anything V2 (small) ONNX weights used by the optional AI-depth stage.

Run once on a machine with internet access:   python tools/download_depth_model.py
Saves to bin/models/depth_anything_v2/model.onnx (about 100 MB). Tensor names are detected automatically by the app.
"""
import sys
import urllib.request
from pathlib import Path

URL = "https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model.onnx"
DEST = Path(__file__).resolve().parents[1] / "bin" / "models" / "depth_anything_v2" / "model.onnx"


def main() -> int:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists() and DEST.stat().st_size > 10_000_000:
        print(f"Already present: {DEST} ({DEST.stat().st_size / 1e6:.0f} MB)")
        return 0
    print(f"Downloading {URL}\n  -> {DEST}")
    tmp = DEST.with_suffix(".part")
    with urllib.request.urlopen(URL) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done / 1e6:.0f}/{total / 1e6:.0f} MB", end="", flush=True)
    if tmp.stat().st_size < 10_000_000:
        tmp.unlink()
        print("\nDownload looks incomplete.")
        return 1
    tmp.replace(DEST)
    print(f"\nDone: {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
