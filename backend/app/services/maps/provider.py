from abc import ABC, abstractmethod
from app.services.maps.schemas import RouteEnrichRequestSegment, SegmentRouteGeometry


class MapsProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier."""
        pass

    @abstractmethod
    async def compute_segment_route(
        self, segment: RouteEnrichRequestSegment
    ) -> SegmentRouteGeometry:
        """Compute or enrich geographic route geometry for a single journey segment."""
        pass
