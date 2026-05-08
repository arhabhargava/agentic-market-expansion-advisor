import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend.agent import recommend_markets

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Rate limiter (in-memory, per IP) ─────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Agentic Market Expansion Advisor")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ─────────────────────────────────────────────────────────────────────
# In dev: set ALLOWED_ORIGINS=* (default).
# In prod: set ALLOWED_ORIGINS=https://yourapp.com,https://admin.yourapp.com
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
_cors_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# ── Auth ──────────────────────────────────────────────────────────────────────
# Set API_KEY in .env to enforce authentication.
# If API_KEY is not set, the endpoint is open (dev mode).
_API_KEY = os.getenv("API_KEY")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def _require_api_key(key: Optional[str] = Security(_api_key_header)) -> None:
    if _API_KEY and key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


# ── Request / Response models ─────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    countries: str
    product: str = ""
    budget: Optional[str] = None

    @field_validator("countries")
    @classmethod
    def countries_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("countries must not be empty")
        return v.strip()

    @field_validator("budget")
    @classmethod
    def budget_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip().lower() not in ("low", "medium", "high"):
            raise ValueError("budget must be one of: low, medium, high")
        return v.strip().lower() if v else v


# ── Middleware ────────────────────────────────────────────────────────────────

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info("%s %s", request.method, request.url.path)
    response = await call_next(request)
    logger.info("%s %s -> %s", request.method, request.url.path, response.status_code)
    return response


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/analyze", dependencies=[Security(_require_api_key)])
@limiter.limit("5/minute")
async def analyze(request: Request, body: AnalyzeRequest):
    logger.info(
        "Analyzing markets: countries=%r product=%r budget=%r",
        body.countries, body.product, body.budget,
    )
    try:
        result = await asyncio.wait_for(
            recommend_markets(body.countries, body.product, body.budget),
            timeout=120,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Analysis timed out after 120 seconds.")
    except Exception as exc:
        logger.exception("Unexpected error during analysis")
        raise HTTPException(status_code=500, detail=str(exc))

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
