# Development and release workflow

## Runtime

The supported interpreter is CPython 3.12; `.python-version` pins the
development patch release. The project declares `>=3.12,<3.13`. The
evaluation environments (`sm-core`, `sm-heat-exchanger`) are installed from the
tags pinned in `pyproject.toml`.

Create and install the development environment on Linux or macOS:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -c constraints/python312.txt -r requirements.txt -e .
```

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
. .venv\Scripts\Activate.ps1
python -m pip install -c constraints\python312.txt -r requirements.txt -e .
```

`constraints/python312.txt` pins the validated direct development profile. It
is not a cross-platform, hash-locked dependency file.

## Verification

```bash
python -m pip check
python -m pytest tests/ -q
```

GitHub Actions runs the same checks on Windows and Ubuntu. The environments
carry their own physics tests and wheel checks in their repositories.

## Useful entry points

| Command | Purpose |
|---|---|
| `python scripts/run_simulation.py` | Exercise every pipeline failure stage |
| `python scripts/run_baseline.py` | Generate and evaluate non-model baselines |
| `python scripts/calibrate_hard_task.py` | Audit a task's feasible design space |
| `python scripts/token_report.py` | Report token use and spend |

## Documentation site

The site at <https://suni-muhendis.github.io/sm-bench/> is built from `docs/`
with MkDocs Material and deployed by the `docs` workflow on every push to
`main`. Only pages listed in the `nav` of `mkdocs.yml` are published. The
leaderboard is computed from `results/` at build time, so new benchmark runs
appear after the next push.

To preview it locally, install the pinned site dependencies in a separate
environment and run:

```bash
python -m pip install -r requirements-docs.txt
python scripts/build_site_data.py
python -m mkdocs serve
```

## Updating an environment

An environment change is released in its own repository with a new tag. To
use it here:

1. Bump the tag in `pyproject.toml` and reinstall.
2. Re-score the recorded runs with the new version and check that every number
   that should not move did not move.
3. Update `CHANGELOG.md`, `pyproject.toml`, `CITATION.cff`, and public docs.
4. Confirm Windows and Ubuntu CI on the exact commit, then tag SM-Bench
   (`vX.Y.Z`).

New simulator or score behavior requires a new version boundary. Historical
result files are never rewritten to look as though they were produced by a
newer referee.
