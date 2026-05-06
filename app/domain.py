"""Value types shared across the app: Marker, Bbox.

These are the names from CONTEXT.md. Keep them small — anything that
isn't truly part of "what is a marker" or "what is a bbox" belongs
elsewhere.
"""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field


class Marker(BaseModel):
    """One geographically-located object. Source-agnostic."""

    id: str
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    props: dict[str, Any] = Field(default_factory=dict)


class MarkerWithSource(Marker):
    """A marker plus the dataset label it came from. Used in API responses."""

    dataset: str


@dataclass(frozen=True)
class Bbox:
    """A WGS84 bounding box. Frozen so it can be hashed / compared."""

    south: float
    west: float
    north: float
    east: float

    def __post_init__(self) -> None:
        if not (-90.0 <= self.south <= self.north <= 90.0):
            raise ValueError("bbox: south must be <= north and both in [-90, 90]")
        if not (-180.0 <= self.west <= self.east <= 180.0):
            raise ValueError("bbox: west must be <= east and both in [-180, 180]")

    @classmethod
    def parse(cls, s: str) -> "Bbox":
        """Parse 'south,west,north,east'. Raises ValueError on bad input."""
        parts = s.split(",")
        if len(parts) != 4:
            raise ValueError("bbox must be four comma-separated floats")
        try:
            nums = [float(p) for p in parts]
        except ValueError as e:
            raise ValueError("bbox values must be floats") from e
        return cls(*nums)

    def contains(self, lat: float, lon: float) -> bool:
        return self.south <= lat <= self.north and self.west <= lon <= self.east

    def as_overpass(self) -> str:
        """Format for Overpass query injection: 's,w,n,e'."""
        return f"{self.south},{self.west},{self.north},{self.east}"


# Amsterdam-stadsdelen, bewust zonder Weesp (Weesp domineert BGT-data anders).
AMSTERDAM = Bbox(south=52.295, west=4.745, north=52.430, east=5.020)
