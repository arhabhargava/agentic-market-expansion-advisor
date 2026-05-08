# CLAUDE.md — Agentic Market Expansion Advisor

This file is loaded automatically by Claude Code at the start of every session.

## Project Overview

Full-stack AI agent that ranks countries for market expansion. Stack:
- **MCP Server** (`mcp_server/server.py`) — FastMCP, stdio transport, 4 tools
- **LLM Agent** (`backend/agent.py`) — `langchain-mcp-adapters` + LangGraph `create_react_agent` + `ChatAnthropic`
- **API** (`backend/main.py`) — FastAPI, POST /analyze, GET /health, rate limiting, optional API key auth
- **UI** (`frontend/src/App.jsx`) — React 19 + Vite + Tailwind CSS v3 + react-markdown

## Key Architecture Rules

1. **MCP server is spawned per request** via `MultiServerMCPClient` (langchain-mcp-adapters) using `sys.executable` and `-m mcp_server.server` (stdio transport).
2. **Tools are discovered dynamically** — `client.get_tools()` returns LangChain `BaseTool` objects proxied from the live MCP server. No hardcoded tool schemas in `agent.py`.
3. **LangGraph drives the loop** — `create_react_agent(llm, tools, prompt=PROMPT)` from `langgraph.prebuilt`. No manual tool-calling loop.
4. **State and reasoning are extracted post-run** — `_extract_state(messages)` pairs `AIMessage.tool_calls` (inputs Claude sent) with `ToolMessage` results via `tool_call_id`. This builds both structured recommendations and a `reasoning_chain` list formatted as `"Called tool_name(args) → result_summary"` — shown in the UI's Tool Calls panel. No global mutable state.
5. **Prompt uses `ChatPromptTemplate`** with `SystemMessagePromptTemplate` + `MessagesPlaceholder` — proper LangChain prompt engineering, not a plain string.
6. **Security is layered in `main.py`**: rate limiting (slowapi, 5/min per IP), configurable CORS (`ALLOWED_ORIGINS` env var), optional API key auth (`API_KEY` env var → `X-API-Key` header).

## Environment

```
python: .venv/bin/python3   (always use venv)
node:   system node (18+)
ports:  backend=8000, frontend=5173
```

Copy `.env.example` to `.env` and fill in values:
```
ANTHROPIC_API_KEY=...          # required
FASTAPI_PORT=8000              # optional
ANTHROPIC_MODEL=claude-sonnet-4-6  # optional
ALLOWED_ORIGINS=*              # optional; restrict to frontend domain in prod
API_KEY=                       # optional; enables X-API-Key auth when set
```

## Running Locally

```bash
# Terminal 1 — backend
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev
```

The MCP server is spawned automatically per request — do NOT start it manually.

## Common Commands

```bash
# Smoke-test the full agent
source .venv/bin/activate
python -c "import asyncio; from backend.agent import recommend_markets; print(asyncio.run(recommend_markets('Germany, France', 'saas', 'high')))"

# Smoke-test MCP server tools directly (standalone)
source .venv/bin/activate
python mcp_server/client_smoke_test.py

# Install Python deps
source .venv/bin/activate && pip install -r requirements.txt

# Install frontend deps
cd frontend && npm install
```

## File Map

| File | Purpose |
|------|---------|
| `backend/agent.py` | MCP client, LangGraph agent, state extraction, result assembly |
| `backend/main.py` | FastAPI — rate limiting, CORS, auth, input validation |
| `mcp_server/server.py` | FastMCP — exposes 4 `@mcp.tool()` functions via stdio |
| `mcp_server/tools/market_analyzer.py` | Product profiles + scoring engine |
| `mcp_server/tools/rest_countries_client.py` | REST Countries + World Bank API client |
| `frontend/src/App.jsx` | Single-page React UI with react-markdown summary rendering |
| `frontend/tailwind.config.js` | Material Design color tokens + custom spacing |
| `.env.example` | Template for all environment variables |
| `VIDEO_SCRIPT.md` | Section-by-section video presentation script |

## Product Profiles

Defined in `mcp_server/tools/market_analyzer.py` → `PRODUCT_PROFILES`.
Keys: `keywords`, `weight_population`, `weight_gdp`, `weight_stability`, `weight_density`, `english_bonus`, `high_income_bonus`, `high_income_threshold_bn`, `label`, `fit_rationale`.
All four weights must sum to 1.0.

To add a profile: edit `PRODUCT_PROFILES` only — no other files need changes.

## Adding an MCP Tool

1. Implement logic in `mcp_server/tools/market_analyzer.py`
2. Add `@mcp.tool()` function in `mcp_server/server.py`

The agent discovers new tools automatically via `client.get_tools()` — no changes to `agent.py` required.

## Known Constraints

- `mcp==1.27.0` requires `anyio>=4.5`; `langchain-core>=0.3` is compatible — do NOT pin `anyio<4`
- CORS: `allow_origins=["*"]` is the dev default — do not add `allow_credentials=True` with wildcard origin (Starlette rejects it)
- Timeout: `/analyze` has a 120s `asyncio.wait_for` — World Bank GDP lookups can be slow
- REST Countries API: use full English country names (`South Korea` not `Korea`, `United States` not `USA`)
- MCP server must be run as a module (`-m mcp_server.server`) so that relative imports in `tools/` resolve — both `mcp_server/__init__.py` and `mcp_server/tools/__init__.py` must exist
