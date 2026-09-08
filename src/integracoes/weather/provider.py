from abc import ABC, abstractmethod
from .models import WeatherBatch, WeatherSite

class WeatherProvider(ABC):
    """Implement fetch with interval-start data; solar knows no API schema."""
    name = 'unspecified'

    @abstractmethod
    def fetch(self, start, site: WeatherSite, periods=96) -> WeatherBatch:
        """Return validated weather with at least the requested horizon."""
        raise NotImplementedError
