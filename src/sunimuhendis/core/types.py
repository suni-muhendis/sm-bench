from typing import Dict, Any, List, Literal, Optional
from pydantic import BaseModel, Field

class ScoreResult(BaseModel):
    """
    Holds normalized reward values calculated from simulation results.
    """
    normalized_total: float = Field(..., description="Normalized total score.")
    components: Dict[str, float] = Field(default_factory=dict, description="Sub-components of the score function.")
    is_valid: bool = Field(..., description="Whether the design is physically/schema-wise valid.")
    error_message: Optional[str] = Field(None, description="Error message if is_valid is False.")


class EvaluationResult(BaseModel):
    """
    The final evaluation object returned by BaseEnvironment.
    """
    task_id: str = Field(..., description="ID of the evaluated task.")
    design_id: str = Field(default="unknown", description="ID of the evaluated design (if any).")
    status: str = Field(..., description="'success', 'schema_error', 'drc_error', 'simulation_error'")
    error_message: Optional[str] = Field(None, description="Error status message")
    score: ScoreResult
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Raw engineering metrics returned from the simulator.")
    raw_simulation_output: Dict[str, Any] = Field(default_factory=dict, description="Other raw data the simulator might return (optional).")
    environment: Optional[str] = Field(None, description="Name of the environment that produced this result.")
    simulator_version: Optional[str] = Field(
        None, description="Physics version of the simulator. Results from different versions are never pooled.")
    score_version: Optional[str] = Field(None, description="Identifier of the score function that produced the score.")


class Requirement(BaseModel):
    """
    One hard requirement a task imposes on a design.

    Requirements are what the task *demands* — the things a design either meets
    or does not. They are deliberately separate from the score weights, which
    express how much partial credit each objective earns.
    """
    name: str = Field(..., description="Human-readable requirement name, e.g. 'heat duty'.")
    metric_key: str = Field(..., description="Key to read from the simulator's metrics dict.")
    operator: Literal["gte", "lte"] = Field(..., description="'gte': metric >= limit. 'lte': metric <= limit.")
    limit: float = Field(..., description="The threshold the metric is compared against.")

    def satisfied_by(self, metrics: Dict[str, Any]) -> bool:
        """Whether a simulated design's metrics meet this requirement."""
        value = metrics.get(self.metric_key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        return value >= self.limit if self.operator == "gte" else value <= self.limit


class AuditReport(BaseModel):
    """
    Result of ``BaseEnvironment.audit_task`` — a feasibility audit of a task
    configuration, before any model is ever run against it.

    The purpose is to catch tasks that are calibrated into a wall: targets no
    design can reach, penalties no design can avoid, or a reward budget that
    pays more for producing *any* valid design than for producing a good one.
    """
    environment: str = Field(..., description="Environment class name the audit ran against.")
    task_id: str = Field(default="audit", description="Task identifier taken from task_params.")

    samples_requested: int = Field(..., description="Designs asked of the sampler.")
    samples_simulated: int = Field(..., description="Designs that reached a successful simulation.")
    feasible_count: int = Field(..., description="Simulated designs meeting every requirement.")

    requirements: List[Requirement] = Field(default_factory=list)
    requirement_satisfaction: Dict[str, float] = Field(
        default_factory=dict, description="Per requirement, fraction of simulated designs meeting it.")

    forced_warnings: List[str] = Field(
        default_factory=list,
        description="Warnings present in EVERY feasible design — an unavoidable penalty, not feedback.")
    min_warning_count: Optional[int] = Field(
        None, description="Fewest warnings any feasible design achieved.")
    warning_frequency: Dict[str, float] = Field(
        default_factory=dict, description="Per warning label, fraction of simulated designs raising it.")
    dead_checks: List[str] = Field(
        default_factory=list,
        description="Declared design checks that never fired across the whole sample.")

    reference_count: int = Field(
        0, description="Designs the task offered as witnesses to its own feasibility.")
    reference_scores: List[float] = Field(
        default_factory=list, description="Score each reference design actually achieved.")
    reference_failures: List[str] = Field(
        default_factory=list,
        description="Reference designs that failed to prove what they were offered to prove.")

    score_ceiling: Optional[float] = Field(
        None, description="Best score observed, over the sample and any reference designs. "
                          "A lower bound: sampling can show a score is reachable, never that "
                          "it is not.")
    feasible_score_floor: Optional[float] = Field(None, description="Worst score among feasible designs.")
    feasible_score_median: Optional[float] = Field(None, description="Median score among feasible designs.")
    entry_reward: Optional[float] = Field(
        None, description="Score gained by going from an invalid response to the worst feasible design.")
    craft_reward: Optional[float] = Field(
        None, description="Score gained by going from the worst feasible design to the best observed.")

    physics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Environment-specific analysis from analyse_physics(), e.g. a thermodynamic ceiling.")

    findings: List[str] = Field(
        default_factory=list, description="Human-readable findings, most severe first.")

    def is_healthy(self) -> bool:
        """True when the audit found no CRITICAL finding."""
        return not any(f.startswith("CRITICAL") for f in self.findings)

    def summary(self) -> str:
        """Readable multi-line summary, suitable for printing to a terminal."""
        lines = [
            "Task feasibility audit — {} / {}".format(self.environment, self.task_id),
            "  sampled {} designs, {} simulated, {} feasible".format(
                self.samples_requested, self.samples_simulated, self.feasible_count),
        ]
        if self.score_ceiling is not None:
            lines.append("  score ceiling {:.4f}".format(self.score_ceiling))
        if self.reference_count:
            lines.append("  {} reference design(s), best {:.4f}{}".format(
                self.reference_count,
                max(self.reference_scores) if self.reference_scores else float("nan"),
                "" if not self.reference_failures
                else " — {} FAILED".format(len(self.reference_failures))))
        if self.entry_reward is not None and self.craft_reward is not None:
            lines.append("  reward budget: entry +{:.3f} vs craft +{:.3f}".format(
                self.entry_reward, self.craft_reward))
        if self.forced_warnings:
            lines.append("  forced warnings: {}".format(", ".join(self.forced_warnings)))
        for key, value in self.physics.items():
            lines.append("  [physics] {}: {}".format(key, value))
        lines.append("  findings:")
        if self.findings:
            lines.extend("    - {}".format(f) for f in self.findings)
        else:
            lines.append("    - none")
        return "\n".join(lines)
