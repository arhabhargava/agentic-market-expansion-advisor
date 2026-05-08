"""
Agentic Market Expansion Advisor — LangChain + MCP implementation.

Architecture:
  - MCP server (mcp_server/server.py) is spawned per request via stdio transport
  - langchain-mcp-adapters discovers its tools and proxies them as LangChain BaseTool objects
  - ChatAnthropic + LangGraph create_react_agent drives the ReAct agentic loop
  - Tool responses are parsed from the agent's message history for structured result assembly
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional, TypedDict

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, SystemMessagePromptTemplate
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

load_dotenv()

MODEL_DEFAULT = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

RecommendationItem = TypedDict(
    "RecommendationItem",
    {
        "country": str,
        "score": float,
        "population": int,
        "gdp_bn": Optional[float],
        "region": str,
        "reasoning": str,
        "product_fit": Optional[Dict[str, Any]],
    },
)

# ── ReAct prompt template ─────────────────────────────────────────────────────

_SYSTEM_TEXT = (
    "You are a senior market expansion strategist. Use the tools provided to analyze countries "
    "for product-market fit. Always call compare_markets first to rank all countries at once, "
    "then use get_country_data and analyze_market_potential for any country that needs deeper "
    "analysis. After all tool calls, cite specific GDP figures and population sizes in your "
    "Final Answer and explain why the top country ranked first.\n\n"
    "Scoring: scores are 1-100. Population, GDP, political stability, and density are weighted "
    "differently per product (luxury weights GDP heavily; FMCG weights population; SaaS rewards "
    "English-speaking high-income economies).\n\n"
    "When calling compare_markets, pass list_of_countries as a JSON array, e.g. "
    '["Germany", "France"].'
)

PROMPT = ChatPromptTemplate.from_messages([
    SystemMessagePromptTemplate.from_template(_SYSTEM_TEXT),
    MessagesPlaceholder(variable_name="messages"),
])


# ── State extraction from message history ────────────────────────────────────

def _extract_state(messages: list) -> Dict[str, Any]:
    """
    Rebuild analysis state and reasoning chain from the agent's message history.

    Pairs AIMessage.tool_calls (inputs Claude sent) with ToolMessage results
    using tool_call_id, so each reasoning step shows the full input → output.
    Format: "Called tool_name({'arg': 'val'}) → result_summary"
    """
    state: Dict[str, Any] = {
        "country_data": {},
        "analyses": {},
        "ranked": [],
        "reasoning_chain": [],
    }

    # Build a lookup: tool_call_id -> (tool_name, args_dict)
    call_inputs: Dict[str, tuple] = {}
    for msg in messages:
        if isinstance(msg, AIMessage):
            for tc in getattr(msg, "tool_calls", []) or []:
                call_inputs[tc["id"]] = (tc["name"], tc.get("args") or {})

    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue

        tool_call_id = getattr(msg, "tool_call_id", None)
        tool_name, tool_args = call_inputs.get(tool_call_id, (getattr(msg, "name", "unknown"), {}))

        try:
            payload = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
        except (json.JSONDecodeError, TypeError):
            payload = {}

        ok = isinstance(payload, dict) and payload.get("ok")
        data = payload.get("data") or {} if ok else {}

        # Build a compact, human-readable input summary
        if tool_args:
            args_str = ", ".join(f"{k}={json.dumps(v)}" for k, v in tool_args.items())
        else:
            args_str = ""

        # Build result summary and update state
        if tool_name == "get_country_data":
            cname = data.get("name")
            if cname:
                state["country_data"][cname] = data
                result_summary = f"ok — {cname}, pop {data.get('population', 'N/A'):,}, GDP ${data.get('gdp') or 'N/A'}B" if isinstance(data.get('population'), int) else f"ok — {cname}"
            else:
                result_summary = "error — country not found"

        elif tool_name == "analyze_market_potential":
            cname = data.get("country")
            factors = data.get("factors", {})
            if cname:
                state["analyses"][cname] = data
                if cname not in state["country_data"]:
                    state["country_data"][cname] = {
                        "name": cname,
                        "population": factors.get("population", 0),
                        "gdp": factors.get("gdp_bn"),
                        "region": factors.get("region", ""),
                    }
                result_summary = f"score {data.get('market_score')}/100, {data.get('potential_rating')} potential"
            else:
                result_summary = "error"

        elif tool_name == "compare_markets":
            ranked = data.get("ranked", [])
            state["ranked"] = ranked
            # Populate country_data so recommendation cards have population/GDP/region
            for r in ranked:
                cname = r.get("country")
                if cname and cname not in state["country_data"]:
                    state["country_data"][cname] = {
                        "name": cname,
                        "population": r.get("population", 0),
                        "gdp": r.get("gdp_bn"),
                        "region": r.get("region", ""),
                    }
            top = ranked[0] if ranked else None
            result_summary = (
                f"{len(ranked)} countries ranked — top: {top['country']} ({top['market_score']}/100)"
                if top else f"{len(ranked)} ranked"
            )

        elif tool_name == "recommend_expansion_targets":
            recs = data.get("recommendations", [])
            if not state["ranked"] and recs:
                for r in recs:
                    state["ranked"].append({
                        "country": r.get("country"),
                        "market_score": r.get("market_score"),
                        "potential_rating": r.get("potential_rating"),
                        "product_fit_analysis": r.get("product_fit_analysis"),
                    })
                    cname = r.get("country")
                    if cname and cname not in state["country_data"]:
                        state["country_data"][cname] = r.get("summary", {})
            result_summary = f"{len(recs)} targets returned"

        else:
            result_summary = "ok" if ok else "error"

        step = f"Called {tool_name}({args_str}) → {result_summary}"
        state["reasoning_chain"].append(step)

    return state


# ── Result assembly ───────────────────────────────────────────────────────────

def _score_to_display(market_score: int) -> float:
    return round(min(10.0, max(1.0, market_score / 10.0)), 1)


def _build_recommendations(
    countries_requested: List[str], state: Dict[str, Any]
) -> List[RecommendationItem]:
    items: List[RecommendationItem] = []

    if state["ranked"]:
        for row in state["ranked"]:
            cname = row.get("country")
            if not cname:
                continue
            facts = state["country_data"].get(cname, {})
            ms = int(row.get("market_score") or 0)
            pfa = row.get("product_fit_analysis") or {}
            bonuses = "; ".join(pfa.get("bonuses_applied") or []) or "standard scoring"
            reasoning = (
                f"Ranked by product-market fit (score {ms}, {row.get('potential_rating', '')}). "
                f"{pfa.get('rationale', '')} {bonuses}."
            ).strip()
            items.append(RecommendationItem(
                country=cname,
                score=_score_to_display(ms),
                population=int(facts.get("population") or 0),
                gdp_bn=facts.get("gdp"),
                region=str(facts.get("region") or ""),
                reasoning=reasoning,
                product_fit=pfa or None,
            ))
        return items

    # Fallback: merge per-country get_country_data + analyze_market_potential pairs
    for c in countries_requested:
        data = state["country_data"].get(c) or state["country_data"].get(c.title())
        an = state["analyses"].get(c)
        if not data or not an:
            continue
        ms = int(an.get("market_score", 50))
        pfa = an.get("product_fit_analysis") or {}
        bonuses = "; ".join(pfa.get("bonuses_applied") or []) or "standard scoring"
        reasoning = (
            f"Product-market fit score {ms} ({an.get('potential_rating', '')}). "
            f"{pfa.get('rationale', '')} {bonuses}."
        ).strip()
        items.append(RecommendationItem(
            country=data["name"],
            score=_score_to_display(ms),
            population=int(data.get("population") or 0),
            gdp_bn=data.get("gdp"),
            region=str(data.get("region") or ""),
            reasoning=reasoning,
            product_fit=pfa or None,
        ))
    items.sort(key=lambda x: x["score"], reverse=True)
    return items


def _product_category(state: Dict[str, Any]) -> str:
    for row in state.get("ranked", []):
        pfa = row.get("product_fit_analysis") or {}
        if pfa.get("product_type"):
            return pfa["product_type"]
    for an in state["analyses"].values():
        pfa = an.get("product_fit_analysis") or {}
        if pfa.get("product_type"):
            return pfa["product_type"]
    return ""


def _parse_countries(countries_input: str) -> List[str]:
    return [p.strip() for p in countries_input.replace(";", ",").split(",") if p.strip()]


# ── Public entry point ────────────────────────────────────────────────────────

async def recommend_markets(
    countries_input: str,
    product: str = "",
    budget: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Spawn the MCP server as a subprocess, acquire its tools via langchain-mcp-adapters,
    and run a LangChain ReAct agent (ChatAnthropic + LangGraph) to analyze countries
    for product-market fit.

    The agent calls all tools through the MCP protocol (stdio transport).
    Results are assembled from the agent's ToolMessage history.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "recommendations": [], "reasoning_chain": [],
            "confidence_score": 0.0, "summary": "",
            "error": "ANTHROPIC_API_KEY is not set.",
        }

    countries = _parse_countries(countries_input)
    if not countries:
        return {
            "recommendations": [], "reasoning_chain": [],
            "confidence_score": 0.0, "summary": "",
            "error": "countries_input must contain at least one country name.",
        }

    budget_label = (budget or "medium").strip().lower()

    try:
        llm = ChatAnthropic(
            model=MODEL_DEFAULT,
            api_key=api_key,
            max_tokens=4096,
        )

        # Spawn mcp_server as a module (-m) so package imports resolve correctly.
        # langchain-mcp-adapters connects over stdio and converts each @mcp.tool()
        # into a LangChain BaseTool.
        mcp_config = {
            "market": {
                "command": sys.executable,
                "args": ["-m", "mcp_server.server"],
                "transport": "stdio",
            }
        }

        client = MultiServerMCPClient(mcp_config)
        tools = await client.get_tools()

        agent = create_react_agent(llm, tools, prompt=PROMPT)

        user_input = (
            f"Analyze these markets for product-market fit.\n\n"
            f"Countries: {', '.join(countries)}\n"
            f"Product: {product or 'general — use balanced scoring'}\n"
            f"Budget tier: {budget_label}\n\n"
            f"Approach:\n"
            f"1. Call compare_markets with list_of_countries as a JSON array and the product "
            f"to get ranked scores in one pass.\n"
            f"2. Call get_country_data + analyze_market_potential on any country needing deeper detail.\n"
            f"3. Optionally call recommend_expansion_targets(product='{product}', "
            f"budget_constraint='{budget_label}') to surface curated global candidates.\n"
            f"4. In your Final Answer, cite GDP figures, population sizes, and scores for each country."
        )

        result = await agent.ainvoke({"messages": [("user", user_input)]})

        messages = result.get("messages", [])
        state = _extract_state(messages)
        summary = str(messages[-1].content) if messages else "Analysis complete."
        recommendations = _build_recommendations(countries, state)
        confidence = 0.9 if state["ranked"] else 0.7

        return {
            "recommendations": recommendations,
            "reasoning_chain": state["reasoning_chain"],
            "confidence_score": confidence,
            "summary": summary,
            "product": product,
            "product_category": _product_category(state),
        }

    except Exception as exc:
        return {
            "recommendations": [],
            "reasoning_chain": [],
            "confidence_score": 0.0,
            "summary": "",
            "error": str(exc),
        }
