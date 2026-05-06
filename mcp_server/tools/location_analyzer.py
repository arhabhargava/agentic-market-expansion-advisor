from typing import Any, Dict, List

from .maps_client import GoogleMapsClient


class LocationAnalyzer:
    """Heuristic location analytics using Google Maps place signals."""

    def __init__(self, maps_client: GoogleMapsClient) -> None:
        self.maps = maps_client

    def analyze_neighborhood(self, location: str) -> Dict[str, Any]:
        geo = self.maps.geocode(location)
        lat = geo["location"]["lat"]
        lng = geo["location"]["lng"]

        amenities = {
            "transit_stations": self.maps.nearby_search(lat, lng, radius=1800, place_type="transit_station"),
            "grocery": self.maps.nearby_search(lat, lng, radius=1800, keyword="grocery"),
            "restaurants": self.maps.nearby_search(lat, lng, radius=1800, place_type="restaurant"),
            "parks": self.maps.nearby_search(lat, lng, radius=1800, place_type="park"),
        }

        business_signals = self.maps.nearby_search(lat, lng, radius=1500, keyword="retail")
        residential_signals = self.maps.nearby_search(lat, lng, radius=1500, keyword="apartment")

        walkability_score = self._clamp(
            10
            + 7 * min(len(amenities["transit_stations"]), 10)
            + 3 * min(len(amenities["restaurants"]), 20)
            + 4 * min(len(amenities["grocery"]), 10)
            + 2 * min(len(amenities["parks"]), 10),
            0,
            100,
        )

        commercial_density_score = self._clamp(5 * min(len(business_signals), 20), 0, 100)
        population_proxy_score = self._clamp(
            50 + 2 * min(len(residential_signals), 25) + min(len(amenities["transit_stations"]), 15),
            0,
            100,
        )

        return {
            "location": location,
            "formatted_address": geo["formatted_address"],
            "coordinates": geo["location"],
            "scores": {
                "population_proxy": population_proxy_score,
                "walkability": walkability_score,
                "commercial_density": commercial_density_score,
            },
            "supporting_metrics": {
                "transit_station_count": len(amenities["transit_stations"]),
                "grocery_count": len(amenities["grocery"]),
                "restaurant_count": len(amenities["restaurants"]),
                "park_count": len(amenities["parks"]),
                "business_count": len(business_signals),
                "residential_count": len(residential_signals),
            },
        }

    def find_competitors(self, location: str, radius: int = 2000) -> Dict[str, Any]:
        geo = self.maps.geocode(location)
        lat = geo["location"]["lat"]
        lng = geo["location"]["lng"]

        competitor_queries = [
            "retail store",
            "shopping mall",
            "department store",
            "grocery store",
        ]

        collected: Dict[str, Dict[str, Any]] = {}
        for query in competitor_queries:
            places = self.maps.nearby_search(lat, lng, radius=radius, keyword=query)
            for place in places:
                place_id = place.get("place_id")
                if place_id and place_id not in collected:
                    collected[place_id] = place

        competitors = list(collected.values())
        competitors.sort(key=lambda x: (x.get("rating") or 0, x.get("user_ratings_total") or 0), reverse=True)

        return {
            "location": location,
            "formatted_address": geo["formatted_address"],
            "search_radius_meters": radius,
            "competitors_found": len(competitors),
            "top_competitors": competitors[:15],
        }

    def recommend_store_locations(self, city: str, budget_constraint: str) -> Dict[str, Any]:
        neighborhoods = self.maps.fetch_neighborhoods(city, limit=10).get("neighborhoods", [])
        budget_factor = self._budget_factor(budget_constraint)

        ranked: List[Dict[str, Any]] = []
        for neighborhood in neighborhoods:
            name = neighborhood.get("name")
            if not name:
                continue

            analysis = self.analyze_neighborhood(f"{name}, {city}")
            competition = self.find_competitors(f"{name}, {city}", radius=1500)

            scores = analysis["scores"]
            competition_penalty = min(competition["competitors_found"] * 2.2, 35)
            market_score = (
                0.45 * scores["population_proxy"]
                + 0.35 * scores["walkability"]
                + 0.2 * scores["commercial_density"]
                - competition_penalty
            )

            adjusted_score = round(market_score * budget_factor, 2)
            ranked.append(
                {
                    "location": name,
                    "city": city,
                    "coordinates": neighborhood.get("location"),
                    "score": adjusted_score,
                    "why": {
                        "population_proxy": scores["population_proxy"],
                        "walkability": scores["walkability"],
                        "commercial_density": scores["commercial_density"],
                        "competition_count": competition["competitors_found"],
                        "budget_factor": budget_factor,
                    },
                }
            )

        ranked.sort(key=lambda row: row["score"], reverse=True)
        return {
            "city": city,
            "budget_constraint": budget_constraint,
            "recommendations": ranked[:3],
            "evaluated_locations": len(ranked),
        }

    @staticmethod
    def _clamp(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))

    @staticmethod
    def _budget_factor(budget_constraint: str) -> float:
        normalized = budget_constraint.strip().lower()
        if normalized in {"low", "tight", "conservative"}:
            return 0.9
        if normalized in {"medium", "moderate", "balanced"}:
            return 1.0
        if normalized in {"high", "flexible", "aggressive"}:
            return 1.08
        return 1.0
