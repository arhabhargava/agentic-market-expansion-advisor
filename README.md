# Agentic Market Expansion Advisor

An agentic full-stack application that helps businesses identify the best countries to expand into for a given product. Users input target countries and a product type; an LLM agent calls real-world data tools, scores each market using product-specific heuristics, and returns ranked recommendations with reasoning.

Built with: **Anthropic Claude** (tool-calling agent) · **FastMCP** (MCP server) · **REST Countries + World Bank APIs** · **FastAPI** · **React + Tailwind CSS**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                              │
│                   React + Tailwind UI                       │
└────────────────────────┬────────────────────────────────────┘
                         │ POST /analyze
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  FastAPI Backend (port 8000)                 │
│                    backend/main.py                          │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │            LLM Agent  (backend/agent.py)            │   │
│   │   Anthropic Claude · tool-calling loop · up to 8   │   │
│   │   rounds · assembles ranked RecommendationItems     │   │
│   └────────────────────┬────────────────────────────────┘   │
└───────────────────────┬┘────────────────────────────────────┘
                        │ tool dispatch
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              MCP Server  (mcp_server/server.py)             │
│                    FastMCP · stdio transport                 │
│                                                             │
│  get_country_data          → REST Countries API v3.1        │
│  analyze_market_potential  → Product-aware scoring engine   │
│  compare_markets           → Ranked comparison              │
│  recommend_expansion_targets → Budget-tier recommendations  │
└──────────────┬──────────────────────┬───────────────────────┘
               │                      │
               ▼                      ▼
  restcountries.com/v3.1     api.worldbank.org (GDP)
  (no key required)          (no key required)
```

**Key design decisions:**

- **MCP Server** runs as a separate subprocess (stdio transport). The agent spawns it at request time using `langchain-mcp-adapters` (`MultiServerMCPClient`), communicates over JSON-RPC, and discovers available tools dynamically via `client.get_tools()` — no hardcoded tool schemas in the agent.
- **Product-aware scoring** — seven product profiles (luxury, saas, fmcg, healthcare, education, finance, ecommerce) each carry different scoring weights for population, GDP, stability, and density. The agent selects the right profile from the user's product description.
- **Real data** — no mocks in production. Every analysis calls the live REST Countries and World Bank APIs.
- **API keys** are only ever read from environment variables, never hardcoded.

---

## Why MCP?

The Model Context Protocol (MCP) is an open standard for connecting AI agents to external tools and data sources. Using it here instead of defining tools directly in the agent gives three concrete benefits:

**1. True separation of concerns**
The LLM agent (`backend/agent.py`) has zero knowledge of REST Countries or World Bank. It only speaks MCP protocol. Swapping the data source — say, replacing World Bank with IMF data — means changing one file (`rest_countries_client.py`) with no changes to the agent.

**2. Dynamic tool discovery**
The agent calls `client.get_tools()` at runtime. Add a new `@mcp.tool()` function to `mcp_server/server.py` and the agent picks it up on the next request — no redeployment of the agent layer required.

**3. Reusability**
The MCP server can be called by any MCP-compatible client — not just this agent. It can be tested standalone (`python mcp_server/client_smoke_test.py`), reused in a different agent, or exposed over HTTP for multi-agent systems.

---

## Tool Calling Flow

What happens inside a single `/analyze` request:

```
1. POST /analyze arrives at FastAPI (main.py)
         │
         ▼
2. main.py validates input, applies rate limit, checks API key
         │
         ▼
3. agent.py spawns mcp_server/server.py as a subprocess (stdio)
   MultiServerMCPClient connects, calls get_tools() → 4 LangChain BaseTools
         │
         ▼
4. LangGraph create_react_agent receives the user question + tools
   Claude reasons: "I need to rank these countries. Call compare_markets first."
         │
         ▼
5. Agent calls compare_markets(["Japan", "India"], "luxury watches")
   → MCP server executes: REST Countries API + World Bank API + scoring engine
   → Returns ranked JSON over stdio
         │
         ▼
6. Claude reads result, may call get_country_data or analyze_market_potential
   for deeper analysis on specific countries
         │
         ▼
7. Claude calls recommend_expansion_targets to surface global alternatives
         │
         ▼
8. Claude writes Final Answer with specific GDP/population figures
         │
         ▼
9. agent.py extracts ToolMessage history → builds reasoning_chain + recommendations
         │
         ▼
10. FastAPI returns structured JSON → React renders market cards + AI summary
```

Each tool call in step 5–7 is a JSON-RPC message sent over stdin/stdout between the agent process and the MCP server process.

---

## Project Structure

```
.
├── backend/
│   ├── agent.py          # Anthropic tool-calling agent loop + result assembly
│   └── main.py           # FastAPI app — POST /analyze, GET /health
│
├── mcp_server/
│   ├── server.py         # FastMCP server — exposes 4 tools
│   └── tools/
│       ├── market_analyzer.py       # Scoring engine + product profiles
│       └── rest_countries_client.py # REST Countries + World Bank client
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx       # Full UI — form, market cards, analysis accordion
│   │   └── index.css     # Tailwind directives
│   ├── tailwind.config.js
│   └── package.json
│
├── requirements.txt
└── .env                  # Never committed — see setup below
```

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.11+ |
| Node.js | 18+ |
| npm | 9+ |

---

## Setup

### 1. Clone the repo

```bash
git clone <your-repo-url>
cd inmarket-location-optimizer-agent
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Then open `.env` and fill in your Anthropic API key:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

**Getting an Anthropic API key:**
1. Sign up at [console.anthropic.com](https://console.anthropic.com)
2. Navigate to **API Keys** → **Create Key**
3. Paste the key into `.env`

> No other API keys are required. REST Countries and World Bank APIs are free and keyless.

### 3. Set up the Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Set up the frontend

```bash
cd frontend
npm install
cd ..
```

---

## Running the Application

Open **two terminal windows** from the project root.

### Terminal 1 — FastAPI backend

```bash
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### Terminal 2 — React frontend

```bash
cd frontend
npm run dev
```

Expected output:
```
  VITE ready in xxx ms
  ➜  Local:   http://localhost:5173/
```

Open **http://localhost:5173** in your browser.

---

## API Reference

### `POST /analyze`

Runs the full market analysis agent.

**Request:**
```json
{
  "countries": "Germany, Japan, France",
  "product": "luxury watches",
  "budget": "high"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `countries` | string | ✅ | Comma-separated country names |
| `product` | string | ❌ | Product type — shapes scoring weights |
| `budget` | string | ❌ | `low`, `medium`, or `high` |

**Response:**
```json
{
  "recommendations": [
    {
      "country": "Japan",
      "score": 9.1,
      "population": 125700000,
      "gdp_bn": 4210.8,
      "region": "Asia",
      "reasoning": "...",
      "product_fit": {
        "product_type": "Luxury / Premium Goods",
        "rationale": "...",
        "bonuses_applied": ["High-income economy ($4211B GDP) (+18 pts)"],
        "scoring_weights": "Population 12% / GDP 56% / Stability 26% / Density 6%"
      }
    }
  ],
  "reasoning_chain": ["compare_markets({...}) -> ok", "..."],
  "confidence_score": 0.91,
  "summary": "...",
  "product": "luxury watches",
  "product_category": "Luxury / Premium Goods"
}
```

### `GET /health`

```json
{ "status": "ok", "timestamp": "2025-05-06T18:00:00+00:00" }
```

---

## MCP Server Tools

The four tools exposed by `mcp_server/server.py`:

| Tool | Description | External API |
|---|---|---|
| `get_country_data(country_name)` | Population, GDP, area, languages, region | REST Countries v3.1 + World Bank |
| `analyze_market_potential(country_data, product)` | Product-aware market score (1–100) | None — internal scoring |
| `compare_markets(list_of_countries, product)` | Ranked comparison across countries | REST Countries + World Bank |
| `recommend_expansion_targets(product, budget_constraint)` | Top 3 from curated budget-tier pool | REST Countries + World Bank |

Run the MCP server standalone (from project root):

```bash
source .venv/bin/activate
python mcp_server/server.py
```

> The agent spawns this automatically as a subprocess on each `/analyze` request — you do not need to start it manually during normal use.

---

## Product Scoring Profiles

The agent automatically detects the product category from the user's input and adjusts scoring weights:

| Category | Example Keywords | Pop % | GDP % | Stability % | Density % |
|---|---|---|---|---|---|
| Luxury / Premium | luxury, watch, designer, premium | 12 | 56 | 26 | 6 |
| Software / SaaS | saas, software, platform, cloud, ai | 18 | 42 | 25 | 15 |
| FMCG | food, beverage, fmcg, grocery | 55 | 18 | 15 | 12 |
| Healthcare / Pharma | pharma, medical, health, biotech | 25 | 42 | 28 | 5 |
| Education / EdTech | edtech, learning, school, training | 42 | 24 | 20 | 14 |
| Finance / Fintech | fintech, banking, payment, insurance | 18 | 50 | 28 | 4 |
| E-commerce / Retail | ecommerce, retail, fashion, shop | 46 | 28 | 14 | 12 |
| General (default) | *(no match)* | 32 | 28 | 22 | 18 |

---

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | — | Your Anthropic API key |
| `FASTAPI_PORT` | ❌ | `8000` | Backend port |
| `ANTHROPIC_MODEL` | ❌ | `claude-sonnet-4-6` | Override the Claude model |
| `ALLOWED_ORIGINS` | ❌ | `*` | Comma-separated list of allowed CORS origins. Set to your frontend domain in production (e.g. `https://yourapp.com`) |
| `API_KEY` | ❌ | *(unset)* | When set, `/analyze` requires an `X-API-Key: <value>` request header. Leave unset for open access in local dev |

---

## Development Guide

### Adding a new product profile

Edit `mcp_server/tools/market_analyzer.py` → `PRODUCT_PROFILES` dict. Add an entry with:
- `keywords` — list of strings to match against user input
- `weight_population`, `weight_gdp`, `weight_stability`, `weight_density` — must sum to 1.0
- `english_bonus`, `high_income_bonus`, `high_income_threshold_bn` — optional bonuses
- `label`, `fit_rationale` — displayed in the UI

### Adding a new MCP tool

1. Implement logic in `mcp_server/tools/market_analyzer.py`
2. Expose it with `@mcp.tool()` in `mcp_server/server.py`

That's it. The agent calls `client.get_tools()` at runtime to discover all tools from the MCP server — no changes to `backend/agent.py` are needed. The new tool's name, description, and input schema are picked up automatically.

### Changing the LLM model

Set `ANTHROPIC_MODEL` in `.env` (e.g., `claude-opus-4-6` for higher reasoning quality).

---

## Security Considerations

### What is protected and how

| Threat | Mitigation |
|---|---|
| API key leakage | `ANTHROPIC_API_KEY` is read server-side only, never sent to the browser. `.env` is in `.gitignore`. |
| Unlimited API spend | `slowapi` rate limiter enforces 5 requests/minute per IP on `/analyze`. Each call can cost $0.10–0.30 in Claude API credits. |
| Unauthorized access | Optional `API_KEY` env var enables `X-API-Key` header auth on `/analyze`. Set it in any non-local deployment. |
| Cross-origin abuse | `ALLOWED_ORIGINS` env var controls CORS. Defaults to `*` for local dev — set to your frontend domain in production. |
| Prompt injection via country names | Country names are passed as structured parameters to MCP tools, not interpolated into raw prompt strings. |
| Malformed input | Pydantic validators on `AnalyzeRequest` reject empty `countries`, invalid `budget` values, and non-string inputs before they reach the agent. |

### What is intentionally open

- REST Countries and World Bank APIs are public and require no credentials — no secrets to protect there.
- `allow_credentials=False` (FastAPI default) is intentional — combining `allow_origins=["*"]` with `allow_credentials=True` is rejected by Starlette.

### Production checklist

- [ ] Set `ALLOWED_ORIGINS=https://yourfrontend.com`
- [ ] Set `API_KEY=<long-random-secret>` and add the header in your frontend fetch calls
- [ ] Store `ANTHROPIC_API_KEY` in a secrets manager (AWS Secrets Manager, GCP Secret Manager, K8s Secret) — not in a `.env` file on the server
- [ ] Put an API gateway or nginx in front for TLS termination and additional rate limiting

---

## Deployment Strategy

### Docker (recommended for most teams)

Backend `Dockerfile`:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Frontend `Dockerfile` (multi-stage):

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
```

Secrets are injected at runtime via `docker-compose.yml` environment blocks — never baked into images:

```yaml
services:
  backend:
    build: .
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - API_KEY=${API_KEY}
      - ALLOWED_ORIGINS=https://yourapp.com
    ports:
      - "8000:8000"
```

### Kubernetes

- Backend deploys as a `Deployment` with 2+ replicas behind a `ClusterIP` service
- `ANTHROPIC_API_KEY` stored as a Kubernetes `Secret`, mounted as an environment variable
- Horizontal pod autoscaling on the backend based on CPU or request latency
- Frontend static assets served from S3 + CloudFront or an nginx `Deployment`
- Ingress controller handles TLS termination and routes `/analyze` to the backend service

### Serverless

- Backend → **Google Cloud Run** or **AWS Lambda + API Gateway** (stateless request/response fits perfectly — no persistent connections needed)
- MCP server spawning works on Cloud Run (full OS subprocess support); on Lambda, package the MCP server alongside the handler
- Frontend → **Vercel** or **Netlify** (zero-config React deploy, automatic CDN)

---

## Future Improvements

| Area | Improvement |
|---|---|
| **Data sources** | Add IMF World Economic Outlook data for GDP forecasts; integrate Numbeo cost-of-living index for FMCG and e-commerce scoring |
| **Streaming** | Stream Claude's reasoning token-by-token to the frontend using Server-Sent Events — eliminates the perceived wait time |
| **Caching** | Cache REST Countries + World Bank responses with a 24-hour TTL (Redis or in-memory) — cuts latency by 60–70% on repeated country lookups |
| **More product profiles** | Add profiles for climate tech, real estate, logistics, gaming — each with domain-specific scoring signals |
| **User accounts** | Save analysis history per user; compare results over time as market conditions change |
| **Map visualisation** | Render a choropleth world map with scores overlaid — makes regional patterns immediately visible |
| **Multi-agent** | Run country analyses in parallel across a pool of sub-agents instead of sequentially — reduces latency from O(n) to O(1) for large country lists |
| **Evaluation** | Add a scoring accuracy benchmark — compare agent recommendations against known market performance data for backtesting |

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'dotenv'`**
You're using the system Python instead of the venv. Run `source .venv/bin/activate` first.

**`ANTHROPIC_API_KEY is not set`**
Ensure `.env` exists at the project root with a valid key value.

**`Error: Failed to fetch` in the browser**
The backend isn't running. Start it with `uvicorn backend.main:app --reload --port 8000`.

**`Analysis timed out after 120 seconds`**
The agent makes multiple sequential API calls including World Bank GDP lookups which can be slow. This is expected on first run — subsequent calls may be faster if the OS caches DNS.

**REST Countries returns 404**
Use the official English country name (e.g., `South Korea` not `Korea`, `United States` not `USA`).
