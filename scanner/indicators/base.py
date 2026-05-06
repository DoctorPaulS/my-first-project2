from abc import ABC, abstractmethod
import pandas as pd


class BaseIndicator(ABC):
    def __init__(self, params: dict = None):
        self.params = params or {}

    @abstractmethod
    def score(self, ohlcv: pd.DataFrame) -> tuple[float, str]:
        """
        Calculate indicator score.

        Args:
            ohlcv: DataFrame with columns Open, High, Low, Close, Volume

        Returns:
            (score, reasoning) where score is 0.0–10.0 and reasoning is a
            plain-English sentence explaining what the indicator observed.
        """
