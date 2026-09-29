"""Environment registry — instantiate evaluation environments by name.

Environments register themselves through the ``sunimuhendis.environments``
entry-point group. A package that provides one declares, in its
``pyproject.toml``::

    [project.entry-points."sunimuhendis.environments"]
    heat_exchanger = "sunimuhendis.environments.heat_exchanger:make_env"

and ``make_env("heat_exchanger")`` finds it once that package is installed.
The core never imports an environment by name, which is what lets every
environment live in a package of its own.

Each factory imports its (possibly heavy) simulator dependencies *lazily*, so
``import sunimuhendis`` and ``list_environments()`` stay dependency-free.

The heat exchanger still ships inside this package, so it is also known here
as a built-in: that keeps it available when the package is imported from a
source tree without being installed. An installed entry point of the same
name takes precedence.
"""
from importlib.metadata import EntryPoint, entry_points
from typing import Any, Callable, Dict, List

from ..core.base_environment import BaseEnvironment

ENTRY_POINT_GROUP = "sunimuhendis.environments"


def _make_heat_exchanger(**kwargs: Any) -> BaseEnvironment:
    from .heat_exchanger import make_env as factory
    return factory(**kwargs)


_BUILTIN: Dict[str, Callable[..., BaseEnvironment]] = {
    "heat_exchanger": _make_heat_exchanger,
}


def _registered() -> Dict[str, EntryPoint]:
    """Installed environment entry points by name.

    Two packages claiming the same name is an error rather than a silent
    choice: which environment scored a design must never depend on install
    order.
    """
    found: Dict[str, EntryPoint] = {}
    for entry in entry_points(group=ENTRY_POINT_GROUP):
        other = found.get(entry.name)
        if other is not None and other.value != entry.value:
            raise RuntimeError(
                "Environment {!r} is registered twice: {} and {}".format(
                    entry.name, other.value, entry.value))
        found[entry.name] = entry
    return found


def list_environments() -> List[str]:
    """Return the names of all available environments."""
    return sorted(set(_BUILTIN) | set(_registered()))


def make_env(name: str, **kwargs: Any) -> BaseEnvironment:
    """Instantiate an environment by name.

    Raises KeyError if no installed package provides the name, listing the
    available options.
    """
    registered = _registered()
    if name in registered:
        factory = registered[name].load()
    elif name in _BUILTIN:
        factory = _BUILTIN[name]
    else:
        raise KeyError(
            "Unknown environment {!r}. Available: {}. An environment becomes "
            "available when the package that provides it is installed.".format(
                name, list_environments())
        ) from None
    env = factory(**kwargs)
    if not isinstance(env, BaseEnvironment):
        raise TypeError("Environment factory for {!r} returned {!r}, not a BaseEnvironment".format(
            name, type(env).__name__))
    return env
