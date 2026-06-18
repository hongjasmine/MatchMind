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
