import json
import os
from typing import Any, Dict, List, Optional, Union

import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from mcp_server.tools.market_analyzer import MarketAnalyzer
from mcp_server.tools.rest_countries_client import RestCountriesClient

load_dotenv()

mcp = FastMCP("agentic-market-expansion-advisor")
_rest_client = RestCountriesClient()
_analyzer = MarketAnalyzer(_rest_client)


def _ok(data: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "data": data}


def _error(message: str, details: Any = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"ok": False, "error": {"message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return payload


@mcp.tool()
def get_country_data(country_name: str) -> Dict[str, Any]:
    """Fetch country facts from REST Countries v3.1 (`/name/{name}`); GDP is billions USD from World Bank."""
    try:
        data = _rest_client.get_country_data(country_name)
        return _ok(
            {
                "name": data["name"],
                "region": data["region"],
                "subregion": data.get("subregion"),
                "population": data["population"],
                "gdp": data["gdp"],
                "area": data["area"],
                "languages": data["languages"],
                "cca2": data.get("cca2"),
                "cca3": data.get("cca3"),
            }
        )
    except ValueError as exc:
        return _error(str(exc))
    except requests.RequestException as exc:
        return _error("Failed to reach REST Countries API.", str(exc))
    except Exception as exc:
        return _error("Unexpected error loading country.", str(exc))


@mcp.tool()
def analyze_market_potential(
    country_data: Union[str, Dict[str, Any]],
    product: str = "",
) -> Dict[str, Any]:
    """Score market attractiveness (1–100) for a specific product from a get_country_data-shaped payload."""
    try:
        result = _analyzer.analyze_market_potential(country_data, product)
        return _ok(result)
    except json.JSONDecodeError as exc:
        return _error("country_data must be JSON object string when passed as text.", str(exc))
    except (TypeError, ValueError) as exc:
        return _error("Invalid country_data.", str(exc))
    except Exception as exc:
        return _error("Analysis failed.", str(exc))


@mcp.tool()
def compare_markets(
    list_of_countries: Union[str, List[str]],
    product: str = "",
) -> Dict[str, Any]:
    """Rank countries by product-aware market_score (best first); accepts JSON array string or list."""
    try:
        result = _analyzer.compare_markets(list_of_countries, product)
        return _ok(result)
    except json.JSONDecodeError as exc:
        return _error("list_of_countries must be a JSON array when passed as text.", str(exc))
    except (TypeError, ValueError) as exc:
        return _error("Invalid compare_markets input.", str(exc))
    except requests.RequestException as exc:
        return _error("Upstream API request failed while comparing.", str(exc))
    except Exception as exc:
        return _error("Comparison failed.", str(exc))


@mcp.tool()
def recommend_expansion_targets(
    product: str = "",
    budget_constraint: Optional[str] = "medium",
) -> Dict[str, Any]:
    """Evaluate curated candidates per budget tier (low/medium/high) for a specific product; returns top 3."""
    try:
        result = _analyzer.recommend_expansion_targets(product, budget_constraint)
        return _ok(result)
    except Exception as exc:
        return _error("Recommendation failed.", str(exc))


if __name__ == "__main__":
    mcp.run(transport="stdio")
