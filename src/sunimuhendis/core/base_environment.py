import re
import statistics
from abc import ABC, abstractmethod
from collections import Counter
from typing import Any, ClassVar, Dict, List, Optional, Sequence
from .types import AuditReport, EvaluationResult, Requirement, ScoreResult
from .base_simulator import BaseSimulator
from .base_score import BaseScoreFunction

class BaseEnvironment(ABC):
    """
    Main environment class combining the simulator, reward function, and DRC validation.
    """

    #: The name the environment is registered under, e.g. ``"heat_exchanger"``.
    name: ClassVar[Optional[str]] = None
    
    def __init__(self, simulator: BaseSimulator, score_function: BaseScoreFunction):
        self.simulator = simulator
        self.score_function = score_function
        
    @abstractmethod
    def validate_schema(self, design_params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Checks the structural/schema validity of the incoming design.
        E.g., validation via Pydantic model.
        """
        pass
        
    @abstractmethod
    def run_drc(self, design_params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Design Rule Check (DRC). Checks physical/logical constraints.
        """
        pass

    def get_score_function(self, task_params: Dict[str, Any]) -> BaseScoreFunction:
        """
        Returns the score function to be used for the current task.
        By default, returns the environment's default score function.
        Subclasses can override this to support dynamic score functions based on task_params.
        """
        return self.score_function

    # ─────────────────────────────────────────────────────────────────
    #  Task feasibility audit — hooks each environment fills
    # ─────────────────────────────────────────────────────────────────
    #
    # ``audit_task`` below is the shared algorithm; the four hooks here are
    # the environment-specific parts. An environment that implements
    # ``sample_designs`` and ``get_requirements`` gets the whole audit. The
    # other two hooks sharpen it but are optional.
    #
    # These are deliberately NOT abstract: existing environments (and the
    # dummy ones in tests and scripts) keep working, and ``audit_task``
    # fails with a message naming exactly what is missing.

    def sample_designs(
        self,
        num_samples: int,
        seed: int = 0,
        task_params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Produce ``num_samples`` candidate designs spanning this environment's
        design space. Must be deterministic for a given ``seed``.

        The sampler should cover the space broadly rather than aim for good
        designs: the audit asks what the task makes *possible*, so a biased
        sampler hides exactly the walls it is meant to find.

        ``task_params`` is passed so the sampler can cover the space in
        coordinates the *task* makes meaningful — a velocity, say, rather than
        a tube count, which only becomes a velocity once the flow is known.
        Sampling in the wrong coordinates does not bias the audit, it blinds
        it: a region reachable only by choosing a velocity is a region a
        tube-count sampler reports as unreachable. It is optional, so a
        sampler that does not need it keeps the shorter signature.
        """
        raise NotImplementedError(
            "{} does not implement sample_designs(); it cannot be audited. "
            "Implement it to return a deterministic list of candidate designs."
            .format(type(self).__name__)
        )

    def reference_designs(self, task_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Designs a task offers as *witnesses* to its own feasibility.

        Sampling can show that something is reachable; it can never show that
        something is not, so a score ceiling measured by sampling is a lower
        bound and nothing more. When a task claims a perfect score is
        attainable, the honest way to back the claim is to exhibit a design
        that attains it. The audit evaluates these alongside the sample and
        reports one that fails to do what it was offered to prove.

        The default reads ``task_params['reference_designs']``, so any
        environment gets this by writing designs into its task file.
        """
        designs = task_params.get("reference_designs") or []
        if not isinstance(designs, (list, tuple)):
            raise ValueError("reference_designs must be a list, got {}"
                             .format(type(designs).__name__))
        return [d for d in designs if isinstance(d, dict)]

    def get_requirements(self, task_params: Dict[str, Any]) -> List[Requirement]:
        """
        The hard requirements this task imposes — what a design must meet to
        count as solving the task, as opposed to merely scoring well.
        """
        raise NotImplementedError(
            "{} does not implement get_requirements(); it cannot be audited. "
            "Implement it to translate task_params into a list of Requirement."
            .format(type(self).__name__)
        )

    def list_design_checks(self) -> Sequence[str]:
        """
        Every design check this environment is capable of raising, as stable
        labels. Optional: supplying it lets the audit report *dead* checks —
        rules that can never fire and so silently protect nothing.
        """
        return ()

    def analyse_physics(self, task_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Environment-specific closed-form analysis of the task, for limits that
        sampling cannot prove. A heat exchanger reports its ε-NTU ceiling here;
        an airframe environment would report something else entirely.

        Anything returned lands in ``AuditReport.physics``. Keys whose name
        starts with ``CRITICAL`` or ``WARNING`` are also promoted into
        ``AuditReport.findings``.
        """
        return {}

    def prepare_simulation_inputs(
        self,
        design_params: Dict[str, Any],
        task_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build the dict handed to ``simulator.simulate()`` for one evaluation.

        Stages 1 and 2 always see the design exactly as the model wrote it.
        This hook exists for stage 3 only, where a task may need to fix the
        *context* the design is simulated in — the operating point, the duty
        specification, the fabrication allowables — none of which the designer
        chooses and none of which belong in the design schema.

        The default is the historical behaviour: simulate the design alone.
        An environment that overrides this must let the task win over the
        design, so a design cannot restate its own operating conditions and
        pick an easier problem than the one it was set.
        """
        return design_params

    def secondary_simulations(
        self,
        design_params: Dict[str, Any],
        task_params: Dict[str, Any],
    ) -> List[tuple]:
        """
        Further conditions the same design must also survive, as
        ``(label, simulator_inputs)`` pairs. The default is none, so a
        single-point task behaves exactly as before.

        This is how a task asks for a design rather than a point solution.
        A design sized for one operating point can sit comfortably inside
        every limit at that point and violate them the moment the plant
        turns down — real exchangers are sized for a velocity *window* for
        exactly this reason. Warnings raised here are added to the primary
        count, so the requirements stay a single-point gate while quality
        becomes a property of the design across its whole operating range.
        """
        return []

    @staticmethod
    def normalise_warning(warning: str) -> str:
        """
        Collapse a warning into a stable label so occurrences can be counted.
        By default strips embedded numbers, so 'Tube velocity 0.13 m/s < min
        0.5 m/s' and 'Tube velocity 0.31 m/s < min 0.5 m/s' become one label.
        """
        return re.sub(r"[-+]?\d*\.?\d+", "#", warning).strip()

    def extract_warnings(self, metrics: Dict[str, Any], raw_output: Dict[str, Any]) -> List[str]:
        """
        Pull the design warnings out of one simulation result. The default
        reads ``raw_output['warnings']``; override if a simulator reports them
        elsewhere.
        """
        warnings = raw_output.get("warnings", [])
        if not isinstance(warnings, (list, tuple)):
            return []
        return [str(w) for w in warnings]

    # ─────────────────────────────────────────────────────────────────
    #  Task feasibility audit — the shared algorithm
    # ─────────────────────────────────────────────────────────────────

    def audit_task(
        self,
        task_params: Dict[str, Any],
        num_samples: int = 20000,
        seed: int = 0,
    ) -> AuditReport:
        """
        Audit a task configuration for feasibility before spending any model
        calls on it.

        Answers four questions a task must survive to measure anything:

        1. Is the task reachable at all — does any design meet every requirement?
        2. Is any penalty unavoidable — does every feasible design carry the
           same warning? Such a penalty is a constant tax, not feedback.
        3. Where does the reward actually live — is producing *some* valid
           design worth more than producing a good one?
        4. Do the declared design checks ever fire, or are some of them dead?

        Requires ``sample_designs`` and ``get_requirements``.
        """
        task_id = str(task_params.get("task_id", "audit"))
        designs = self.sample_designs(num_samples, seed, task_params)
        references = self.reference_designs(task_params)
        reference_from = len(designs)
        designs = list(designs) + list(references)
        requirements = self.get_requirements(task_params)
        reference_results: List[tuple] = []

        best_score = None
        feasible_scores: List[float] = []
        feasible_warning_sets: List[frozenset] = []
        feasible_warning_counts: List[int] = []
        warning_counter: Counter = Counter()
        requirement_hits: Counter = Counter()
        simulated = 0

        for index, design in enumerate(designs):
            result = self.evaluate(task_id, task_params, "audit-{}".format(index), design)
            score = result.score.normalized_total
            if index >= reference_from:
                reference_results.append((index - reference_from, result))
            if best_score is None or score > best_score:
                best_score = score
            if result.status != "success":
                continue

            simulated += 1
            labels = {self.normalise_warning(w)
                      for w in self.extract_warnings(result.metrics, result.raw_simulation_output)}
            for label in labels:
                warning_counter[label] += 1

            met_all = True
            for requirement in requirements:
                if requirement.satisfied_by(result.metrics):
                    requirement_hits[requirement.name] += 1
                else:
                    met_all = False
            if met_all:
                feasible_scores.append(score)
                feasible_warning_sets.append(frozenset(labels))
                feasible_warning_counts.append(len(labels))

        report = AuditReport(
            environment=type(self).__name__,
            task_id=task_id,
            samples_requested=len(designs),
            samples_simulated=simulated,
            feasible_count=len(feasible_scores),
            requirements=requirements,
            score_ceiling=best_score,
        )

        if simulated:
            report.requirement_satisfaction = {
                r.name: requirement_hits[r.name] / simulated for r in requirements
            }
            report.warning_frequency = {
                label: count / simulated for label, count in warning_counter.most_common()
            }
            declared = list(self.list_design_checks())
            if declared:
                fired = set(warning_counter)
                report.dead_checks = [
                    check for check in declared
                    if not any(check.lower() in label.lower() for label in fired)
                ]

        if feasible_scores:
            report.feasible_score_floor = min(feasible_scores)
            report.feasible_score_median = statistics.median(feasible_scores)
            report.min_warning_count = min(feasible_warning_counts)
            forced = frozenset.intersection(*feasible_warning_sets)
            report.forced_warnings = sorted(forced)
            report.entry_reward = report.feasible_score_floor
            if best_score is not None:
                report.craft_reward = best_score - report.feasible_score_floor

        report.reference_count = len(references)
        if reference_results:
            report.reference_scores = [
                result.score.normalized_total for _, result in reference_results]
            for position, result in reference_results:
                if result.status != "success":
                    report.reference_failures.append(
                        "reference design {} did not simulate ({}): {}".format(
                            position, result.status, result.error_message))
                    continue
                unmet = [r.name for r in requirements if not r.satisfied_by(result.metrics)]
                if unmet:
                    report.reference_failures.append(
                        "reference design {} does not meet: {}".format(
                            position, "; ".join(unmet)))

        report.physics = self.analyse_physics(task_params)
        report.findings = self._derive_findings(report)
        return report

    @staticmethod
    def _derive_findings(report: AuditReport) -> List[str]:
        """Turn the measured audit numbers into ranked, readable findings."""
        findings: List[str] = []

        if report.samples_simulated == 0:
            findings.append(
                "CRITICAL: no sampled design simulated successfully — the sampler and the "
                "environment disagree about the design space."
            )
            return findings

        if report.feasible_count == 0:
            unmet = sorted(report.requirement_satisfaction.items(), key=lambda kv: kv[1])
            findings.append(
                "CRITICAL: no sampled design meets every requirement — the task may be "
                "unreachable. Hardest requirement: '{}' met by {:.2%} of designs.".format(
                    unmet[0][0], unmet[0][1]) if unmet else
                "CRITICAL: no sampled design meets every requirement."
            )

        if report.forced_warnings:
            findings.append(
                "CRITICAL: {} warning(s) fire for EVERY feasible design ({}). This is a constant "
                "penalty no design can avoid, so it carries no information and only shrinks the "
                "usable score range.".format(
                    len(report.forced_warnings), "; ".join(report.forced_warnings))
            )

        if report.entry_reward is not None and report.craft_reward is not None:
            if report.craft_reward <= 0:
                findings.append(
                    "CRITICAL: the best design observed scores no better than the worst feasible "
                    "one — the score cannot rank designs that solve the task."
                )
            elif report.entry_reward > report.craft_reward:
                findings.append(
                    "WARNING: reward budget favours showing up over engineering — reaching any "
                    "feasible design is worth +{:.3f} while perfecting it is worth only +{:.3f}. "
                    "Iterative improvement has little room to show.".format(
                        report.entry_reward, report.craft_reward)
                )

        if report.min_warning_count:
            findings.append(
                "INFO: the fewest warnings any feasible design achieved is {} — a warning-free "
                "design may be out of reach.".format(report.min_warning_count)
            )

        if report.reference_failures:
            findings.append(
                "CRITICAL: {} reference design(s) do not do what the task offers them to "
                "prove ({}). A witness that does not hold is worse than none, because the "
                "task's feasibility claim now rests on nothing.".format(
                    len(report.reference_failures), "; ".join(report.reference_failures))
            )

        if report.dead_checks:
            findings.append(
                "INFO: {} declared design check(s) never fired across the sample ({}). They "
                "protect nothing as configured.".format(
                    len(report.dead_checks), "; ".join(report.dead_checks))
            )

        for key, value in report.physics.items():
            if key.startswith("CRITICAL") or key.startswith("WARNING"):
                findings.append("{}: {}".format(key, value))

        severities = ("CRITICAL", "WARNING", "INFO")

        def rank(finding: str) -> int:
            for level, prefix in enumerate(severities):
                if finding.startswith(prefix):
                    return level
            return len(severities)

        findings.sort(key=rank)
        return findings
        
    def evaluate(self, task_id: str, task_params: Dict[str, Any], design_id: str, design_params: Dict[str, Any]) -> EvaluationResult:
        """
        Main evaluation loop: schema, DRC, simulation, score.

        Every result, whatever stage it stopped at, is stamped with the
        environment name and the simulator and score versions that produced
        it, so a number can always be traced back to the physics it was
        measured with.
        """
        score_fn = self.get_score_function(task_params)
        result = self._run_pipeline(score_fn, task_id, task_params, design_id, design_params)
        result.environment = self.name
        result.simulator_version = getattr(self.simulator, "VERSION", None)
        result.score_version = getattr(score_fn, "VERSION", None)
        return result

    def _run_pipeline(
        self,
        score_fn: BaseScoreFunction,
        task_id: str,
        task_params: Dict[str, Any],
        design_id: str,
        design_params: Dict[str, Any],
    ) -> EvaluationResult:
        """The four stages, cheapest first; the first failure short-circuits."""
        
        # 1. Schema Validation
        schema_valid, schema_err = self.validate_schema(design_params)
        if not schema_valid:
            score = score_fn.calculate_score(task_params, {}, is_valid=False, error_message=schema_err)
            return EvaluationResult(
                task_id=task_id,
                design_id=design_id,
                status="schema_error",
                score=score,
                error_message=schema_err
            )
            
        # 2. DRC Validation
        drc_valid, drc_err = self.run_drc(design_params)
        if not drc_valid:
            score = score_fn.calculate_score(task_params, {}, is_valid=False, error_message=drc_err)
            return EvaluationResult(
                task_id=task_id,
                design_id=design_id,
                status="drc_error",
                score=score,
                error_message=drc_err
            )
            
        # 3. Simulation
        #
        # Building the simulator's inputs happens OUTSIDE the try below, on
        # purpose. Everything inside it is the design's failure and scores
        # zero; a malformed task configuration is the experimenter's failure
        # and must raise, or a typo in a task file would be recorded as every
        # model failing to design, indistinguishably from the real thing.
        sim_inputs = self.prepare_simulation_inputs(design_params, task_params)
        secondary = self.secondary_simulations(design_params, task_params)

        try:
            success, metrics, raw_data, sim_err = self.simulator.simulate(sim_inputs)
            
            if not success:
                score = score_fn.calculate_score(task_params, {}, is_valid=False, error_message=sim_err)
                return EvaluationResult(
                    task_id=task_id,
                    design_id=design_id,
                    status="simulation_error",
                    score=score,
                    error_message=sim_err
                )
                
            # 3b. The same design at every other operating point the task names.
            if secondary:
                metrics = dict(metrics)
                raw_data = dict(raw_data)
                total = float(metrics.get("num_warnings", 0.0) or 0.0)
                merged = list(raw_data.get("warnings", []) or [])
                points: Dict[str, Any] = {}

                for label, inputs in secondary:
                    ok, point_metrics, point_raw, point_err = self.simulator.simulate(inputs)
                    if not ok:
                        message = "at operating point '{}': {}".format(label, point_err)
                        return EvaluationResult(
                            task_id=task_id,
                            design_id=design_id,
                            status="simulation_error",
                            score=score_fn.calculate_score(
                                task_params, {}, is_valid=False, error_message=message),
                            error_message=message,
                        )
                    found = self.extract_warnings(point_metrics, point_raw)
                    total += len(found)
                    merged.extend("[{}] {}".format(label, w) for w in found)
                    points[label] = {"metrics": point_metrics, "warnings": found}
                    metrics["{}_num_warnings".format(label)] = float(len(found))

                metrics["num_warnings"] = total
                raw_data["warnings"] = merged
                raw_data["secondary_points"] = points

            # 4. Score Calculation (Success case)
            score = score_fn.calculate_score(task_params, metrics, is_valid=True)
            return EvaluationResult(
                task_id=task_id,
                design_id=design_id,
                status="success",
                score=score,
                metrics=metrics,
                raw_simulation_output=raw_data
            )
            
        except Exception as e:
            # Catch unexpected simulator crashes
            error_msg = f"Unexpected simulation crash: {str(e)}"
            score = score_fn.calculate_score(task_params, {}, is_valid=False, error_message=error_msg)
            return EvaluationResult(
                task_id=task_id,
                design_id=design_id,
                status="simulation_error",
                score=score,
                error_message=error_msg
            )
