import os
from typing import Any, Dict, List, Optional

import requests


class GoogleMapsClient:
    """Small wrapper around Google Maps Geocoding + Places endpoints."""

    GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
    PLACES_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    PLACES_TEXT_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"

    def __init__(self, api_key: Optional[str] = None, timeout: int = 20) -> None:
        self.api_key = api_key or os.getenv("GOOGLE_MAPS_API_KEY")
        self.timeout = timeout
        if not self.api_key:
            raise ValueError("GOOGLE_MAPS_API_KEY is not configured.")

    def geocode(self, address: str) -> Dict[str, Any]:
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

    def text_search(self, query: str) -> List[Dict[str, Any]]:
        response = requests.get(
            self.PLACES_TEXT_URL,
            params={"query": query, "key": self.api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") not in {"OK", "ZERO_RESULTS"}:
            raise ValueError(f"Text search failed: {payload.get('status')}")

        return self._normalize_places(payload.get("results", []))

    def fetch_neighborhoods(self, city: str, limit: int = 12) -> Dict[str, Any]:
        city_data = self.geocode(city)
        center = city_data["location"]
        query = f"best neighborhoods in {city}"
        candidates = self.text_search(query)

        if not candidates:
            candidates = self.nearby_search(
                center["lat"],
                center["lng"],
                radius=7000,
                keyword="neighborhood",
            )

        neighborhoods = []
        for item in candidates[:limit]:
            loc = item.get("location", {})
            neighborhoods.append(
                {
                    "name": item.get("name"),
                    "place_id": item.get("place_id"),
                    "location": {"lat": loc.get("lat"), "lng": loc.get("lng")},
                    "rating": item.get("rating"),
                    "types": item.get("types", []),
                    "address": item.get("address"),
                }
            )

        return {
            "city": city,
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
