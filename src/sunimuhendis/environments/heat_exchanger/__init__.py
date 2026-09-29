"""Heat exchanger evaluation environment."""


def make_env(**kwargs):
    """Build the heat-exchanger environment; registered as ``heat_exchanger``.

    ``score_version`` sets the default score; a task that names its own
    ``score_version`` is scored with that one instead. The imports are lazy so
    that discovering the environment does not import its physics libraries.
    """
    from .env import HeatExchangerEnv
    from .score import get_score_function
    from .simulator import HeatExchangerSimulator

    score_version = kwargs.get("score_version", "heat_exchanger_score_v1")
    return HeatExchangerEnv(HeatExchangerSimulator(), get_score_function(score_version))
