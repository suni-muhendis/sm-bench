import math
import random
from typing import Dict, Any, List, Optional, Sequence

import ht
from pydantic import ValidationError

from ...core.base_environment import BaseEnvironment
from ...core.base_score import BaseScoreFunction
from ...core.types import Requirement
from .schema import HeatExchangerDesign
from .drc import run_heat_exchanger_drc
from .simulator import HeatExchangerSimulator


class HeatExchangerEnv(BaseEnvironment):
    name = "heat_exchanger"

    def validate_schema(self, design_params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        try:
            HeatExchangerDesign.model_validate(design_params)
            return True, None
        except ValidationError as e:
            return False, f"Schema Error: {str(e)}"

    def run_drc(self, design_params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        return run_heat_exchanger_drc(design_params)

    def get_score_function(self, task_params: Dict[str, Any]) -> BaseScoreFunction:
        """
        Overrides base behavior to dynamically select the score version if
        'score_version' is explicitly defined in the task configuration.
        """
        score_version = task_params.get("score_version")
        if score_version:
            from .score import get_score_function
            return get_score_function(score_version)
        return self.score_function

    # ─────────────────────────────────────────────────────────────────
    #  Operating conditions the task fixes, not the designer
    # ─────────────────────────────────────────────────────────────────

    #: The context a task may set, with the validation each value must pass.
    #: Everything here is imposed by the plant the exchanger goes into — the
    #: streams it must handle, the fouling it must tolerate, the pressure and
    #: stress it is built to. None of it is a design decision, so none of it
    #: belongs in the schema; but all of it changes the physics, so a task
    #: that cannot set it can only ever pose one problem.
    OPERATING_CONDITION_KEYS = {
        "m_dot_hot": "positive",
        "m_dot_cold": "positive",
        "T_hot_in": "temperature",
        "T_cold_in": "temperature",
        "k_wall": "positive",
        "R_fi": "non_negative",
        "R_fo": "non_negative",
        "P_design": "positive",
        "allowable_stress": "positive",
    }

    @classmethod
    def operating_conditions(cls, task_params: Dict[str, Any]) -> Dict[str, float]:
        """
        Resolve this task's operating point, defaults included.

        Raises ``ValueError`` on an unknown key or an impossible value rather
        than falling back to the default: a typo that silently reverts to
        2.5 kg/s would make every downstream number a quiet lie, and the audit
        would certify the wrong task.
        """
        sim = HeatExchangerSimulator
        resolved = {
            "m_dot_hot": sim.DEFAULT_M_DOT_HOT,
            "m_dot_cold": sim.DEFAULT_M_DOT_COLD,
            "T_hot_in": sim.DEFAULT_T_HOT_IN_C,
            "T_cold_in": sim.DEFAULT_T_COLD_IN_C,
            "k_wall": 50.0,
            "R_fi": 1.76e-4,
            "R_fo": 1.76e-4,
            "P_design": 101325.0,
            "allowable_stress": 137e6,
        }

        raw = task_params.get("operating_conditions") or {}
        if not isinstance(raw, dict):
            raise ValueError("operating_conditions must be a mapping, got {}"
                             .format(type(raw).__name__))

        for key, value in raw.items():
            rule = cls.OPERATING_CONDITION_KEYS.get(key)
            if rule is None:
                raise ValueError(
                    "unknown operating condition '{}'; the task may set only: {}"
                    .format(key, ", ".join(sorted(cls.OPERATING_CONDITION_KEYS)))
                )
            try:
                number = float(value)
            except (TypeError, ValueError):
                raise ValueError("operating condition '{}' must be a number, got {!r}"
                                 .format(key, value))
            if not math.isfinite(number):
                raise ValueError("operating condition '{}' is not finite".format(key))
            if rule == "positive" and number <= 0:
                raise ValueError("operating condition '{}' must be positive, got {}"
                                 .format(key, number))
            if rule == "non_negative" and number < 0:
                raise ValueError("operating condition '{}' must not be negative, got {}"
                                 .format(key, number))
            if rule == "temperature" and number <= -273.15:
                raise ValueError("operating condition '{}' is below absolute zero".format(key))
            resolved[key] = number

        if resolved["T_hot_in"] <= resolved["T_cold_in"]:
            raise ValueError(
                "T_hot_in ({} C) must exceed T_cold_in ({} C); there is no heat to exchange"
                .format(resolved["T_hot_in"], resolved["T_cold_in"])
            )
        return resolved

    def prepare_simulation_inputs(
        self,
        design_params: Dict[str, Any],
        task_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Simulate the design at the operating point the *task* specifies.

        The task is applied over the design, not under it. The schema forbids
        extra fields so a benchmarked design cannot carry these keys anyway,
        but a design handed straight to the environment could — and a design
        that could restate its own flow rate would be answering an easier
        question than the one it was asked.
        """
        return dict(design_params, **self.operating_conditions(task_params))

    def secondary_simulations(
        self,
        design_params: Dict[str, Any],
        task_params: Dict[str, Any],
    ) -> List[tuple]:
        """
        The other loads this exchanger has to live at.

        A task lists them under ``secondary_operating_points`` as
        ``{"name": "turndown", "operating_conditions": {...}}``. Each point's
        conditions are applied *over* the task's primary point, so a turndown
        case names only the flows it changes and inherits the inlet
        temperatures, fouling and allowables it does not.

        Why this is the lever: measured over 5,714 sampled designs, ten met
        every requirement at full load with no warnings at all — and all ten
        raised at least one at 60% flow. Tube velocity has a floor for fouling
        and a ceiling for erosion, so a design sized at one flow cannot be
        sized at another by accident. Nothing else in this environment's
        parameter space couples the limits that way.
        """
        points = task_params.get("secondary_operating_points") or []
        if not isinstance(points, (list, tuple)):
            raise ValueError("secondary_operating_points must be a list, got {}"
                             .format(type(points).__name__))

        primary = self.operating_conditions(task_params)
        prepared: List[tuple] = []
        seen = set()

        for index, point in enumerate(points):
            if not isinstance(point, dict):
                raise ValueError("secondary operating point {} must be a mapping".format(index))
            label = str(point.get("name") or "point_{}".format(index + 1))
            if not label.strip():
                raise ValueError("secondary operating point {} has an empty name".format(index))
            if label in seen:
                raise ValueError("duplicate secondary operating point name '{}'".format(label))
            seen.add(label)

            unknown = set(point) - {"name", "operating_conditions"}
            if unknown:
                raise ValueError(
                    "secondary operating point '{}' has unexpected key(s): {}"
                    .format(label, ", ".join(sorted(unknown)))
                )

            overrides = point.get("operating_conditions") or {}
            if not isinstance(overrides, dict):
                raise ValueError("operating_conditions of point '{}' must be a mapping"
                                 .format(label))
            if not overrides:
                raise ValueError(
                    "secondary operating point '{}' changes nothing; simulating the primary "
                    "point twice would just double every warning it raises".format(label)
                )

            # Validate the merged point, not the overrides alone: a turndown
            # case that only lowers the flow must still be a possible one.
            resolved = self.operating_conditions(
                {"operating_conditions": dict(primary, **overrides)})
            prepared.append((label, dict(design_params, **resolved)))

        return prepared

    # ─────────────────────────────────────────────────────────────────
    #  Task feasibility audit hooks
    # ─────────────────────────────────────────────────────────────────

    #: Tube outside diameters in common commercial use [m] — 3/8" to 2".
    TUBE_OD_SERIES = (0.00953, 0.0127, 0.01588, 0.01905, 0.0254, 0.0318, 0.0381, 0.0508)

    #: Tube counts spanning small bundles to large ones. Even, because the
    #: DRC requires the count to divide by the (fixed) two tube passes.
    TUBE_COUNT_SERIES = (2, 4, 10, 20, 50, 100, 200, 400, 800, 1600)

    #: Commercial tube wall thicknesses [m] — 20 BWG to 11 BWG.
    TUBE_WALL_SERIES = (0.0009, 0.0012, 0.0016, 0.002, 0.0025, 0.0032)

    def _sample_by_velocity(self, rng, task_params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        One design drawn in the coordinates the physics uses.

        The broad sampler picks a tube count and a bore independently of the
        flow, so tube and nozzle velocity come out essentially random — and
        every limit that is a velocity window is then satisfied only by
        accident. Measured on ``heat_exchanger_hard_v4``, that sampler found
        no warning-free design in 6,000 tries while a structured grid found
        566, which the audit would have reported as a score ceiling of 0.61
        against a true ceiling of 1.000. The fix is to sample the velocity
        and derive the geometry, not the reverse.
        """
        sim = HeatExchangerSimulator
        conditions = self.operating_conditions(task_params or {})
        m_dot_hot = conditions["m_dot_hot"]
        m_dot_cold = conditions["m_dot_cold"]
        rho_hot = sim.HOT_FLUID["rho"]
        rho_cold = sim.COLD_FLUID["rho"]

        do = rng.choice(self.TUBE_OD_SERIES)
        wall = rng.choice([w for w in self.TUBE_WALL_SERIES if 2 * w < do * 0.8]
                          or [self.TUBE_WALL_SERIES[0]])
        di = do - 2 * wall
        passes = rng.choice((2, 2, 2, 4))

        # Tube count from a target velocity that spans the fouling floor and
        # the erosion ceiling, and overshoots both so the walls stay visible.
        v_tube = rng.uniform(0.2, 4.0)
        area_per_tube = math.pi * di * di / 4.0
        per_pass = max(1, int(round(m_dot_hot / (rho_hot * v_tube * area_per_tube))))
        count = passes * per_pass

        # Nozzle bores from target velocities, same reasoning.
        def bore(m_dot, rho):
            v = rng.uniform(0.5, 6.0)
            return math.sqrt(4.0 * m_dot / (rho * v * math.pi))

        length = rng.uniform(1.0, 9.0)
        pitch_ratio = rng.uniform(1.25, 1.60)
        # Shell just large enough for the bundle, plus a sampled clearance.
        bundle = do + pitch_ratio * do * math.sqrt(4.0 * count / math.pi)
        shell = bundle * rng.uniform(1.02, 1.6)

        return {
            "geometry_type": "shell_and_tube",
            "length": length,
            "inner_tube_di": di,
            "inner_tube_do": do,
            "outer_shell_di": shell,
            "number_of_tubes": count,
            "baffle_spacing": length * rng.uniform(0.05, 0.9),
            "tube_passes": passes,
            "pitch_ratio": pitch_ratio,
            "pitch_type": rng.choice(("square", "triangular")),
            "baffle_cut": rng.uniform(0.15, 0.45),
            "D_nozzle_hot": min(bore(m_dot_hot, rho_hot), 0.34 * shell),
            "D_nozzle_cold": min(bore(m_dot_cold, rho_cold), 0.34 * shell),
        }

    def sample_designs(
        self,
        num_samples: int,
        seed: int = 0,
        task_params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Spread candidate designs across the heat-exchanger design space.

        Deliberately broad rather than good: the audit asks what the task makes
        reachable, so a sampler that steered towards known-good designs would
        hide the very walls it is there to find. One design in ten is a
        concentric tube, which is the only way to reach pure counter-flow and
        therefore the only escape from the 1-2 shell-and-tube ε ceiling.

        Three in ten designs are instead drawn in velocity coordinates
        (``_sample_by_velocity``), because a limit that is a velocity window
        is invisible to a sampler that chooses tube counts and bores without
        reference to the flow.

        Self-contained by design — ``baselines/`` is excluded from the wheel,
        so the shipped environment cannot depend on the samplers that live there.
        """
        rng = random.Random(seed)
        designs: List[Dict[str, Any]] = []
        for _ in range(num_samples):
            # Three in ten are drawn in velocity coordinates. Without them the
            # audit is blind to every region a velocity window defines — see
            # ``_sample_by_velocity``.
            if rng.random() < 0.30:
                designs.append(self._sample_by_velocity(rng, task_params))
                continue

            if rng.random() < 0.14:
                do = rng.uniform(0.01, 0.30)
                length = rng.uniform(1.0, 200.0)
                designs.append({
                    "geometry_type": "concentric_tube",
                    "length": length,
                    "inner_tube_di": do * rng.uniform(0.55, 0.95),
                    "inner_tube_do": do,
                    "outer_shell_di": do * rng.uniform(1.05, 4.0),
                    "number_of_tubes": 1,
                    "baffle_spacing": length / 5.0,
                })
                continue

            do = rng.choice(self.TUBE_OD_SERIES)
            length = rng.uniform(0.5, 15.0)
            shell = rng.uniform(0.1, 1.5)
            passes = rng.choice((2, 2, 2, 4, 6))
            count = rng.choice(self.TUBE_COUNT_SERIES)
            design = {
                "geometry_type": "shell_and_tube",
                "length": length,
                "inner_tube_di": do * rng.uniform(0.55, 0.94),
                "inner_tube_do": do,
                "outer_shell_di": shell,
                "number_of_tubes": count - (count % passes),
                "baffle_spacing": rng.uniform(0.05, min(length * 0.95, 2.0)),
            }
            # Half the designs also exercise the optional fields. A sampler that
            # only ever emitted the seven required ones would leave the audit
            # blind to the levers it is there to evaluate — the nozzle and
            # layout checks would look dead simply because nothing ever moved
            # them.
            if rng.random() < 0.5:
                design.update({
                    "tube_passes": passes,
                    "pitch_ratio": rng.uniform(1.25, 1.60),
                    "pitch_type": rng.choice(("square", "triangular")),
                    "baffle_cut": rng.uniform(0.15, 0.45),
                    "D_nozzle_hot": rng.uniform(0.015, 0.35 * shell),
                    "D_nozzle_cold": rng.uniform(0.015, 0.35 * shell),
                })
            designs.append(design)
        return designs

    def get_requirements(self, task_params: Dict[str, Any]) -> List[Requirement]:
        """
        The three hard requirements a heat-exchanger task imposes: deliver the
        target duty, and stay inside both pressure-drop limits.

        Defaults match those in ``score.py`` so an under-specified task audits
        the same way it scores.
        """
        return [
            Requirement(
                name="heat duty",
                metric_key="heat_duty_W",
                operator="gte",
                limit=float(task_params.get("target_heat_duty", 150000.0)),
            ),
            Requirement(
                name="tube pressure drop",
                metric_key="dp_tube_Pa",
                operator="lte",
                limit=float(task_params.get("max_dp_tube", 50000.0)),
            ),
            Requirement(
                name="shell pressure drop",
                metric_key="dp_shell_Pa",
                operator="lte",
                limit=float(task_params.get("max_dp_shell", 50000.0)),
            ),
        ]

    def list_design_checks(self) -> Sequence[str]:
        """
        Every check ``HeatExchangerSimulator._check_design_limits`` can raise,
        identified by a phrase unique to its warning text. Supplying this lets
        the audit report checks that never fire — rules that, as configured,
        protect nothing.
        """
        return (
            "erosion risk",
            "fouling risk",
            "Shell velocity # m/s > max",
            "Hot nozzle velocity",
            "Cold nozzle velocity",
            "Tube ΔP",
            "Shell ΔP",
            "Min approach",
            "poor design",
            "Tube wall",
            "Shell wall",
            "flow-induced vibration",
            "Unsupported span",
            "tube sag risk",
            "poor distribution",
            "TEMA minimum",
            "laminar flow",
            "transitional flow",
        )

    def analyse_physics(self, task_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Closed-form limits that sampling cannot prove, for this environment.

        Three walls a heat-exchanger task can be calibrated into:

        1. **The ε ceiling.** The schema fixes the configuration at one shell
           pass and two tube passes, whose effectiveness asymptotes to
           ``2/(1+Cr+√(1+Cr²))`` however much area a design buys. A duty target
           near that ceiling leaves nothing to optimise.
        2. **Duty that forces the F warning.** With flows and inlet temperatures
           fixed, the LMTD correction factor F depends on duty alone. Past a
           certain duty every design trips ``MIN_F_LMTD``, so meeting the
           requirement guarantees the penalty.
        3. **A pressure-drop budget eaten by the nozzles.** Nozzle diameter is
           not in the schema, so its loss is a constant the design cannot
           influence. When it dominates the limit, the real constraint is far
           tighter than the stated one — and can make the minimum tube velocity
           unreachable.
        """
        sim = HeatExchangerSimulator
        hot, cold = sim.HOT_FLUID, sim.COLD_FLUID
        oc = self.operating_conditions(task_params)
        m_dot_hot, m_dot_cold = oc["m_dot_hot"], oc["m_dot_cold"]

        c_hot = m_dot_hot * hot["Cp"]
        c_cold = m_dot_cold * cold["Cp"]
        c_min, c_max = min(c_hot, c_cold), max(c_hot, c_cold)
        c_ratio = c_min / c_max
        t_hot_in, t_cold_in = oc["T_hot_in"], oc["T_cold_in"]
        duty_max = c_min * (t_hot_in - t_cold_in)

        # 1. ε ceiling of the 1-2 shell-and-tube configuration the schema forces.
        root = math.sqrt(1.0 + c_ratio ** 2)
        eps_ceiling = 2.0 / (1.0 + c_ratio + root)
        duty_ceiling = eps_ceiling * duty_max

        target = float(task_params.get("target_heat_duty", 150000.0))
        out: Dict[str, Any] = {
            "operating_conditions": dict(oc),
            "capacity_ratio_Cr": round(c_ratio, 5),
            "duty_max_thermodynamic_W": round(duty_max, 1),
            "epsilon_ceiling_1_2_shell_and_tube": round(eps_ceiling, 6),
            "duty_ceiling_1_2_shell_and_tube_W": round(duty_ceiling, 1),
            "target_duty_W": target,
        }

        reach = target / duty_ceiling if duty_ceiling > 0 else float("inf")
        out["target_as_fraction_of_duty_ceiling"] = round(reach, 4)
        if reach > 1.0:
            out["CRITICAL_duty_unreachable"] = (
                "target duty {:.0f} W exceeds the {:.0f} W ceiling of the 1-2 shell-and-tube "
                "configuration the schema forces; no design can meet it at any size"
                .format(target, duty_ceiling)
            )
        elif reach > 0.90:
            out["CRITICAL_duty_near_ceiling"] = (
                "target duty is {:.1%} of the {:.0f} W configuration ceiling — beyond NTU~3 more "
                "area buys almost no duty, so the heat objective is a threshold, not a gradient"
                .format(reach, duty_ceiling)
            )

        # 2. The duty past which every design trips the F correction warning.
        duty_at_f_limit = self._duty_at_f_limit(c_hot, c_cold, t_hot_in, t_cold_in, duty_ceiling)
        if duty_at_f_limit is not None:
            out["duty_at_F_limit_W"] = round(duty_at_f_limit, 1)
            if target > duty_at_f_limit:
                out["CRITICAL_F_warning_forced"] = (
                    "F falls below {} above {:.0f} W, and F depends on duty alone — so meeting the "
                    "{:.0f} W target guarantees the 'poor design' warning on every design"
                    .format(sim.MIN_F_LMTD, duty_at_f_limit, target)
                )

        # 3. Nozzle share of each pressure-drop budget, and the tube velocity it allows.
        limits = (
            ("tube", float(task_params.get("max_dp_tube", 50000.0)),
             hot["rho"], m_dot_hot, sim.DEFAULT_D_NOZZLE_HOT),
            ("shell", float(task_params.get("max_dp_shell", 50000.0)),
             cold["rho"], m_dot_cold, sim.DEFAULT_D_NOZZLE_COLD),
        )
        for side, limit, rho, m_dot, d_nozzle in limits:
            v_nozzle = m_dot / (rho * math.pi * (d_nozzle / 2.0) ** 2)
            dp_nozzle = sim.NOZZLE_K_TOTAL * rho * v_nozzle ** 2 / 2.0
            share = dp_nozzle / limit if limit > 0 else float("inf")
            out["{}_nozzle_dp_Pa".format(side)] = round(dp_nozzle, 1)
            out["{}_nozzle_share_of_limit".format(side)] = round(share, 4)
            if share >= 0.5:
                out["WARNING_{}_budget_is_fixed".format(side)] = (
                    "{:.0%} of the {:.0f} Pa {}-side limit is nozzle loss, which the schema does "
                    "not expose — the design can only influence the remaining {:.0f} Pa"
                    .format(share, limit, side, max(limit - dp_nozzle, 0.0))
                )

        # The tube-side budget left over caps velocity through the header loss alone.
        dp_tube_limit = float(task_params.get("max_dp_tube", 50000.0))
        v_nozzle_hot = m_dot_hot / (
            hot["rho"] * math.pi * (sim.DEFAULT_D_NOZZLE_HOT / 2.0) ** 2)
        budget = dp_tube_limit - sim.NOZZLE_K_TOTAL * hot["rho"] * v_nozzle_hot ** 2 / 2.0
        # Header loss is 4 velocity heads per pass; two passes are forced by the schema.
        header_coefficient = 4.0 * 2 * hot["rho"] / 2.0
        v_cap = math.sqrt(budget / header_coefficient) if budget > 0 else 0.0
        out["tube_velocity_cap_m_s"] = round(v_cap, 4)
        if v_cap < sim.MIN_TUBE_VELOCITY:
            out["CRITICAL_tube_velocity_warning_forced"] = (
                "the {:.0f} Pa tube limit caps velocity at {:.3f} m/s even with zero friction, "
                "below the {} m/s fouling minimum — so satisfying the pressure-drop requirement "
                "guarantees the velocity warning"
                .format(dp_tube_limit, v_cap, sim.MIN_TUBE_VELOCITY)
            )

        return out

    @staticmethod
    def _duty_at_f_limit(c_hot, c_cold, t_hot_in_c, t_cold_in_c, duty_ceiling):
        """
        The duty at which F crosses ``MIN_F_LMTD``, by bisection.

        F is a function of the four terminal temperatures; with flows and both
        inlets fixed, duty determines all of them, so F is a function of duty
        alone and crosses the limit exactly once (it falls monotonically as the
        temperature cross deepens). Returns None if the limit is never crossed
        below the configuration's duty ceiling.
        """
        limit = HeatExchangerSimulator.MIN_F_LMTD
        t_hot_in = t_hot_in_c + 273.15
        t_cold_in = t_cold_in_c + 273.15

        def f_at(duty):
            try:
                return ht.F_LMTD_Fakheri(
                    Thi=t_hot_in,
                    Tho=t_hot_in - duty / c_hot,
                    Tci=t_cold_in,
                    Tco=t_cold_in + duty / c_cold,
                    shells=1,
                )
            except (ValueError, ZeroDivisionError):
                return 0.0

        low, high = 1.0, duty_ceiling * 0.999
        if f_at(high) > limit:
            return None
        for _ in range(80):
            mid = (low + high) / 2.0
            if f_at(mid) > limit:
                low = mid
            else:
                high = mid
        return low
