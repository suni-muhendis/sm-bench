"""Validate the public wheel boundary and Python runtime contract."""
import argparse
from email.parser import BytesParser
from pathlib import Path
import tomllib
from zipfile import ZipFile


EXPECTED_REQUIRES_PYTHON = ">=3.12,<3.13"
ROOT = Path(__file__).resolve().parents[1]


def _specifier_parts(value):
    return frozenset(part.strip() for part in value.split(",") if part.strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel_or_directory", type=Path)
    args = parser.parse_args()

    candidate = args.wheel_or_directory
    wheels = sorted(candidate.glob("*.whl")) if candidate.is_dir() else [candidate]
    if len(wheels) != 1:
        raise RuntimeError("Expected exactly one wheel, found {}".format(len(wheels)))

    wheel = wheels[0]
    expected_version = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    with ZipFile(wheel) as archive:
        files = archive.namelist()
        metadata_files = [name for name in files if name.endswith(".dist-info/METADATA")]
        if len(metadata_files) != 1:
            raise RuntimeError("Expected exactly one METADATA file")
        metadata = BytesParser().parsebytes(archive.read(metadata_files[0]))

    if _specifier_parts(metadata["Requires-Python"]) != _specifier_parts(EXPECTED_REQUIRES_PYTHON):
        raise RuntimeError("Unexpected Requires-Python: {}".format(metadata["Requires-Python"]))
    if metadata["Version"] != expected_version:
        raise RuntimeError("Unexpected wheel version: {}".format(metadata["Version"]))
    if not any(name.startswith("sunimuhendis/prompts/") for name in files):
        raise RuntimeError("Public prompt package is missing")
    forbidden = ("sunimuhendis/model_clients/", "sunimuhendis/baselines/")
    leaked = [name for name in files if name.startswith(forbidden)]
    if leaked:
        raise RuntimeError("Wheel contains excluded packages: {}".format(leaked))

    print("Validated {}: Requires-Python={}, {} files".format(
        wheel.name, metadata["Requires-Python"], len(files)))


if __name__ == "__main__":
    main()
