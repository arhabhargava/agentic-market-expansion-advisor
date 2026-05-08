import math
from typing import Any, Dict, List, Optional

import requests

REST_COUNTRIES_BASE = "https://restcountries.com/v3.1"
WORLD_BANK_GDP_URL = "https://api.worldbank.org/v2/country/{cca3}/indicator/NY.GDP.MKTP.CD"


class RestCountriesClient:
    """Fetches country facts from REST Countries; enriches GDP when possible via World Bank."""

    def __init__(self, timeout: int = 25) -> None:
        self.timeout = timeout

    def get_country_data(self, country_name: str) -> Dict[str, Any]:
        name = country_name.strip()
        if not name:
            raise ValueError("country_name must be non-empty.")

        url = f"{REST_COUNTRIES_BASE}/name/{requests.utils.quote(name, safe='')}"
        response = requests.get(url, timeout=self.timeout)
        if response.status_code == 404:
            raise ValueError(f"No country matched '{country_name}'.")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            raise ValueError(f"Unexpected response for '{country_name}'.")

        raw = payload[0]
        return self._normalize_country(raw)

    def _normalize_country(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        names = raw.get("name") or {}
        common_name = names.get("common") or names.get("official") or "Unknown"

        languages_obj = raw.get("languages") or {}
        langs: List[str] = sorted(set(languages_obj.values())) if languages_obj else []

        population = int(raw["population"]) if raw.get("population") is not None else 0
        area = raw.get("area")
        area_f = float(area) if area is not None and not (isinstance(area, float) and math.isnan(area)) else None

        cca3 = raw.get("cca3") or ""
        gdp_bn = self._fetch_latest_gdp_billion_usd(cca3) if cca3 else None

        return {
            "name": common_name,
            "region": raw.get("region") or "Unknown",
            "population": population,
            "gdp": gdp_bn,
            "area": area_f,
            "languages": langs,
            "cca2": raw.get("cca2"),
            "cca3": cca3,
            "subregion": raw.get("subregion"),
        }

    def _fetch_latest_gdp_billion_usd(self, cca3: str) -> Optional[float]:
        """World Bank nominal GDP (current USD); returns billions USD."""
        url = WORLD_BANK_GDP_URL.format(cca3=requests.utils.quote(cca3, safe=""))
        try:
            r = requests.get(
                url,
                params={"format": "json", "per_page": 20},
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, list) or len(data) < 2:
                return None
            rows = data[1]
            if not isinstance(rows, list):
                return None
            for row in rows:
                val = row.get("value")
                if val is not None:
                    try:
                        return round(float(val) / 1_000_000_000.0, 2)
                    except (TypeError, ValueError):
                        continue
        except requests.RequestException:
            return None
        return None
