from typing import Any, Dict

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


@mcp.tool()
def get_location_data(city: str) -> Dict[str, Any]:
    """Return city center and predefined neighborhood coordinates."""
    try:
        data = maps_client.fetch_neighborhoods(city)
        return _ok(data)
    except ValueError as exc:
        return _error("Invalid or unsupported city.", str(exc))
    except Exception as exc:
        return _error("Failed to fetch location data.", str(exc))


@mcp.tool()
def analyze_neighborhood(location: str) -> Dict[str, Any]:
    """Analyze population density, walkability, and foot traffic."""
    try:
        data = analyzer.analyze_neighborhood(location)
        return _ok(data)
    except Exception as exc:
        return _error("Failed to analyze neighborhood.", str(exc))


@mcp.tool()
def find_competitors(location: str) -> Dict[str, Any]:
    """Find nearby retail competitors and density score."""
    try:
        data = analyzer.find_competitors(location)
        return _ok(data)
    except Exception as exc:
        return _error("Failed to find competitors.", str(exc))


@mcp.tool()
def recommend_store_locations(city: str, budget_constraint: str = "medium") -> Dict[str, Any]:
    """Rank top 3 neighborhoods using traffic + walkability - competitor density."""
    try:
        data = analyzer.recommend_store_locations(city=city, budget_constraint=budget_constraint)
        return _ok(data)
    except ValueError as exc:
        return _error("Invalid or unsupported city.", str(exc))
    except Exception as exc:
        return _error("Failed to recommend store locations.", str(exc))


if __name__ == "__main__":
    mcp.run(transport="stdio")
