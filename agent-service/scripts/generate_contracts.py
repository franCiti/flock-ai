"""Generate the Pydantic models of the public contract from contracts/schemas.

Usage (from agent-service/):  uv run python scripts/generate_contracts.py [output_dir]

The generated package is committed. A test regenerates it into a temporary directory and fails if
the committed code is out of date, so a contract change cannot go unnoticed.
"""

import subprocess
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_DIR = SERVICE_ROOT.parent / "contracts" / "schemas"
DEFAULT_OUTPUT_DIR = SERVICE_ROOT / "src" / "flock_agent" / "contracts" / "generated"

CODEGEN_OPTIONS = [
    "--input-file-type",
    "jsonschema",
    "--output-model-type",
    "pydantic_v2.BaseModel",
    "--target-python-version",
    "3.12",
    "--snake-case-field",
    "--allow-population-by-field-name",
    "--use-annotated",
    "--field-constraints",
    "--use-standard-collections",
    "--use-union-operator",
    "--use-title-as-name",
    "--collapse-root-models",
    "--enum-field-as-literal",
    "all",
    "--output-datetime-class",
    "AwareDatetime",
    "--use-double-quotes",
    "--disable-timestamp",
    # Only the formatter: the code generator runs ruff-check before formatting, so long lines
    # would always fail. The project's own Ruff runs afterwards (see generate()).
    "--formatters",
    "ruff-format",
]


def generate(output_dir: Path) -> None:
    command = [
        sys.executable,
        "-m",
        "datamodel_code_generator",
        "--input",
        str(SCHEMAS_DIR),
        "--output",
        str(output_dir),
        *CODEGEN_OPTIONS,
    ]
    # Fixed commands without user input.
    subprocess.run(command, check=True, cwd=SERVICE_ROOT)  # noqa: S603
    # Explicit config so the output is identical wherever it is generated (the up-to-date test
    # generates into a temporary directory). E501: schema descriptions the formatter cannot wrap.
    ruff = [sys.executable, "-m", "ruff"]
    config = ["--config", str(SERVICE_ROOT / "pyproject.toml")]
    check = [*ruff, "check", *config, "--extend-ignore", "E501", "--fix", "--quiet"]
    subprocess.run([*check, str(output_dir)], check=True)  # noqa: S603
    subprocess.run([*ruff, "format", *config, "--quiet", str(output_dir)], check=True)  # noqa: S603


if __name__ == "__main__":
    generate(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT_DIR)
