# Third-party software and research provenance

This document separates SM-Bench-owned code and data from third-party
software, model output, and research inputs. It is an engineering provenance
record, not a replacement for the license terms supplied by each upstream
project.

## Software dependencies

SM-Bench is an application, not a distributed package. It installs the
project's own evaluation packages, `sm-core` and `sm-heat-exchanger`
(Apache-2.0), from their release tags; their third-party dependencies
(`pydantic`, `json-repair`, `ht`, `fluids`, `scipy`) are documented in
their own repositories. The benchmark application uses further dependencies
listed in `pyproject.toml` and `requirements.txt`. The authoritative license
for each dependency is the license included with its installed distribution
or upstream source.

Releases up to `envs-v0.7.0` shipped the `sunimuhendis` wheel from this
repository, containing project-authored modules only.

## Third-party model responses

Benchmark JSONL records can contain raw responses produced by external models.
SM-Bench does not claim authorship of that text. The scope and reuse limits
are described in [the benchmark-data license](results/LICENSE.md). Users must
check the originating model and provider terms before reusing raw responses.

## No endorsement

Names of third-party projects identify provenance only. They do not
imply endorsement of SM-Bench, its simulations, benchmark results, or
derived research conclusions.
