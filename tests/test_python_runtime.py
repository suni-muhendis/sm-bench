import sys
import tomllib
from pathlib import Path

from sm_bench import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_test_suite_runs_on_supported_python_minor():
    assert sys.version_info[:2] == (3, 12)


def test_python_version_contract_is_consistent():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert project["requires-python"] == ">=3.12,<3.13"
    assert (ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.12.10"
    assert "Programming Language :: Python :: 3.12" in project["classifiers"]
    assert not any(
        classifier.startswith("Programming Language :: Python :: 3.")
        and classifier != "Programming Language :: Python :: 3.12"
        for classifier in project["classifiers"]
    )


def test_public_version_is_consistent():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")

    assert project["version"] == __version__
    assert "version: {}".format(__version__) in citation
