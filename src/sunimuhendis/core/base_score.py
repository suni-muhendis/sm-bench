from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, Optional
from .types import ScoreResult

class BaseScoreFunction(ABC):
    """
    Base class from which all score functions inherit.
    """

    #: Identifier of this score function, e.g. ``"heat_exchanger_score_v4"``.
    #: Stamped onto every result by ``evaluate()``.
    VERSION: ClassVar[Optional[str]] = None
    
    @abstractmethod
    def calculate_score(
        self, 
        task_params: Dict[str, Any],
        metrics: Dict[str, Any], 
        is_valid: bool = True, 
        error_message: Optional[str] = None
    ) -> ScoreResult:
        """
        Calculates the score from simulator outputs or errors.
        
        Args:
            task_params: Contains the design targets or environment parameters.
            metrics: Metrics returned from simulation (if is_valid=True).
            is_valid: Whether the design or simulation is valid/successful.
            error_message: Message in case of error.
            
        Returns:
            ScoreResult: Normalized and decomposed score object.
        """
        pass
