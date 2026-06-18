"""
MatchMind FastAPI Backend
API gateway for the LangGraph agent.

Routes:
  POST /verify        → main claim verification endpoint
  GET  /matches/live  → raw live match data (MCP passthrough)
  GET  /health        → health check
  GET  /evals/recent  → last N verdict results (for eval dashboard)
"""

import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agent.pipeline import run_agent
from app.mcp_server.tools import get_live_matches, get_match_details
from app.mcp_server.cache import cached_tool_call
from app.api.storage import store_verdict, get_recent_verdicts
from app.evals.framework import evaluate_verdict
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("MatchMind starting up...")
    yield
    logger.info("MatchMind shutting down...")


app = FastAPI(
    title="MatchMind",
    description="Live sports argument verification agent for WC 2026",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class VerifyRequest(BaseModel):
    claim: str = Field(..., min_length=5, max_length=500, description="The sports claim to verify")


class VerifyResponse(BaseModel):
    verdict: str
    verdict_emoji: str
    confidence: int
    explanation: str
    citations: list[str]
    match_snapshot: dict | None
    share_text: str
    latency_ms: float
    token_usage: dict | None = None
    verdict_id: str | None = None
    eval_scores: dict | None = None


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "matchmind",
        "env": settings.app_env,
    }


@app.post("/verify", response_model=VerifyResponse)
async def verify_claim(req: VerifyRequest):
    try:
        result = await run_agent(req.claim)

        card = result.get("card", {})
        if not card:
            raise HTTPException(status_code=500, detail="Agent returned empty card")

        eval_scores = evaluate_verdict(req.claim, result)
        verdict_id = await store_verdict(req.claim, {**result, "eval_scores": eval_scores})

        if result.get("latency_ms", 0) > 3000:
            logger.warning(f"Latency SLA breach: {result['latency_ms']}ms for claim: {req.claim[:60]}")

        return VerifyResponse(
            verdict=card["verdict"],
            verdict_emoji=card["verdict_emoji"],
            confidence=card["confidence"],
            explanation=card["explanation"],
            citations=card["citations"],
            match_snapshot=card.get("match_snapshot"),
            share_text=card["share_text"],
            latency_ms=result["latency_ms"],
            token_usage=card.get("token_usage"),
            verdict_id=verdict_id,
            eval_scores=eval_scores,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Pipeline error for claim: {req.claim[:60]}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/matches/live")
async def live_matches():
    return await cached_tool_call("get_live_matches", get_live_matches)


@app.get("/matches/{match_id}")
async def match_details(match_id: int):
    from app.mcp_server.tools import get_match_details
    return await cached_tool_call(
        "get_match_details",
        get_match_details,
        match_id=match_id,
    )


@app.get("/evals/recent")
async def recent_evals(limit: int = 20):
    return await get_recent_verdicts(limit)
