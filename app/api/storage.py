"""
MongoDB storage for MatchMind verdicts.
Free tier Atlas cluster. Used for:
- Storing all verdicts (eval dataset accumulation)
- Latency tracking
- Eval benchmarking
"""
import motor.motor_asyncio
from datetime import datetime, timezone
from app.config import get_settings

settings = get_settings()

_client: motor.motor_asyncio.AsyncIOMotorClient | None = None
_db = None


def get_db():
    global _client, _db
    if _client is None:
        _client = motor.motor_asyncio.AsyncIOMotorClient(settings.mongodb_uri)
        _db = _client["matchmind"]
    return _db


async def store_verdict(claim: str, result: dict) -> str:
    """Store a verdict result. Returns inserted document ID."""
    db = get_db()
    doc = {
        "claim": claim,
        "verdict": result.get("verdict"),
        "confidence": result.get("confidence"),
        "explanation": result.get("explanation"),
        "citations": result.get("citations", []),
        "latency_ms": result.get("latency_ms"),
        "token_usage": result.get("token_usage"),
        "eval_scores": result.get("eval_scores"),
        "match_snapshot": result.get("card", {}).get("match_snapshot"),
        "created_at": datetime.now(timezone.utc),
        "error": result.get("error"),
    }
    inserted = await db["verdicts"].insert_one(doc)
    return str(inserted.inserted_id)


async def get_recent_verdicts(limit: int = 20) -> list[dict]:
    """Fetch recent verdicts for the frontend feed."""
    db = get_db()
    cursor = db["verdicts"].find(
        {},
        {"_id": 0, "claim": 1, "verdict": 1, "explanation": 1, "created_at": 1}
    ).sort("created_at", -1).limit(limit)
    return await cursor.to_list(length=limit)


async def get_verdict_summary() -> dict:
    """Aggregate stats across all stored verdicts."""
    db = get_db()
    docs = await db["verdicts"].find(
        {},
        {
            "_id": 0, "verdict": 1, "latency_ms": 1,
            "eval_scores": 1, "token_usage": 1,
        }
    ).to_list(length=10_000)

    if not docs:
        return {"total_verdicts": 0}

    n = len(docs)

    # Latency percentiles
    latencies = sorted(
        d["latency_ms"] for d in docs if d.get("latency_ms") is not None
    )
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    p50 = latencies[int(len(latencies) * 0.50)] if latencies else 0.0
    p95 = latencies[min(int(len(latencies) * 0.95), len(latencies) - 1)] if latencies else 0.0

    # Token averages (skip EXISTENCE tier — 0 tokens by design)
    token_vals = [
        d["token_usage"]["total_tokens"]
        for d in docs
        if d.get("token_usage") and d["token_usage"].get("total_tokens", 0) > 0
    ]
    avg_tokens = sum(token_vals) / len(token_vals) if token_vals else 0.0

    # Eval score averages — use only docs that have all three sub-scores
    evals = [
        d["eval_scores"] for d in docs
        if d.get("eval_scores")
        and d["eval_scores"].get("citation_score") is not None
        and d["eval_scores"].get("position_score") is not None
        and d["eval_scores"].get("concision_score") is not None
    ]
    def _avg(key: str) -> float:
        vals = [e[key] for e in evals]
        return sum(vals) / len(vals) if vals else 0.0

    # Verdict distribution
    verdict_dist: dict[str, int] = {}
    for d in docs:
        v = d.get("verdict") or "UNKNOWN"
        verdict_dist[v] = verdict_dist.get(v, 0) + 1

    # Flag counts
    flag_counts: dict[str, int] = {}
    for e in evals:
        for flag in e.get("flags", []):
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

    avg_citation = round(_avg("citation_score"), 3)
    avg_position = round(_avg("position_score"), 3)
    avg_concision = round(_avg("concision_score"), 3)
    avg_overall = round(avg_citation * 0.40 + avg_position * 0.40 + avg_concision * 0.20, 3)

    return {
        "total_verdicts": n,
        "avg_latency_ms": round(avg_latency, 1),
        "p50_latency_ms": round(p50, 1),
        "p95_latency_ms": round(p95, 1),
        "avg_total_tokens": round(avg_tokens, 1),
        "avg_eval_score": avg_overall,
        "avg_citation_score": avg_citation,
        "avg_position_score": avg_position,
        "avg_concision_score": avg_concision,
        "verdict_distribution": verdict_dist,
        "flag_counts": flag_counts,
    }
