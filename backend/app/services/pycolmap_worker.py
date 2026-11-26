"""Child-process entry point for PyColmapEngine (see pycolmap_engine._run_isolated)."""
import json
import sys
from pathlib import Path

from app.services import pycolmap_engine as eng


def main() -> int:
    step, project_dir, args = sys.argv[1], Path(sys.argv[2]), json.loads(sys.argv[3])
    cls = eng.PyColmapEngine
    if step == "extract":
        res = cls._extract(project_dir, args["preset"], args["use_gpu"])
    elif step == "match":
        res = cls._match(project_dir, args["strategy"], args["use_gpu"])
    elif step == "map":
        res = {"models": [str(p) for p in cls._map(project_dir, Path(args["sparse_dir"]))]}
    else:
        print(f"unknown step {step}", file=sys.stderr)
        return 2
    print("RESULT " + json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
