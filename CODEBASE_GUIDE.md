# Codebase Guide — Agentic Market Expansion Advisor

A plain-English walkthrough of every file, what it does, and how the pieces connect.

---

## The Big Picture

A user types country names into a web form and asks "where should I expand my product?" The system:

1. **React UI** collects the input and sends it to the backend API
2. **FastAPI** receives the request, rate-limits it, and calls the AI agent
3. **LangChain + LangGraph agent** (powered by Claude) reasons through the problem and calls tools
4. **MCP server** runs as a subprocess and exposes those tools over the MCP protocol (stdio)
5. **Tools** hit real external APIs (REST Countries, World Bank) to get live data
6. **Scoring engine** turns raw country facts into a ranked market-fit score
7. Everything flows back up the chain as a structured JSON response with ranked recommendations

---

## Request Flow Diagram

```
User (browser)
    │  POST /analyze { countries, product, budget }
    ▼
frontend/src/App.jsx          ← React UI collects input, renders results
    │
    │  HTTP POST to localhost:8000/analyze
    ▼
backend/main.py               ← FastAPI validates input, rate-limits, checks API key, 120s timeout
    │
    │  calls recommend_markets()
    ▼
backend/agent.py              ← Spawns MCP server via MultiServerMCPClient, runs LangGraph ReAct loop
    │
    │  stdio subprocess (MCP protocol / JSON-RPC) ──────────────────────────┐
    ▼                                                                        │
mcp_server/server.py          ← FastMCP exposes 4 @mcp.tool() functions    │
    │                                                                        │
    │  imports                                                               │
    ├──► mcp_server/tools/rest_countries_client.py  ← HTTP → REST Countries API
    │                                                         + World Bank API
    └──► mcp_server/tools/market_analyzer.py        ← Scoring engine, product profiles
```

---

## File-by-File

---

### `backend/main.py` — The API Gateway

**What it is:** A FastAPI web server. The only thing that touches HTTP from the outside world.

**What it does:**
- Defines one real endpoint: `POST /analyze`
- Validates the incoming request using Pydantic — `countries` must be non-empty, `budget` must be `low`/`medium`/`high` if provided
- Enforces a **rate limit** of 5 requests per minute per IP using `slowapi` — protects Claude API spend
- Optionally enforces **API key auth** via `X-API-Key` header — enabled when `API_KEY` env var is set
- Configures **CORS** from the `ALLOWED_ORIGINS` env var (defaults to `*` in dev, lockable in prod)
- Wraps the agent call in a 120-second timeout (external API calls can be slow)
- Returns the agent's structured result as JSON, or an HTTP error if something fails
- Also exposes `GET /health` — returns `{"status": "ok", "timestamp": "..."}` for uptime checks

**Talks to:** `backend/agent.py` — imports and calls `recommend_markets()`

**Talked to by:** `frontend/src/App.jsx` — the browser fetches `http://localhost:8000/analyze`

---

### `backend/agent.py` — The AI Brain

**What it is:** The core intelligence layer. This is where Claude thinks.

**What it does:**
1. **Spawns the MCP server** as a subprocess using `MultiServerMCPClient` from `langchain-mcp-adapters`. The config passes `sys.executable` and `["-m", "mcp_server.server"]` so it always runs in the active venv. Communication happens over stdio via the MCP protocol (JSON-RPC).
2. **Discovers tools** — calls `client.get_tools()` to get all 4 MCP tools as LangChain `BaseTool` objects. The agent never imports business logic directly; everything comes through MCP.
3. **Runs the ReAct loop** — `create_react_agent` from `langgraph.prebuilt` gives Claude the tools and a `ChatPromptTemplate` prompt. Claude reasons step by step:
   - *"I should call `compare_markets` first to get a ranked list"* → calls tool
   - *"France needs a deeper look"* → calls `get_country_data` then `analyze_market_potential`
   - *"I have enough data, here is my final answer"* → loop ends
4. **Extracts state and reasoning chain** — after the agent finishes, `_extract_state()` walks the message history. It first builds a lookup of `AIMessage.tool_calls` (the inputs Claude sent, keyed by `tool_call_id`), then pairs each `ToolMessage` result with its corresponding input. This produces both structured state (country data, ranked results) and the `reasoning_chain` list in the format `"Called tool_name(args) → result_summary"`.
5. **Assembles the response** — `_build_recommendations()` turns the raw state into a clean ranked list with scores, population, GDP, region, and reasoning text.

**Key constants:**
- `_SYSTEM_TEXT` — the system prompt string giving Claude its role and tool usage strategy
- `PROMPT` — a `ChatPromptTemplate` wrapping `_SYSTEM_TEXT` as a `SystemMessagePromptTemplate` + `MessagesPlaceholder`
- `MODEL_DEFAULT` — reads `ANTHROPIC_MODEL` env var, defaults to `claude-sonnet-4-6`

**Talks to:** `mcp_server/server.py` (subprocess over stdio via MCP protocol)

**Talked to by:** `backend/main.py`

---

### `mcp_server/server.py` — The Tool Server

**What it is:** A standalone FastMCP server that exposes 4 tools over the MCP protocol. It runs as a subprocess — it is never called directly as a Python import by the agent.

**Why it exists separately:** MCP (Model Context Protocol) is an open standard for connecting AI agents to external tools. Running the tools as a server means they're fully decoupled from the agent and can be tested independently, reused by other agents, or swapped out without touching `agent.py`.

**The 4 tools it exposes:**

| Tool | What it does |
|---|---|
| `get_country_data` | Fetches one country's facts: population, GDP (billions USD), area, languages, region |
| `analyze_market_potential` | Given country facts + a product type, returns a score 1–100 and a `High`/`Medium`/`Low` rating |
| `compare_markets` | Takes a list of countries + product, scores all of them, returns ranked |
| `recommend_expansion_targets` | Picks from a curated pool of countries for a budget tier (low/medium/high), returns top 3 |

**Talks to:**
- `mcp_server/tools/rest_countries_client.py` — for country facts
- `mcp_server/tools/market_analyzer.py` — for scoring

**Talked to by:** `backend/agent.py` (spawns it as subprocess, calls tools via MCP protocol)

**Can also be tested directly:** `mcp_server/client_smoke_test.py`

---

### `mcp_server/tools/rest_countries_client.py` — External API Client

**What it is:** A thin HTTP client that wraps two external APIs.

**What it does:**
1. Calls **REST Countries v3.1** (`restcountries.com/v3.1/name/{name}`) — gets a country's population, area, languages, region, 3-letter code (cca3)
2. Uses that cca3 code to call the **World Bank API** for nominal GDP in current USD, then converts it to billions
3. Returns a normalized dict with consistent field names regardless of quirks in the raw API responses

**Talks to:** `https://restcountries.com` and `https://api.worldbank.org` — real live external APIs, no keys required

**Talked to by:** `mcp_server/tools/market_analyzer.py` and `mcp_server/server.py`

---

### `mcp_server/tools/market_analyzer.py` — Scoring Engine

**What it is:** Pure business logic. No HTTP calls, no AI — just math and product knowledge.

**What it does:**

**Product profiles** (`PRODUCT_PROFILES`) — 7 categories (luxury, saas, fmcg, healthcare, education, finance, ecommerce), each with:
- Scoring weights that add up to 1.0 — e.g. luxury weights GDP at 56%, FMCG weights population at 55%
- Bonuses for English-speaking countries or high-income economies
- A label and rationale string explaining why those weights make sense

**`analyze_market_potential(country_data, product)`**
- Detects which product profile applies by keyword-matching the product string
- Calculates sub-scores for population (log scale), GDP (log scale), regional stability (lookup by region), and population density
- Adds growth adjustment for high-growth subregions (Southeast Asia, South America, etc.)
- Applies English/high-income bonuses
- Returns a 1–100 integer score + `High`/`Medium`/`Low` rating + full breakdown

**`compare_markets(countries, product)`**
- Calls `get_country_data` + `analyze_market_potential` for each country
- Sorts results by score, returns ranked list

**`recommend_expansion_targets(product, budget_constraint)`**
- Uses a hardcoded pool per budget tier (e.g. medium = Mexico, Germany, Spain, Australia, Canada)
- Scores all, returns top 3 with full reasoning

**Talked to by:** `mcp_server/server.py`

---

### `frontend/src/App.jsx` — The UI

**What it is:** A single-page React app. Everything visible to the user lives here.

**What it does:**
- **Form** (left column): text area for country names, text input for product, dropdown for budget tier, quick-select product suggestion chips
- **On submit**: POSTs `{ countries, product, budget }` to `http://localhost:8000/analyze`, shows the AI-native loading panel while waiting
- **Loading state**: animated `AgentLoader` component cycles through 6 analysis stages every 2.8 seconds with typing dots and a progressive step list — no generic spinner
- **Results** (right column): renders a `MarketCard` per recommendation — country name, score bar (0–100), population/GDP/region stats, reasoning text, bonus tags
- **Analysis Process** (open by default at the bottom): shows the AI's full markdown-rendered summary (`react-markdown`) and a numbered list of every tool call the agent made in `"Called tool_name(args) → result_summary"` format
- **Error state**: displays the error message if the API call fails

**Key components:**

| Component | Purpose |
|---|---|
| `App` | Root — holds all state, handles form submit |
| `AgentLoader` | AI-native loading panel with stage cycling and typing dots |
| `TypingDots` | Three animated dots indicating active processing |
| `MarketCard` | Renders one country's recommendation card |
| `ScoreBar` | The colored progress bar showing score % |
| `StatBox` | Small box showing one stat (population, GDP, region) |
| `AnalysisProcess` | Open-by-default section with markdown AI summary + tool call log |

**Talks to:** `backend/main.py` at `http://localhost:8000/analyze`

---

### `mcp_server/client_smoke_test.py` — Dev Testing Script

**What it is:** A standalone script for testing the MCP server tools directly, without going through the agent or the API.

**What it does:** Spawns `mcp_server/server.py` as a subprocess (same way the agent does), then calls all 4 tools in sequence and prints the raw JSON responses. Useful for checking that country lookups and scoring work before touching the agent.

**Run it with:**
```bash
source .venv/bin/activate
python mcp_server/client_smoke_test.py
```

---

## Data Shape Flowing Through the System

### What the frontend sends:
```json
{ "countries": "Germany, France, Japan", "product": "saas", "budget": "high" }
```

### What `main.py` forwards to `agent.py`:
```python
recommend_markets("Germany, France, Japan", product="saas", budget="high")
```

### What `compare_markets` MCP tool returns (inside the agent loop):
```json
{
  "ok": true,
  "data": {
    "ranked": [
      {
        "country": "Germany",
        "market_score": 84,
        "potential_rating": "High",
        "product_fit_analysis": {
          "product_type": "Software / SaaS",
          "rationale": "English-speaking, high-GDP markets accelerate SaaS adoption...",
          "bonuses_applied": ["High-income economy ($4200B GDP) (+8 pts)"],
          "scoring_weights": "Population 18% / GDP 42% / Stability 25% / Density 15%"
        }
      }
    ]
  }
}
```

### What `_extract_state()` builds as `reasoning_chain`:
```
"Called compare_markets(list_of_countries=[\"Germany\",\"France\",\"Japan\"], product=\"saas\") → 3 countries ranked — top: Germany (84/100)"
"Called get_country_data(country_name=\"Germany\") → ok — Germany, pop 83,240,000, GDP $4200.0B"
"Called analyze_market_potential(country_name=\"Germany\", product=\"saas\") → score 84/100, High potential"
"Called recommend_expansion_targets(product=\"saas\", budget_constraint=\"high\") → 3 targets returned"
```

### What the frontend receives:
```json
{
  "recommendations": [
    {
      "country": "Germany",
      "score": 8.4,
      "population": 83240000,
      "gdp_bn": 4200.0,
      "region": "Europe",
      "reasoning": "Ranked by product-market fit (score 84, High). ...",
      "product_fit": { "product_type": "Software / SaaS", "bonuses_applied": [...] }
    }
  ],
  "reasoning_chain": [
    "Called compare_markets(...) → 3 countries ranked — top: Germany (84/100)",
    "Called get_country_data(...) → ok — Germany, pop 83,240,000, GDP $4200.0B"
  ],
  "confidence_score": 0.9,
  "summary": "Germany leads due to...",
  "product": "saas",
  "product_category": "Software / SaaS"
}
```

---

## Dependency Map

```
frontend/src/App.jsx
  └── fetch → backend/main.py

backend/main.py
  └── import → backend/agent.py

backend/agent.py
  └── MultiServerMCPClient (MCP stdio) → mcp_server/server.py
        ├── import → mcp_server/tools/rest_countries_client.py
        │     └── HTTP → restcountries.com
        │     └── HTTP → api.worldbank.org
        └── import → mcp_server/tools/market_analyzer.py
              └── uses → rest_countries_client.py (passed in as dependency)

mcp_server/client_smoke_test.py
  └── subprocess (MCP stdio) → mcp_server/server.py  (test path only)
```

---

## Where to Make Changes

| What you want to change | Where to go |
|---|---|
| Add a new product category (e.g. "gaming") | `mcp_server/tools/market_analyzer.py` → `PRODUCT_PROFILES` |
| Change the scoring formula | `mcp_server/tools/market_analyzer.py` → `analyze_market_potential()` |
| Add a new tool (e.g. competitor lookup) | Add logic in `market_analyzer.py`, add `@mcp.tool()` in `server.py` — agent picks it up via `client.get_tools()` automatically |
| Change which countries are in the budget pools | `mcp_server/tools/market_analyzer.py` → `BUDGET_CANDIDATES` |
| Change Claude's reasoning behavior | `backend/agent.py` → `_SYSTEM_TEXT` / `PROMPT` |
| Change the API timeout | `backend/main.py` → `asyncio.wait_for(..., timeout=120)` |
| Change the rate limit | `backend/main.py` → `@limiter.limit("5/minute")` |
| Change what the results look like | `frontend/src/App.jsx` → `MarketCard` component |
| Change the loading experience | `frontend/src/App.jsx` → `AgentLoader` component + `ANALYSIS_STAGES` |
| Test MCP tools without running the full stack | `mcp_server/client_smoke_test.py` |
