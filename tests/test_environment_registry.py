"""The environment registry and the provenance stamped on every result.

Environments are found through the ``sunimuhendis.environments`` entry-point
group, which is what lets an environment live in a package of its own. These
tests pin that discovery, the errors around it, and that every result names
the environment and the simulator and score versions that produced it.
"""
from importlib.metadata import EntryPoint

import pytest

import sunimuhendis.environments.registry as registry
from sunimuhendis import list_environments, make_env
from sunimuhendis.environments.heat_exchanger.env import HeatExchangerEnv
from sunimuhendis.environments.heat_exchanger.score import SCORE_REGISTRY

_HE_TARGET = "sunimuhendis.environments.heat_exchanger:make_env"


def _entry(name, value):
    return EntryPoint(name=name, value=value, group=registry.ENTRY_POINT_GROUP)


def _install(monkeypatch, *entries):
    """Make the registry see exactly these installed entry points."""
    monkeypatch.setattr(registry, "entry_points", lambda group: [e for e in entries if e.group == group])


def test_the_heat_exchanger_is_installed_as_an_entry_point():
    # Read from the installed distribution metadata: this fails if the
    # package was not (re)installed after pyproject.toml changed.
    assert registry._registered()["heat_exchanger"].value == _HE_TARGET


def test_make_env_builds_the_named_environment():
    env = make_env("heat_exchanger")
    assert isinstance(env, HeatExchangerEnv)
    assert env.name == "heat_exchanger"
    assert "heat_exchanger" in list_environments()


def test_the_built_in_heat_exchanger_works_without_installed_metadata(monkeypatch):
    _install(monkeypatch)
    assert list_environments() == ["heat_exchanger"]
    assert isinstance(make_env("heat_exchanger"), HeatExchangerEnv)


def test_an_installed_entry_point_is_discovered(monkeypatch):
    _install(monkeypatch,
             _entry("heat_exchanger", _HE_TARGET),
             _entry("other_heat_exchanger", _HE_TARGET))
    assert list_environments() == ["heat_exchanger", "other_heat_exchanger"]
    assert isinstance(make_env("other_heat_exchanger"), HeatExchangerEnv)


def test_an_entry_point_takes_precedence_over_the_built_in(monkeypatch):
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        return HeatExchangerEnv.__new__(HeatExchangerEnv)

    monkeypatch.setattr(EntryPoint, "load", lambda self: factory)
    _install(monkeypatch, _entry("heat_exchanger", "elsewhere:make_env"))
    make_env("heat_exchanger", score_version="heat_exchanger_score_v4")
    assert calls == [{"score_version": "heat_exchanger_score_v4"}]


def test_two_packages_claiming_one_name_is_an_error(monkeypatch):
    _install(monkeypatch,
             _entry("heat_exchanger", _HE_TARGET),
             _entry("heat_exchanger", "someone_else:make_env"))
    with pytest.raises(RuntimeError, match="registered twice"):
        make_env("heat_exchanger")


def test_the_same_entry_point_seen_twice_is_not_an_error(monkeypatch):
    # Editable installs can expose one distribution's metadata twice.
    _install(monkeypatch, _entry("heat_exchanger", _HE_TARGET), _entry("heat_exchanger", _HE_TARGET))
    assert isinstance(make_env("heat_exchanger"), HeatExchangerEnv)


def test_an_unknown_environment_says_what_is_available(monkeypatch):
    _install(monkeypatch)
    with pytest.raises(KeyError, match="Unknown environment 'rotor'.*heat_exchanger.*installed"):
        make_env("rotor")


def test_a_factory_must_return_an_environment(monkeypatch):
    monkeypatch.setattr(EntryPoint, "load", lambda self: (lambda **kwargs: object()))
    _install(monkeypatch, _entry("broken", "broken:make_env"))
    with pytest.raises(TypeError, match="broken"):
        make_env("broken")


def test_score_versions_are_named_by_their_registry_key():
    for key, score_class in SCORE_REGISTRY.items():
        assert score_class.VERSION == key


_TASK = {"target_heat_duty": 150000.0, "max_dp_tube": 50000.0, "max_dp_shell": 50000.0}
_DESIGN = {
    "geometry_type": "shell_and_tube", "length": 3.0, "inner_tube_di": 0.016,
    "inner_tube_do": 0.019, "outer_shell_di": 0.35, "number_of_tubes": 60,
    "baffle_spacing": 0.3,
}


@pytest.mark.parametrize("design, status", [
    (_DESIGN, "success"),
    ({"geometry_type": "shell_and_tube"}, "schema_error"),
])
def test_every_result_is_stamped_whatever_stage_it_stopped_at(design, status):
    result = make_env("heat_exchanger").evaluate("t", _TASK, "d", design)
    assert result.status == status
    assert result.environment == "heat_exchanger"
    assert result.simulator_version == "v4"
    assert result.score_version == "heat_exchanger_score_v1"


def test_the_stamped_score_version_is_the_one_the_task_names():
    task = dict(_TASK, score_version="heat_exchanger_score_v3")
    result = make_env("heat_exchanger").evaluate("t", task, "d", _DESIGN)
    assert result.score_version == "heat_exchanger_score_v3"
