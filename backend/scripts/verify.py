"""Run the standard backend verification flow."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _run(command: list[str]) -> None:
    print(f"$ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    pyright = shutil.which("pyright")
    if pyright is None:
        raise SystemExit("pyright is not installed in the current environment.")

    _run([sys.executable, "scripts/check_boundaries.py"])
    _run([pyright])
    _run([sys.executable, "-m", "pytest"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
