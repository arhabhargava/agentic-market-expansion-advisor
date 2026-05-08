import json
import math
from typing import Any, Dict, List, Optional, Union

from .rest_countries_client import RestCountriesClient

JsonDict = Dict[str, Any]


def _coerce_dict(value: Union[str, JsonDict]) -> JsonDict:
    if isinstance(value, str):
        return json.loads(value)
    if isinstance(value, dict):
        return value
    raise TypeError("country_data must be an object or JSON string.")


def _coerce_country_list(value: Union[str, List[str]]) -> List[str]:
    if isinstance(value, str):
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            raise TypeError("list_of_countries must be a JSON array.")
        return [str(x).strip() for x in parsed if str(x).strip()]
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    raise TypeError("list_of_countries must be a list or JSON array string.")


STABILITY_BY_REGION: Dict[str, float] = {
    "Europe": 0.22,
    "Asia": 0.15,
    "Africa": 0.08,
    "Americas": 0.16,
    "Oceania": 0.18,
    "Antarctic": 0.05,
}

HIGH_GROWTH_SUBREGIONS = {
    "South-Eastern Asia",
    "Southern Asia",
    "Eastern Asia",
    "Central America",
    "South America",
    "Western Africa",
    "Eastern Africa",
}

BUDGET_CANDIDATES: Dict[str, List[str]] = {
    "low": ["Philippines", "Vietnam", "India", "Indonesia", "Poland"],
    "medium": ["Mexico", "Germany", "Spain", "Australia", "Canada"],
    "high": ["United States", "Japan", "United Kingdom", "France", "Singapore"],
}

# Product profiles: scoring weights + bonuses per category
PRODUCT_PROFILES: Dict[str, Dict[str, Any]] = {
    "luxury": {
        "keywords": ["luxury", "premium", "high-end", "designer", "watch", "jewel", "yacht", "supercar", "couture"],
        "weight_population": 0.12,
        "weight_gdp": 0.56,
        "weight_stability": 0.26,
        "weight_density": 0.06,
        "english_bonus": 0,
        "high_income_bonus": 18,
        "high_income_threshold_bn": 500,
        "label": "Luxury / Premium Goods",
        "fit_rationale": "Purchasing power matters more than market size; high-GDP, stable economies dominate.",
    },
    "saas": {
        "keywords": ["saas", "software", "platform", "app", "tech", "digital", "cloud", "ai", "data", "api", "b2b", "crm", "erp"],
        "weight_population": 0.18,
        "weight_gdp": 0.42,
        "weight_stability": 0.25,
        "weight_density": 0.15,
        "english_bonus": 14,
        "high_income_bonus": 8,
        "high_income_threshold_bn": 300,
        "label": "Software / SaaS",
        "fit_rationale": "English-speaking, high-GDP markets accelerate SaaS adoption and reduce onboarding friction.",
    },
    "fmcg": {
        "keywords": ["fmcg", "consumer goods", "food", "beverage", "snack", "household", "grocery", "packaged", "drink", "cpg"],
        "weight_population": 0.55,
        "weight_gdp": 0.18,
        "weight_stability": 0.15,
        "weight_density": 0.12,
        "english_bonus": 0,
        "high_income_bonus": 0,
        "high_income_threshold_bn": 0,
        "label": "FMCG / Consumer Goods",
        "fit_rationale": "Volume-driven; large populations and high density drive FMCG sales regardless of income level.",
    },
    "healthcare": {
        "keywords": ["healthcare", "pharma", "medical", "health", "medicine", "hospital", "biotech", "drug", "wellness", "diagnostic"],
        "weight_population": 0.25,
        "weight_gdp": 0.42,
        "weight_stability": 0.28,
        "weight_density": 0.05,
        "english_bonus": 5,
        "high_income_bonus": 12,
        "high_income_threshold_bn": 400,
        "label": "Healthcare / Pharma",
        "fit_rationale": "High-income, politically stable markets with regulatory clarity are optimal for healthcare.",
    },
    "education": {
        "keywords": ["education", "edtech", "learning", "school", "university", "training", "course", "e-learning", "tutoring"],
        "weight_population": 0.42,
        "weight_gdp": 0.24,
        "weight_stability": 0.20,
        "weight_density": 0.14,
        "english_bonus": 16,
        "high_income_bonus": 0,
        "high_income_threshold_bn": 0,
        "label": "Education / EdTech",
        "fit_rationale": "Large young populations and English fluency are the primary EdTech growth levers.",
    },
    "finance": {
        "keywords": ["finance", "fintech", "banking", "payment", "insurance", "investment", "lending", "crypto", "wallet", "wealth"],
        "weight_population": 0.18,
        "weight_gdp": 0.50,
        "weight_stability": 0.28,
        "weight_density": 0.04,
        "english_bonus": 8,
        "high_income_bonus": 14,
        "high_income_threshold_bn": 400,
        "label": "Finance / Fintech",
        "fit_rationale": "Strong financial infrastructure in stable, high-GDP markets accelerates fintech adoption.",
    },
    "ecommerce": {
        "keywords": ["ecommerce", "e-commerce", "marketplace", "shop", "retail", "fashion", "clothing", "apparel", "store"],
        "weight_population": 0.46,
        "weight_gdp": 0.28,
        "weight_stability": 0.14,
        "weight_density": 0.12,
        "english_bonus": 5,
        "high_income_bonus": 5,
        "high_income_threshold_bn": 200,
        "label": "E-commerce / Retail",
        "fit_rationale": "Dense, populous markets with rising GDP create strong e-commerce demand.",
    },
}

DEFAULT_PRODUCT_PROFILE: Dict[str, Any] = {
    "weight_population": 0.32,
    "weight_gdp": 0.28,
    "weight_stability": 0.22,
    "weight_density": 0.18,
    "english_bonus": 0,
    "high_income_bonus": 0,
    "high_income_threshold_bn": 0,
    "label": "General Product",
    "fit_rationale": "Balanced scoring across population size, GDP, regional stability, and market density.",
}


def _detect_product_profile(product: str) -> Dict[str, Any]:
    product_lower = (product or "").strip().lower()
    if not product_lower:
        return DEFAULT_PRODUCT_PROFILE
    for profile in PRODUCT_PROFILES.values():
        for keyword in profile["keywords"]:
            if keyword in product_lower:
                return profile
    return DEFAULT_PRODUCT_PROFILE


class MarketAnalyzer:
    def __init__(self, client: RestCountriesClient) -> None:
        self.client = client

    def analyze_market_potential(
        self, country_data: Union[str, JsonDict], product: str = ""
    ) -> Dict[str, Any]:
        d = _coerce_dict(country_data)
        name = d.get("name") or "Unknown"
        region = str(d.get("region") or "Unknown")
        subregion = d.get("subregion")
        population = int(d.get("population") or 0)
        gdp_b = d.get("gdp")
        languages: List[str] = d.get("languages") or []

        profile = _detect_product_profile(product)

        stability = STABILITY_BY_REGION.get(region, 0.12)
        population_score = min(100.0, 18.0 * math.log10(max(population, 1)))

        area = d.get("area")
        density_score = 0.0
        if isinstance(area, (int, float)) and area and area > 0:
            density = population / float(area)
            density_score = min(100.0, 3.0 * math.log10(max(density, 0.01)))

        gdp_score = 0.0
        if isinstance(gdp_b, (int, float)) and gdp_b and gdp_b > 0:
            gdp_score = min(100.0, 12.0 * math.log10(gdp_b))

        growth_adj = 0.0
        if subregion in HIGH_GROWTH_SUBREGIONS:
            growth_adj = 12.0
        elif subregion == "Northern America":
            growth_adj = 6.0
        elif subregion == "Western Europe":
            growth_adj = 4.0

        raw_score = (
            profile["weight_population"] * population_score
            + profile["weight_gdp"] * gdp_score
            + profile["weight_stability"] * (stability * 100.0)
            + profile["weight_density"] * density_score
            + growth_adj
        )

        # English bonus
        english_bonus = 0
        if profile["english_bonus"] > 0 and "English" in languages:
            english_bonus = profile["english_bonus"]
            raw_score += english_bonus

        # High-income bonus
        high_income_bonus = 0
        threshold = profile["high_income_threshold_bn"]
        if (
            profile["high_income_bonus"] > 0
            and isinstance(gdp_b, (int, float))
            and gdp_b
            and gdp_b > threshold
        ):
            high_income_bonus = profile["high_income_bonus"]
            raw_score += high_income_bonus

        market_score = int(max(1, min(100, round(raw_score))))

        if market_score >= 72:
            potential_rating = "High"
        elif market_score >= 45:
            potential_rating = "Medium"
        else:
            potential_rating = "Low"

        bonuses: List[str] = []
        if english_bonus:
            bonuses.append(f"English-speaking market (+{english_bonus} pts)")
        if high_income_bonus:
            gdp_display = f"${int(gdp_b)}B" if gdp_b else "N/A"
            bonuses.append(f"High-income economy ({gdp_display} GDP) (+{high_income_bonus} pts)")
        if growth_adj:
            bonuses.append(f"High-growth subregion: {subregion} (+{int(growth_adj)} pts)")

        product_fit_analysis = {
            "product_type": profile["label"],
            "rationale": profile["fit_rationale"],
            "bonuses_applied": bonuses,
            "scoring_weights": (
                f"Population {int(profile['weight_population']*100)}% / "
                f"GDP {int(profile['weight_gdp']*100)}% / "
                f"Stability {int(profile['weight_stability']*100)}% / "
                f"Density {int(profile['weight_density']*100)}%"
            ),
        }

        return {
            "country": name,
            "market_score": market_score,
            "potential_rating": potential_rating,
            "product_fit_analysis": product_fit_analysis,
            "factors": {
                "population": population,
                "gdp_bn": gdp_b,
                "region": region,
                "region_stability_weight": stability,
                "growth_potential_adjustment": growth_adj,
            },
        }

    def compare_markets(
        self, list_of_countries: Union[str, List[str]], product: str = ""
    ) -> Dict[str, Any]:
        names = _coerce_country_list(list_of_countries)
        if not names:
            raise ValueError("list_of_countries is empty.")

        ranked: List[Dict[str, Any]] = []
        errors: List[Dict[str, str]] = []

        for cn in names:
            try:
                data = self.client.get_country_data(cn)
                analysis = self.analyze_market_potential(data, product)
                ranked.append(
                    {
                        "country": analysis["country"],
                        "market_score": analysis["market_score"],
                        "potential_rating": analysis["potential_rating"],
                        "product_fit_analysis": analysis["product_fit_analysis"],
                        "population": data.get("population", 0),
                        "gdp_bn": data.get("gdp"),
                        "region": data.get("region", ""),
                    }
                )
            except ValueError as exc:
                errors.append({"country": cn, "message": str(exc)})
            except Exception as exc:
                errors.append({"country": cn, "message": str(exc)})

        ranked.sort(key=lambda x: x["market_score"], reverse=True)
        return {"ranked": ranked, "errors": errors}

    def recommend_expansion_targets(
        self, product: str = "", budget_constraint: Optional[str] = "medium"
    ) -> Dict[str, Any]:
        key = (budget_constraint or "medium").strip().lower()
        if key not in BUDGET_CANDIDATES:
            key = "medium"

        candidates = BUDGET_CANDIDATES[key]
        enriched: List[Dict[str, Any]] = []
        errors: List[Dict[str, str]] = []

        for cn in candidates:
            try:
                data = self.client.get_country_data(cn)
                analysis = self.analyze_market_potential(data, product)
                enriched.append({"data": data, "analysis": analysis})
            except ValueError as exc:
                errors.append({"country": cn, "message": str(exc)})
            except Exception as exc:
                errors.append({"country": cn, "message": str(exc)})

        enriched.sort(key=lambda x: int(x["analysis"]["market_score"]), reverse=True)
        top = enriched[:3]

        profile = _detect_product_profile(product)
        recommendations: List[Dict[str, Any]] = []
        for idx, row in enumerate(top, start=1):
            data = row["data"]
            analysis = row["analysis"]
            pfa = analysis["product_fit_analysis"]
            bonuses_str = "; ".join(pfa["bonuses_applied"]) if pfa["bonuses_applied"] else "no special bonuses"
            reasoning = (
                f"Ranked #{idx} for `{profile['label']}` in `{key}` budget tier "
                f"(score {analysis['market_score']}, {analysis['potential_rating']} potential). "
                f"{pfa['rationale']} Applied: {bonuses_str}."
            )
            recommendations.append(
                {
                    "country": analysis["country"],
                    "market_score": analysis["market_score"],
                    "potential_rating": analysis["potential_rating"],
                    "product_fit_analysis": pfa,
                    "reasoning": reasoning,
                    "summary": data,
                }
            )

        return {
            "product": product,
            "budget_constraint": key,
            "candidates_evaluated": candidates,
            "recommendations": recommendations,
            "partial_errors": errors,
        }
