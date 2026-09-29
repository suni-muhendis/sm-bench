"""Install a wheel in a clean venv and exercise the public environment API."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _venv_python(directory):
    if os.name == "nt":
        return directory / "Scripts" / "python.exe"
    return directory / "bin" / "python"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel_or_directory", type=Path)
    parser.add_argument(
        "--constraint",
        type=Path,
        default=ROOT / "constraints" / "python312.txt",
    )
    args = parser.parse_args()

    candidate = args.wheel_or_directory
    wheels = sorted(candidate.glob("*.whl")) if candidate.is_dir() else [candidate]
    if len(wheels) != 1:
        raise RuntimeError("Expected exactly one wheel, found {}".format(len(wheels)))
    wheel = wheels[0].resolve()
    constraint = args.constraint.resolve()

    task = json.loads((ROOT / "configs/tasks/heat_exchanger/task_001.json").read_text(encoding="utf-8"))
    design = json.loads((ROOT / "examples/designs/heat_exchanger_valid_001.json").read_text(encoding="utf-8"))
    payload = json.dumps({"task": task, "design": design})
    code = """import json, sys
from pathlib import Path
import sunimuhendis
from sunimuhendis import make_env

payload = json.loads(sys.stdin.read())
result = make_env("heat_exchanger").evaluate(
    "wheel-smoke", payload["task"], "sample", payload["design"]
)
assert result.status == "success", result
assert result.environment == "heat_exchanger", result.environment
from importlib.metadata import entry_points
assert "heat_exchanger" in {e.name for e in entry_points(group="sunimuhendis.environments")}
import_path = Path(sunimuhendis.__file__).resolve()
environment_root = Path(sys.prefix).resolve()
assert import_path.is_relative_to(environment_root), (
    "Import did not come from the clean consumer venv: "
    + str(import_path)
    + " is outside "
    + str(environment_root)
)
print(json.dumps({
    "import_path": str(import_path),
    "environment_root": str(environment_root),
    "status": result.status,
    "score": result.score.normalized_total,
}))
"""

    with tempfile.TemporaryDirectory(prefix="sunimuhendis-wheel-") as temp:
        environment = Path(temp) / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = _venv_python(environment)
        requirement = "sunimuhendis[heat_exchanger] @ " + wheel.as_uri()
        subprocess.run(
            [str(python), "-m", "pip", "install", "-c", str(constraint), requirement],
            check=True,
            timeout=300,
        )
        smoke_cwd = Path(temp) / "outside-repository"
        smoke_cwd.mkdir()
        try:
            completed = subprocess.run(
                [str(python), "-I", "-c", code],
                input=payload,
                capture_output=True,
                text=True,
                cwd=smoke_cwd,
                timeout=60,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            if exc.stdout:
                print(exc.stdout, end="")
            if exc.stderr:
                print(exc.stderr, end="", file=sys.stderr)
            raise
        result = json.loads(completed.stdout)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
