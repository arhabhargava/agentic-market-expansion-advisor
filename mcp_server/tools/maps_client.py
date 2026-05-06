import os
from typing import Any, Dict, List, Optional

import requests


class GoogleMapsClient:
    """Google Maps wrapper with realistic mock fallback."""

    GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
    PLACES_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    MAJOR_CITY_NEIGHBORHOODS: Dict[str, Dict[str, Any]] = {
        "new york": {
            "center": {"lat": 40.7128, "lng": -74.0060},
            "neighborhoods": [
                {"name": "Chelsea", "lat": 40.7465, "lng": -74.0014},
                {"name": "SoHo", "lat": 40.7233, "lng": -74.0030},
                {"name": "Williamsburg", "lat": 40.7081, "lng": -73.9571},
                {"name": "Upper West Side", "lat": 40.7870, "lng": -73.9754},
                {"name": "Astoria", "lat": 40.7644, "lng": -73.9235},
            ],
        },
        "chicago": {
            "center": {"lat": 41.8781, "lng": -87.6298},
            "neighborhoods": [
                {"name": "River North", "lat": 41.8924, "lng": -87.6340},
                {"name": "Wicker Park", "lat": 41.9088, "lng": -87.6796},
                {"name": "West Loop", "lat": 41.8827, "lng": -87.6475},
                {"name": "Lincoln Park", "lat": 41.9250, "lng": -87.6493},
                {"name": "South Loop", "lat": 41.8604, "lng": -87.6256},
            ],
        },
        "san francisco": {
            "center": {"lat": 37.7749, "lng": -122.4194},
            "neighborhoods": [
                {"name": "Mission District", "lat": 37.7599, "lng": -122.4148},
                {"name": "SoMa", "lat": 37.7786, "lng": -122.4059},
                {"name": "Nob Hill", "lat": 37.7930, "lng": -122.4162},
                {"name": "Sunset District", "lat": 37.7534, "lng": -122.4944},
                {"name": "Marina District", "lat": 37.8037, "lng": -122.4368},
            ],
        },
        "los angeles": {
            "center": {"lat": 34.0522, "lng": -118.2437},
            "neighborhoods": [
                {"name": "Hollywood", "lat": 34.0983, "lng": -118.3267},
                {"name": "Downtown LA", "lat": 34.0407, "lng": -118.2468},
                {"name": "Silver Lake", "lat": 34.0865, "lng": -118.2702},
                {"name": "Santa Monica", "lat": 34.0195, "lng": -118.4912},
                {"name": "Culver City", "lat": 34.0211, "lng": -118.3965},
            ],
        },
        "seattle": {
            "center": {"lat": 47.6062, "lng": -122.3321},
            "neighborhoods": [
                {"name": "Capitol Hill", "lat": 47.6231, "lng": -122.3193},
                {"name": "Ballard", "lat": 47.6687, "lng": -122.3868},
                {"name": "South Lake Union", "lat": 47.6225, "lng": -122.3382},
                {"name": "Fremont", "lat": 47.6513, "lng": -122.3493},
                {"name": "Queen Anne", "lat": 47.6376, "lng": -122.3561},
            ],
        },
    }

    def __init__(self, api_key: Optional[str] = None, timeout: int = 20) -> None:
        self.api_key = api_key or os.getenv("GOOGLE_MAPS_API_KEY")
        self.timeout = timeout

    def geocode(self, address: str) -> Dict[str, Any]:
        city_key = self._normalize_city(address)
        if city_key in self.MAJOR_CITY_NEIGHBORHOODS:
            center = self.MAJOR_CITY_NEIGHBORHOODS[city_key]["center"]
            return {
                "formatted_address": address.title(),
                "location": center,
                "place_id": f"mock-{city_key}-center",
                "types": ["locality"],
                "address_components": [],
            }
        if not self.api_key:
            raise ValueError(
                f"City '{address}' is not supported in mock mode. Add GOOGLE_MAPS_API_KEY for live geocoding."
            )

        response = requests.get(
            self.GEOCODE_URL,
            params={"address": address, "key": self.api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "OK" or not payload.get("results"):
            raise ValueError(f"Geocoding failed for '{address}': {payload.get('status')}")

        top = payload["results"][0]
        loc = top["geometry"]["location"]
        return {
            "formatted_address": top.get("formatted_address"),
            "location": {"lat": loc["lat"], "lng": loc["lng"]},
            "place_id": top.get("place_id"),
            "types": top.get("types", []),
            "address_components": top.get("address_components", []),
        }

    def nearby_search(
        self,
        lat: float,
        lng: float,
        radius: int = 2000,
        keyword: Optional[str] = None,
        place_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not self.api_key:
            return self._mock_nearby_search(lat, lng, keyword=keyword, place_type=place_type)

        params: Dict[str, Any] = {
            "location": f"{lat},{lng}",
            "radius": radius,
            "key": self.api_key,
        }
        if keyword:
            params["keyword"] = keyword
        if place_type:
            params["type"] = place_type

        response = requests.get(self.PLACES_NEARBY_URL, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") not in {"OK", "ZERO_RESULTS"}:
            raise ValueError(f"Nearby search failed: {payload.get('status')}")

        return self._normalize_places(payload.get("results", []))

    def fetch_neighborhoods(self, city: str) -> Dict[str, Any]:
        city_key = self._normalize_city(city)
        if city_key not in self.MAJOR_CITY_NEIGHBORHOODS:
            raise ValueError(
                f"Unsupported city '{city}'. Supported cities: {', '.join(sorted(self.MAJOR_CITY_NEIGHBORHOODS.keys()))}."
            )

        city_data = self.geocode(city)
        center = city_data["location"]
        seed = self.MAJOR_CITY_NEIGHBORHOODS[city_key]["neighborhoods"]
        neighborhoods = [
            {
                "name": item["name"],
                "location": {"lat": item["lat"], "lng": item["lng"]},
            }
            for item in seed
        ]

        return {
            "city": city.title(),
            "city_center": center,
            "neighborhoods": neighborhoods,
            "count": len(neighborhoods),
        }

    @staticmethod
    def _normalize_places(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for place in results:
            geo = place.get("geometry", {}).get("location", {})
            normalized.append(
                {
                    "name": place.get("name"),
                    "place_id": place.get("place_id"),
                    "address": place.get("formatted_address") or place.get("vicinity"),
                    "location": {"lat": geo.get("lat"), "lng": geo.get("lng")},
                    "rating": place.get("rating"),
                    "user_ratings_total": place.get("user_ratings_total"),
                    "price_level": place.get("price_level"),
                    "types": place.get("types", []),
                }
            )
        return normalized

    @staticmethod
    def _normalize_city(city: str) -> str:
        return city.strip().lower()

    def _mock_nearby_search(
        self, lat: float, lng: float, keyword: Optional[str] = None, place_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        token = (keyword or place_type or "business").lower()
        base_count = (abs(int(lat * 100)) + abs(int(lng * 100))) % 8 + 6
        if "retail" in token or "store" in token or "shopping" in token:
            count = base_count + 4
            place_category = "store"
        elif "transit" in token:
            count = max(base_count - 1, 4)
            place_category = "transit_station"
        elif "restaurant" in token:
            count = base_count + 2
            place_category = "restaurant"
        else:
            count = base_count
            place_category = "point_of_interest"

        return [
            {
                "name": f"Mock {place_category.title()} {idx + 1}",
                "place_id": f"mock-{place_category}-{idx + 1}-{int(abs(lat) * 1000)}",
                "address": "Mock Address",
                "location": {"lat": lat + (idx * 0.001), "lng": lng - (idx * 0.001)},
                "rating": round(3.6 + ((idx % 7) * 0.18), 1),
                "user_ratings_total": 30 + idx * 11,
                "price_level": (idx % 4) + 1,
                "types": [place_category, "point_of_interest"],
            }
            for idx in range(count)
        ]
