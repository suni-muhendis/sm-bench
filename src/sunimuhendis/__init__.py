"""sunimuhendis — SM-Bench physics-simulation evaluation environments.

Public API for consumers (e.g. a training repo) that only need the
"referee" (DRC + simulator + score) for one or more environments:

    from sunimuhendis import make_env, list_environments

    env = make_env("heat_exchanger")
    result = env.evaluate(task_id, task_params, design_id, design)
    reward = result.score.normalized_total
"""
from .environments import make_env, list_environments

__version__ = "0.7.0"
__all__ = ["make_env", "list_environments", "__version__"]
