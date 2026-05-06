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

        business_signals = self.maps.nearby_search(lat, lng, radius=1500, keyword="retail store")
        residential_signals = self.maps.nearby_search(lat, lng, radius=1500, keyword="apartment")

        walkability_score = int(
            self._clamp(
                20
                + 5 * min(len(amenities["transit_stations"]), 10)
                + 2 * min(len(amenities["restaurants"]), 20)
                + 3 * min(len(amenities["grocery"]), 12)
                + 1.5 * min(len(amenities["parks"]), 10),
                1,
                100,
            )
        )
        population_density = int(
            self._clamp(
                2000 + 180 * len(residential_signals) + 60 * len(amenities["transit_stations"]),
                1200,
                20000,
            )
        )
        foot_traffic_score = int(
            self._clamp(
                (0.45 * walkability_score)
                + (0.25 * min(len(amenities["restaurants"]) * 4, 100))
                + (0.3 * min(len(business_signals) * 4, 100)),
                1,
                100,
            )
        )

        return {
            "name": location,
            "population_density": population_density,
            "walkability": walkability_score,
            "foot_traffic_score": foot_traffic_score,
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
        competitors.sort(
            key=lambda x: (x.get("rating") or 0, x.get("user_ratings_total") or 0),
            reverse=True,
        )
        business_types = sorted(
            {item for comp in competitors for item in comp.get("types", []) if item and item != "point_of_interest"}
        )
        competitor_count = len(competitors)
        density_score = int(self._clamp((competitor_count / 25) * 100, 1, 100))

        return {
            "location": location,
            "competitor_count": competitor_count,
            "business_types": business_types[:12],
            "density_score": density_score,
        }

    def recommend_store_locations(self, city: str, budget_constraint: str = "medium") -> Dict[str, Any]:
        neighborhoods = self.maps.fetch_neighborhoods(city).get("neighborhoods", [])
        budget_factor = self._budget_factor(budget_constraint)

        ranked: List[Dict[str, Any]] = []
        for neighborhood in neighborhoods:
            name = neighborhood.get("name")
            if not name:
                continue

            analysis = self.analyze_neighborhood(f"{name}, {city}")
            competition = self.find_competitors(f"{name}, {city}", radius=1500)

            base_score = (
                analysis["foot_traffic_score"]
                + analysis["walkability"]
                - competition["density_score"]
            )
            adjusted_score = round(base_score * budget_factor, 2)
            ranked.append(
                {
                    "name": name,
                    "coordinates": neighborhood.get("location"),
                    "score": adjusted_score,
                    "reasoning": (
                        f"Strong foot traffic ({analysis['foot_traffic_score']}) and walkability "
                        f"({analysis['walkability']}) with competitor density score "
                        f"{competition['density_score']}."
                    ),
                }
            )

        ranked.sort(key=lambda row: row["score"], reverse=True)
        return {
            "city": city.title(),
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
