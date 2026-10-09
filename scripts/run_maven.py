"""Run the Maven Wrapper of core-api with the given goals (used by the pre-commit hooks).

Usage:  python scripts/run_maven.py <goal>...

The wrapper is a shell script on Linux and macOS and a .cmd file on Windows, and pre-commit cannot
launch the shell script on Windows (there, "bash" is usually WSL and "sh" is not on the PATH).
"""

import os
import subprocess
import sys
from pathlib import Path

CORE_API = Path(__file__).resolve().parents[1] / "core-api"


def main(goals: list[str]) -> int:
    wrapper = CORE_API / ("mvnw.cmd" if os.name == "nt" else "mvnw")
    command = [str(wrapper), "--batch-mode", "--no-transfer-progress", "--quiet", *goals]
    # Fixed command: the goals come from .pre-commit-config.yaml.
    return subprocess.run(command, cwd=CORE_API, check=False).returncode  # noqa: S603


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
