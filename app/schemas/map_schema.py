from pydantic import BaseModel,Field
from typing import Optional, List 



class GeoPoint(BaseModel):
    lat: float
    lng: float
    label: Optional[str] = None


class NearbyPlace(BaseModel):
    provider: str = "google_places"
    place_id: Optional[str] = None
    name: str
    category: Optional[str] = None
    address: Optional[str] = None
    rating: Optional[float] = None
    user_rating_count: Optional[int] = None
    location: GeoPoint
    maps_url: Optional[str] = None
    
    
class GeoInsights(BaseModel):

    avg_distance_km: float = 0.0
    max_distance_km: float = 0.0

    walkability_score: float = 0.0
    accessibility_score: float = 0.0

    clustering_score: float = 0.0  # lieux proches entre eux

    travel_efficiency: float = 0.0  # optimisation parcours

    recommendation_hint: str = "neutral"

    prefer_nearby_places: bool = True
    avoid_long_travel: bool = False
    

class RouteInfo(BaseModel):
    origin_label: Optional[str] = None
    destination_label: Optional[str] = None
    distance_meters: Optional[int] = None
    duration_seconds: Optional[int] = None
    travel_mode: str = "DRIVE"
    
    
class GeoContext(BaseModel):

    available: bool = False

    user_location: Optional[GeoPoint] = None
    destination_location: Optional[GeoPoint] = None

    nearby_places: List[NearbyPlace] = Field(default_factory=list)
    
    route_matrix: List[RouteInfo] = Field(default_factory=list)

    insights: GeoInsights = GeoInsights()

    max_travel_time_minutes: int = 25