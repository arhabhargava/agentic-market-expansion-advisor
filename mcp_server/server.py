import json
from typing import Any, Dict, Tuple

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from tools.location_analyzer import LocationAnalyzer
from tools.maps_client import GoogleMapsClient

load_dotenv()

mcp = FastMCP("store-location-optimizer")
maps_client = GoogleMapsClient()
analyzer = LocationAnalyzer(maps_client)


def _ok(data: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "data": data}


def _error(message: str, details: Any = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"ok": False, "error": {"message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return payload


def _parse_budget_payload(raw_budget_constraint: str) -> Tuple[str, str]:
    """
    Accepts plain budget strings ('low', 'medium', 'high') or JSON:
    {"city":"Chicago","budget":"medium"}.
    """
    city = "Chicago"
    budget = raw_budget_constraint
    try:
        parsed = json.loads(raw_budget_constraint)
        if isinstance(parsed, dict):
            city = str(parsed.get("city", city))
            budget = str(parsed.get("budget", budget))
    except json.JSONDecodeError:
        pass
    return city, budget


@mcp.tool()
def get_location_data(city: str) -> Dict[str, Any]:
    """Fetch candidate neighborhoods and city center for a given city."""
    try:
        data = maps_client.fetch_neighborhoods(city)
        return _ok(data)
    except Exception as exc:
        return _error("Failed to fetch location data.", str(exc))


@mcp.tool()
def analyze_neighborhood(location: str) -> Dict[str, Any]:
    """Analyze a neighborhood across population proxy, walkability, and density."""
    try:
        data = analyzer.analyze_neighborhood(location)
        return _ok(data)
    except Exception as exc:
        return _error("Failed to analyze neighborhood.", str(exc))


@mcp.tool()
def find_competitors(location: str) -> Dict[str, Any]:
    """Find nearby competing retail businesses around a location."""
    try:
        data = analyzer.find_competitors(location)
        return _ok(data)
    except Exception as exc:
        return _error("Failed to find competitors.", str(exc))


@mcp.tool()
def recommend_store_locations(budget_constraint: str) -> Dict[str, Any]:
    """
    Rank top 3 locations based on opportunity score and budget constraints.
    `budget_constraint` accepts:
      - plain text ('low', 'medium', 'high')
      - JSON string: {"city":"Chicago","budget":"medium"}
    """
    try:
        city, budget = _parse_budget_payload(budget_constraint)
        data = analyzer.recommend_store_locations(city=city, budget_constraint=budget)
        return _ok(data)
    except Exception as exc:
        return _error("Failed to recommend store locations.", str(exc))


if __name__ == "__main__":
    mcp.run(transport="stdio")
