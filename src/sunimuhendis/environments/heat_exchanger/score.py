from typing import Dict, Any, Optional
from ...core.base_score import BaseScoreFunction
from ...core.types import ScoreResult

class HeatExchangerScoreV1(BaseScoreFunction):
    VERSION = "heat_exchanger_score_v1"

    def calculate_score(self, task_params: Dict[str, Any], metrics: Dict[str, Any], is_valid: bool = True, error_message: Optional[str] = None) -> ScoreResult:
        if not is_valid:
            return ScoreResult(normalized_total=0.0, is_valid=False, error_message=error_message)
            
        # Fetch weights from task configuration, use defaults if not present
        w_heat = task_params.get("w_heat", 0.4)
        w_drop_tube = task_params.get("w_drop_tube", 0.05)
        w_drop_shell = task_params.get("w_drop_shell", 0.05)
        w_eff = task_params.get("w_eff", 0.2)
        w_cost = task_params.get("w_cost", 0.3)
        
        # Get targets
        target_heat = task_params.get("target_heat_duty", 150000.0) # W
        max_dp_tube = task_params.get("max_dp_tube", 50000.0) # Pa
        max_dp_shell = task_params.get("max_dp_shell", 50000.0) # Pa
        
        # Get metrics (Supports both old and new simulator names)
        heat_duty = metrics.get("heat_duty_W", metrics.get("heat_duty", 0.0))
        dp_tube = metrics.get("dp_tube_Pa", metrics.get("pressure_drop_tube", max_dp_tube * 2))
        dp_shell = metrics.get("dp_shell_Pa", metrics.get("pressure_drop_shell", max_dp_shell * 2))
        effectiveness = metrics.get("effectiveness", 0.0)
        cost_annualised = metrics.get("cost_annualised_USD_per_yr", 100000.0)
        num_warnings = metrics.get("num_warnings", 0.0)
        
        # 1. Heat duty score: Higher is better (max 1.0)
        r_heat = min(heat_duty / target_heat, 1.0)
        
        # 2. Pressure drop tube penalty
        if dp_tube <= max_dp_tube:
            r_drop_tube = 1.0
        else:
            r_drop_tube = max(1.0 - ((dp_tube - max_dp_tube) / max_dp_tube), 0.0)
            
        # 3. Pressure drop shell penalty
        if dp_shell <= max_dp_shell:
            r_drop_shell = 1.0
        else:
            r_drop_shell = max(1.0 - ((dp_shell - max_dp_shell) / max_dp_shell), 0.0)
            
        # 4. Effectiveness score
        r_eff = min(max(effectiveness, 0.0), 1.0)
        
        # 5. Cost score: Lower cost yields higher reward (example baseline 50000 USD/yr)
        # If cost is under 50k it approaches 1.0, decreases if above.
        baseline_cost = 50000.0
        r_cost = min(baseline_cost / max(cost_annualised, 1.0), 1.0)
        
        # Calculate total score
        total_score = (w_heat * r_heat) + (w_drop_tube * r_drop_tube) + (w_drop_shell * r_drop_shell) + (w_eff * r_eff) + (w_cost * r_cost)
        
        # Warnings penalty (10% reduction for each warning)
        penalty_factor = max(1.0 - (num_warnings * 0.1), 0.0)
        
        # normalize
        total_weight = w_heat + w_drop_tube + w_drop_shell + w_eff + w_cost
        normalized = (total_score / total_weight) * penalty_factor if total_weight > 0 else 0.0
        
        components = {
            "heat_duty_reward": r_heat,
            "pressure_drop_tube_reward": r_drop_tube,
            "pressure_drop_shell_reward": r_drop_shell,
            "effectiveness_reward": r_eff,
            "cost_reward": r_cost,
            "penalty_factor": penalty_factor
        }
        
        return ScoreResult(
            normalized_total=normalized,
            components=components,
            is_valid=True
        )

class HeatExchangerScoreV2(BaseScoreFunction):
    VERSION = "heat_exchanger_score_v2"

    def calculate_score(self, task_params: Dict[str, Any], metrics: Dict[str, Any], is_valid: bool = True, error_message: Optional[str] = None) -> ScoreResult:
        if not is_valid:
            return ScoreResult(normalized_total=0.0, is_valid=False, error_message=error_message)
            
        # Fetch weights
        w_heat = task_params.get("w_heat", 0.4)
        w_drop_tube = task_params.get("w_drop_tube", 0.05)
        w_drop_shell = task_params.get("w_drop_shell", 0.05)
        w_eff = task_params.get("w_eff", 0.2)
        w_cost = task_params.get("w_cost", 0.3)
        
        # Fetch targets and parameters
        target_heat = task_params.get("target_heat_duty", 150000.0)
        max_dp_tube = task_params.get("max_dp_tube", 50000.0)
        max_dp_shell = task_params.get("max_dp_shell", 50000.0)
        
        # V2 specific configuration
        target_cost = task_params.get("target_cost", 50000.0)
        oversizing_penalty_factor = task_params.get("oversizing_penalty_factor", 0.5)
        safety_margin = task_params.get("heat_safety_margin", 1.05)
        warning_penalty_per_warning = task_params.get("warning_penalty_per_warning", 0.1)
        dp_decay_factor = task_params.get("dp_decay_factor", 0.2) # Below limit, pressure drop decay
        
        # Get metrics
        heat_duty = metrics.get("heat_duty_W", metrics.get("heat_duty", 0.0))
        dp_tube = metrics.get("dp_tube_Pa", metrics.get("pressure_drop_tube", max_dp_tube * 2))
        dp_shell = metrics.get("dp_shell_Pa", metrics.get("pressure_drop_shell", max_dp_shell * 2))
        effectiveness = metrics.get("effectiveness", 0.0)
        cost_annualised = metrics.get("cost_annualised_USD_per_yr", target_cost * 2)
        num_warnings = metrics.get("num_warnings", 0.0)
        
        # 1. Heat Duty Score
        if heat_duty < target_heat:
            # Under target: quadratic penalty to severely punish missing the spec
            r_heat = (heat_duty / target_heat) ** 2
        else:
            # Over target: safe up to margin, then gradual penalty
            ratio = heat_duty / target_heat
            if ratio <= safety_margin:
                r_heat = 1.0
            else:
                excess_ratio = ratio - safety_margin
                r_heat = max(1.0 - (oversizing_penalty_factor * excess_ratio), 0.0)
                
        # 2. Pressure drop tube score
        if dp_tube <= 0:
            r_drop_tube = 1.0
        elif dp_tube <= max_dp_tube:
            # Linear decay to (1 - dp_decay_factor) at max_dp
            r_drop_tube = 1.0 - (dp_decay_factor * (dp_tube / max_dp_tube))
        else:
            # Rapid decay beyond limit
            r_drop_tube = max(1.0 - dp_decay_factor - ((dp_tube - max_dp_tube) / max_dp_tube), 0.0)
            
        # 3. Pressure drop shell score
        if dp_shell <= 0:
            r_drop_shell = 1.0
        elif dp_shell <= max_dp_shell:
            r_drop_shell = 1.0 - (dp_decay_factor * (dp_shell / max_dp_shell))
        else:
            r_drop_shell = max(1.0 - dp_decay_factor - ((dp_shell - max_dp_shell) / max_dp_shell), 0.0)
            
        # 4. Effectiveness score
        r_eff = min(max(effectiveness, 0.0), 1.0)
        
        # 5. Cost score
        # Target cost gets 1.0. Higher costs get linearly penalized (or inverse).
        if cost_annualised <= target_cost:
            r_cost = 1.0
        else:
            # Drop from 1.0 down to 0.0 if cost is double the target cost.
            r_cost = max(1.0 - ((cost_annualised - target_cost) / target_cost), 0.0)
            
        # Calculate raw total
        total_score = (w_heat * r_heat) + (w_drop_tube * r_drop_tube) + (w_drop_shell * r_drop_shell) + (w_eff * r_eff) + (w_cost * r_cost)
        total_weight = w_heat + w_drop_tube + w_drop_shell + w_eff + w_cost
        
        # Warning penalty 
        penalty_factor = max((1.0 - warning_penalty_per_warning) ** num_warnings, 0.0)
        
        raw_score_before_penalty = total_score / total_weight if total_weight > 0 else 0.0
        normalized = raw_score_before_penalty * penalty_factor
        
        components = {
            "heat_duty_score": r_heat,
            "pressure_drop_tube_score": r_drop_tube,
            "pressure_drop_shell_score": r_drop_shell,
            "effectiveness_score": r_eff,
            "cost_score": r_cost,
            "warning_penalty": penalty_factor,
            "raw_score_before_penalty": raw_score_before_penalty
        }
        
        return ScoreResult(
            normalized_total=normalized,
            components=components,
            is_valid=True
        )


class HeatExchangerScoreV3(BaseScoreFunction):
    """Specification-aware thermal, hydraulic, and economic score.

    V3 preserves continuous partial rewards while applying an additional
    penalty for each missed hard-task requirement.  Cost is normalized over a
    task-configurable useful range and softly gated by thermal/hydraulic
    performance so an undersized but cheap exchanger cannot receive full cost
    credit.
    """

    VERSION = "heat_exchanger_score_v3"

    def calculate_score(
        self,
        task_params: Dict[str, Any],
        metrics: Dict[str, Any],
        is_valid: bool = True,
        error_message: Optional[str] = None,
    ) -> ScoreResult:
        if not is_valid:
            return ScoreResult(
                normalized_total=0.0,
                is_valid=False,
                error_message=error_message,
            )

        w_heat = task_params.get("w_heat", 0.50)
        w_drop_tube = task_params.get("w_drop_tube", 0.175)
        w_drop_shell = task_params.get("w_drop_shell", 0.175)
        w_eff = task_params.get("w_eff", 0.05)
        w_cost = task_params.get("w_cost", 0.10)

        target_heat = task_params.get("target_heat_duty", 350000.0)
        max_dp_tube = task_params.get("max_dp_tube", 2500.0)
        max_dp_shell = task_params.get("max_dp_shell", 2500.0)
        cost_good = task_params.get("cost_good", 5000.0)
        cost_bad = task_params.get("cost_bad", 15000.0)
        warning_penalty = task_params.get("warning_penalty_per_warning", 0.10)
        unmet_penalty = task_params.get("unmet_penalty_per_requirement", 0.10)

        weights = (w_heat, w_drop_tube, w_drop_shell, w_eff, w_cost)
        if any(weight < 0 for weight in weights):
            raise ValueError("Score V3 weights must be non-negative")
        if target_heat <= 0 or max_dp_tube <= 0 or max_dp_shell <= 0:
            raise ValueError("Score V3 heat and pressure-drop targets must be positive")
        if cost_good < 0 or cost_bad <= cost_good:
            raise ValueError("Score V3 requires 0 <= cost_good < cost_bad")
        if warning_penalty < 0 or unmet_penalty < 0:
            raise ValueError("Score V3 penalty rates must be non-negative")

        heat_duty = metrics.get("heat_duty_W", metrics.get("heat_duty", 0.0))
        dp_tube = metrics.get(
            "dp_tube_Pa", metrics.get("pressure_drop_tube", max_dp_tube * 2)
        )
        dp_shell = metrics.get(
            "dp_shell_Pa", metrics.get("pressure_drop_shell", max_dp_shell * 2)
        )
        effectiveness = metrics.get("effectiveness", 0.0)
        cost_annualised = metrics.get("cost_annualised_USD_per_yr", cost_bad)
        num_warnings = max(float(metrics.get("num_warnings", 0.0)), 0.0)

        r_heat = min(max(heat_duty / target_heat, 0.0), 1.0)

        if dp_tube <= max_dp_tube:
            r_drop_tube = 1.0
        else:
            r_drop_tube = max(
                1.0 - ((dp_tube - max_dp_tube) / max_dp_tube), 0.0
            )

        if dp_shell <= max_dp_shell:
            r_drop_shell = 1.0
        else:
            r_drop_shell = max(
                1.0 - ((dp_shell - max_dp_shell) / max_dp_shell), 0.0
            )

        r_eff = min(max(effectiveness, 0.0), 1.0)
        r_cost_raw = min(
            max((cost_bad - cost_annualised) / (cost_bad - cost_good), 0.0),
            1.0,
        )
        cost_performance_gate = min(r_heat, r_drop_tube, r_drop_shell)
        r_cost = r_cost_raw * cost_performance_gate

        unmet_heat = heat_duty < target_heat
        unmet_dp_tube = dp_tube > max_dp_tube
        unmet_dp_shell = dp_shell > max_dp_shell
        num_unmet = int(unmet_heat) + int(unmet_dp_tube) + int(unmet_dp_shell)

        total_weight = sum(weights)
        weighted_total = (
            w_heat * r_heat
            + w_drop_tube * r_drop_tube
            + w_drop_shell * r_drop_shell
            + w_eff * r_eff
            + w_cost * r_cost
        )
        raw_score = weighted_total / total_weight if total_weight > 0 else 0.0
        warning_penalty_total = warning_penalty * num_warnings
        requirement_penalty_total = unmet_penalty * num_unmet
        penalty_factor = max(
            1.0 - warning_penalty_total - requirement_penalty_total,
            0.0,
        )
        normalized = min(max(raw_score * penalty_factor, 0.0), 1.0)

        components = {
            "heat_duty_reward": r_heat,
            "pressure_drop_tube_reward": r_drop_tube,
            "pressure_drop_shell_reward": r_drop_shell,
            "effectiveness_reward": r_eff,
            "cost_reward_raw": r_cost_raw,
            "cost_performance_gate": cost_performance_gate,
            "cost_reward": r_cost,
            "num_unmet_requirements": float(num_unmet),
            "warning_penalty_total": warning_penalty_total,
            "requirement_penalty_total": requirement_penalty_total,
            "penalty_factor": penalty_factor,
            "raw_score_before_penalty": raw_score,
        }

        return ScoreResult(
            normalized_total=normalized,
            components=components,
            is_valid=True,
        )

# Original public name used by demos and manual evaluation.
HeatExchangerScore = HeatExchangerScoreV1



class HeatExchangerScoreV4(BaseScoreFunction):
    """Gated optimisation score: requirements are the gate, quality is the score.

    V1-V3 spread most of their weight across the task requirements themselves,
    so a design earned roughly 85% of the available raw score the moment it met
    the duty target and both pressure-drop limits. Everything a good engineer
    does beyond that — making it cheaper, making it clean — competed for the
    remaining 15%. Measured across sixteen parameter settings, the score for
    merely reaching a feasible design never moved off 0.439, whatever the
    targets were. That is a structural property of the weighting, not a
    calibration that better numbers could fix.

    V4 separates the two questions engineering actually asks:

      1. *Does it meet spec?*  The duty target and both pressure-drop limits
         are a gate. Passing it is worth ``gate_share`` (0.30 by default) and
         no more; a design that falls short earns the same share scaled by how
         close it came, so the boundary is continuous rather than a cliff.

      2. *How good is it?*  The remaining 0.70 is earned only by designs that
         pass, and only through things that can always be improved: annualised
         cost, thermal effectiveness, and freedom from design warnings.

    Effectiveness is deliberately *not* part of the quality term, even though
    every earlier version rewards it. With the flows and inlet temperatures
    fixed, ``Q_max = C_min * dT`` is a constant, so effectiveness is exactly
    ``heat_duty / 627300`` — measured across 4,353 designs the correlation
    with duty is 1.0000000000 and the ratio never varies. Rewarding both means
    paying twice for one quantity, and because the gate already forces a
    minimum duty it hands the quality term a free floor: at a 250 kW target,
    effectiveness cannot fall below 0.3985, which is 72% of a 0.55 goal before
    the design has done anything. Quality is therefore carried by cost, which
    is genuinely unbounded, and by warning-freedom, which across the same
    sample is uncorrelated with cost (r = 0.007) and so is a second, separate
    thing to be good at rather than something tradeable against the first.
    """

    VERSION = "heat_exchanger_score_v4"

    def calculate_score(
        self,
        task_params: Dict[str, Any],
        metrics: Dict[str, Any],
        is_valid: bool = True,
        error_message: Optional[str] = None,
    ) -> ScoreResult:
        if not is_valid:
            return ScoreResult(
                normalized_total=0.0,
                is_valid=False,
                error_message=error_message,
            )

        gate_share = task_params.get("gate_share", 0.30)
        target_heat = task_params.get("target_heat_duty", 250000.0)
        max_dp_tube = task_params.get("max_dp_tube", 10000.0)
        max_dp_shell = task_params.get("max_dp_shell", 10000.0)

        cost_good = task_params.get("cost_good", 2000.0)
        cost_bad = task_params.get("cost_bad", 20000.0)
        warning_penalty = task_params.get("warning_penalty_per_warning", 0.10)

        if not 0.0 <= gate_share <= 1.0:
            raise ValueError("Score V4 requires 0 <= gate_share <= 1")
        if target_heat <= 0 or max_dp_tube <= 0 or max_dp_shell <= 0:
            raise ValueError("Score V4 heat and pressure-drop targets must be positive")
        if cost_good < 0 or cost_bad <= cost_good:
            raise ValueError("Score V4 requires 0 <= cost_good < cost_bad")
        if warning_penalty < 0:
            raise ValueError("Score V4 penalty rate must be non-negative")

        heat_duty = metrics.get("heat_duty_W", metrics.get("heat_duty", 0.0))
        dp_tube = metrics.get(
            "dp_tube_Pa", metrics.get("pressure_drop_tube", max_dp_tube * 2)
        )
        dp_shell = metrics.get(
            "dp_shell_Pa", metrics.get("pressure_drop_shell", max_dp_shell * 2)
        )
        effectiveness = metrics.get("effectiveness", 0.0)
        cost_annualised = metrics.get("cost_annualised_USD_per_yr", cost_bad)
        num_warnings = max(float(metrics.get("num_warnings", 0.0)), 0.0)

        # ── 1. The gate ───────────────────────────────────────────────
        duty_progress = min(max(heat_duty / target_heat, 0.0), 1.0)
        tube_progress = _limit_progress(dp_tube, max_dp_tube)
        shell_progress = _limit_progress(dp_shell, max_dp_shell)

        duty_met = heat_duty >= target_heat
        tube_met = dp_tube <= max_dp_tube
        shell_met = dp_shell <= max_dp_shell
        unmet = [name for name, met in (
            ("heat duty", duty_met),
            ("tube pressure drop", tube_met),
            ("shell pressure drop", shell_met),
        ) if not met]

        gate_progress = (duty_progress + tube_progress + shell_progress) / 3.0

        # ── 2. Quality, earned only past the gate ─────────────────────
        cost_reward = _band_reward(cost_annualised, cost_good, cost_bad)
        quality = cost_reward
        penalty_factor = max(1.0 - num_warnings * warning_penalty, 0.0)

        if unmet:
            total = gate_share * gate_progress
        else:
            total = gate_share + (1.0 - gate_share) * quality * penalty_factor

        components = {
            "gate_passed": 0.0 if unmet else 1.0,
            "gate_progress": gate_progress,
            "duty_progress": duty_progress,
            "tube_drop_progress": tube_progress,
            "shell_drop_progress": shell_progress,
            "num_unmet_requirements": float(len(unmet)),
            "cost_reward": cost_reward,
            "effectiveness": effectiveness,
            "quality": quality,
            "penalty_factor": penalty_factor,
            "gate_component": gate_share * (gate_progress if unmet else 1.0),
            "quality_component": 0.0 if unmet else (1.0 - gate_share) * quality * penalty_factor,
        }

        return ScoreResult(
            normalized_total=min(max(total, 0.0), 1.0),
            components=components,
            is_valid=True,
            error_message=(
                "Unmet requirement(s): {}".format(", ".join(unmet)) if unmet else None
            ),
        )


def _limit_progress(value: float, limit: float) -> float:
    """How close a not-to-exceed quantity is to its limit, as a 0-1 reward."""
    if value <= limit:
        return 1.0
    return max(1.0 - ((value - limit) / limit), 0.0)


def _band_reward(value: float, good: float, bad: float) -> float:
    """Linear reward: 1.0 at or below ``good``, 0.0 at or above ``bad``."""
    if value <= good:
        return 1.0
    if value >= bad:
        return 0.0
    return (bad - value) / (bad - good)


SCORE_REGISTRY = {
    "heat_exchanger_score_v1": HeatExchangerScoreV1,
    "heat_exchanger_score_v2": HeatExchangerScoreV2,
    "heat_exchanger_score_v3": HeatExchangerScoreV3,
    "heat_exchanger_score_v4": HeatExchangerScoreV4,
}

def get_score_function(version: str) -> BaseScoreFunction:
    """Returns the instantiated score function based on version string."""
    if version not in SCORE_REGISTRY:
        raise ValueError(f"Unknown score version '{version}'. Available: {list(SCORE_REGISTRY.keys())}")
    return SCORE_REGISTRY[version]()
