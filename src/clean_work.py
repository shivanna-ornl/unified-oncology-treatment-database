from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    work = args.repo.resolve() / "work"
    for name in ("standardized", "provisional"):
        target = work / name
        if target.exists() and target.is_dir():
            shutil.rmtree(target)
    for name in ("treatment_validation.sqlite", "treatment_validation.sqlite-shm", "treatment_validation.sqlite-wal"):
        (work / name).unlink(missing_ok=True)


if __name__ == "__main__":
    main()

