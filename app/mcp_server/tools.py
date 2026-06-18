"""
MatchMind MCP Server
Wraps football-data.org API as MCP tools for the LangGraph agent.

Tools exposed:
  - get_live_matches()         → all live World Cup matches right now
  - get_match_details(id)      → lineups, stats, events for one match
  - get_team_standings(team)   → group table position for a team
"""

import json
import httpx
import asyncio
from typing import Any
from app.config import get_settings

settings = get_settings()

FOOTBALL_API_BASE = "https://api.football-data.org/v4"
WC_2026_COMPETITION_CODE = "WC"  # football-data.org code for World Cup

HEADERS = {
    "X-Auth-Token": settings.football_data_api_key,
}


# ─── Raw API helpers ──────────────────────────────────────────────────────────

async def _fetch(path: str, params: dict | None = None) -> dict:
    """Single async request to football-data.org with error handling."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{FOOTBALL_API_BASE}{path}",
            headers=HEADERS,
            params=params or {},
        )
        resp.raise_for_status()
        return resp.json()


# ─── MCP Tool implementations ─────────────────────────────────────────────────

async def get_live_matches() -> dict[str, Any]:
    """
    MCP Tool: get_live_matches
    Returns all currently live World Cup 2026 matches with scores and minute.
    Falls back to today's scheduled matches if none are live.
    """
    try:
        data = await _fetch(
            f"/competitions/{WC_2026_COMPETITION_CODE}/matches",
            params={"status": "LIVE"},
        )
        matches = data.get("matches", [])

        if not matches:
            # Fallback: scheduled matches today
            data = await _fetch(
                f"/competitions/{WC_2026_COMPETITION_CODE}/matches",
                params={"status": "SCHEDULED"},
            )
            matches = data.get("matches", [])[:5]

        formatted = []
        for m in matches:
            formatted.append({
                "id": m["id"],
                "status": m["status"],
                "minute": m.get("minute"),
                "home_team": m["homeTeam"]["name"],
                "away_team": m["awayTeam"]["name"],
                "home_score": m["score"]["fullTime"]["home"],
                "away_score": m["score"]["fullTime"]["away"],
                "half_time_score": {
                    "home": m["score"]["halfTime"]["home"],
                    "away": m["score"]["halfTime"]["away"],
                },
                "stage": m.get("stage"),
                "group": m.get("group"),
            })

        return {"matches": formatted, "count": len(formatted)}

    except httpx.HTTPStatusError as e:
        return {"error": f"API error {e.response.status_code}: {e.response.text}"}
    except Exception as e:
        return {"error": str(e)}


async def get_match_details(match_id: int) -> dict[str, Any]:
    """
    MCP Tool: get_match_details
    Returns lineups, match events (goals/cards), and head-to-head stats.
    """
    try:
        data = await _fetch(f"/matches/{match_id}")

        home = data["homeTeam"]
        away = data["awayTeam"]

        # Extract goals
        goals = [
            {
                "minute": g["minute"],
                "team": g["team"]["name"],
                "scorer": g["scorer"]["name"] if g.get("scorer") else "Unknown",
                "type": g.get("type", "REGULAR"),
            }
            for g in data.get("goals", [])
        ]

        # Extract bookings (yellow/red cards)
        bookings = [
            {
                "minute": b["minute"],
                "team": b["team"]["name"],
                "player": b["player"]["name"] if b.get("player") else "Unknown",
                "card": b["card"],
            }
            for b in data.get("bookings", [])
        ]

        return {
            "match_id": match_id,
            "status": data["status"],
            "minute": data.get("minute"),
            "home_team": {
                "name": home["name"],
                "lineup": [p["name"] for p in home.get("lineup", [])],
                "bench": [p["name"] for p in home.get("bench", [])],
            },
            "away_team": {
                "name": away["name"],
                "lineup": [p["name"] for p in away.get("lineup", [])],
                "bench": [p["name"] for p in away.get("bench", [])],
            },
            "score": data["score"]["fullTime"],
            "goals": goals,
            "bookings": bookings,
        }

    except httpx.HTTPStatusError as e:
        return {"error": f"API error {e.response.status_code}"}
    except Exception as e:
        return {"error": str(e)}


async def get_team_standings(team_name: str) -> dict[str, Any]:
    """
    MCP Tool: get_team_standings
    Returns current group-stage standings for a given team name.
    """
    try:
        data = await _fetch(
            f"/competitions/{WC_2026_COMPETITION_CODE}/standings"
        )
        groups = data.get("standings", [])

        for group in groups:
            for entry in group.get("table", []):
                if team_name.lower() in entry["team"]["name"].lower():
                    return {
                        "team": entry["team"]["name"],
                        "group": group.get("group"),
                        "position": entry["position"],
                        "played": entry["playedGames"],
                        "won": entry["won"],
                        "drawn": entry["draw"],
                        "lost": entry["lost"],
                        "goals_for": entry["goalsFor"],
                        "goals_against": entry["goalsAgainst"],
                        "goal_difference": entry["goalDifference"],
                        "points": entry["points"],
                    }

        return {"error": f"Team '{team_name}' not found in standings"}

    except httpx.HTTPStatusError as e:
        return {"error": f"API error {e.response.status_code}"}
    except Exception as e:
        return {"error": str(e)}


# ─── Tool registry (used by LangGraph agent) ──────────────────────────────────

TOOL_REGISTRY = {
    "get_live_matches": {
        "fn": get_live_matches,
        "description": "Get all currently live World Cup 2026 matches with scores",
        "parameters": {},
    },
    "get_match_details": {
        "fn": get_match_details,
        "description": "Get lineups, goals, and cards for a specific match by ID",
        "parameters": {"match_id": "integer - the match ID from get_live_matches"},
    },
    "get_team_standings": {
        "fn": get_team_standings,
        "description": "Get group standings for a team by name",
        "parameters": {"team_name": "string - team name (e.g. 'Brazil', 'France')"},
    },
}


async def dispatch_tool(tool_name: str, **kwargs) -> dict:
    """Route a tool call to the right implementation."""
    if tool_name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool: {tool_name}"}
    return await TOOL_REGISTRY[tool_name]["fn"](**kwargs)
