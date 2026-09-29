from abc import ABC, abstractmethod

class BaseModelClient(ABC):
    def __init__(self, model_name: str):
        self.model_name = model_name

    @abstractmethod
    def generate_design(self, prompt: str) -> str:
        """
        Takes the full prompt (system + user) and returns the raw string response from the model.
        """
        pass
