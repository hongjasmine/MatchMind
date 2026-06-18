"""
MatchMind LangGraph Agent — WITH TEMP TIMING DIAGNOSTICS
"""

import json
import time
import re
from typing import TypedDict
from langgraph.graph import StateGraph, END
import google.generativeai as genai

from app.mcp_server.tools import get_live_matches, get_match_details, get_team_standings, dispatch_tool
from app.mcp_server.cache import cached_tool_call
from app.config import get_settings

settings = get_settings()
genai.configure(api_key=settings.google_api_key)


class AgentState(TypedDict):
    claim: str
    match_context: dict
    raw_verdict: str
    verdict: str
    confidence: float
    explanation: str
    citations: list[str]
    card: dict
    latency_ms: float
    token_usage: dict
    error: str | None


async def fetch_node(state: AgentState) -> AgentState:
    t0 = time.time()
    claim = state["claim"]
    context = {}

    live = await cached_tool_call("get_live_matches", get_live_matches)
    context["live_matches"] = live

    claim_lower = claim.lower()
    common_teams = [
        "brazil", "france", "argentina", "germany", "spain",
        "england", "portugal", "usa", "mexico", "japan",
        "netherlands", "italy", "croatia", "senegal", "morocco",
    ]
    mentioned_teams = [t for t in common_teams if t in claim_lower]

    for team in mentioned_teams[:2]:
        standings = await cached_tool_call(
            "get_team_standings", get_team_standings, team_name=team,
        )
        context[f"standings_{team}"] = standings

    if live.get("matches") and len(live["matches"]) == 1:
        match_id = live["matches"][0]["id"]
        details = await cached_tool_call(
            "get_match_details", get_match_details, match_id=match_id,
        )
        context["match_details"] = details

    print(f"[TIMING] fetch_node total: {(time.time()-t0)*1000:.1f}ms")
    return {**state, "match_context": context}


VERDICT_SYSTEM_PROMPT = """You are MatchMind, a sports argument fact-checker for the 2026 FIFA World Cup.

Your job: Given a user's sports claim and live match data, determine if the claim is:
- SUPPORTED: The data clearly backs the claim
- REFUTED: The data clearly contradicts the claim
- PARTIALLY_SUPPORTED: The data partially supports the claim or is inconclusive
- INSUFFICIENT_DATA: Cannot verify with available data

Rules:
1. Only cite specific numbers and facts from the provided data
2. Be concise — users are watching a live match
3. Your explanation must be 1-2 sentences max
4. Citations must include a concrete number whenever the data has one — score,
   minute, points, goals, position. GOOD: "Score: 1-0", "67th minute", "Brazil:
   6 points". BAD: "United States vs Australia", "Live match listed" (no number).
   If the claim is about a match existing/scheduled (not stats), cite the
   match status and stage instead, e.g. "Status: SCHEDULED, Group D".

Respond ONLY in this JSON format (no markdown, no extra text):
{
  "verdict": "SUPPORTED|REFUTED|PARTIALLY_SUPPORTED|INSUFFICIENT_DATA",
  "confidence": 0.0-1.0,
  "explanation": "One or two sentence explanation using specific data.",
  "citations": ["specific data point 1", "specific data point 2"]
}"""


async def verdict_node(state: AgentState) -> AgentState:
    t0 = time.time()
    model = genai.GenerativeModel(
        "gemini-2.5-flash",
        system_instruction=VERDICT_SYSTEM_PROMPT,
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            max_output_tokens=500,
            response_mime_type="application/json",
        ),
    )
    t1 = time.time()
    print(f"[TIMING] model init: {(t1-t0)*1000:.1f}ms")

    context_str = json.dumps(state["match_context"], indent=2)
    print(f"[TIMING] context size: {len(context_str)} chars")
    user_prompt = f"""Claim to verify: "{state['claim']}"

Live match data:
{context_str}

Verify the claim using the data above. Citations must be short, human-readable
facts (e.g. "Score: 2-0" or "Brazil: 6 points"), never raw data structures."""

    token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    try:
        response = await model.generate_content_async(user_prompt)
        t2 = time.time()
        print(f"[TIMING] gemini generate_content_async: {(t2-t1)*1000:.1f}ms")
        raw = response.text

        if hasattr(response, "usage_metadata") and response.usage_metadata:
            token_usage = {
                "prompt_tokens": response.usage_metadata.prompt_token_count,
                "completion_tokens": response.usage_metadata.candidates_token_count,
                "total_tokens": response.usage_metadata.total_token_count,
            }

        parsed = json.loads(raw)
        citations = _clean_citations(parsed.get("citations", []))

        print(f"[TIMING] verdict_node total: {(time.time()-t0)*1000:.1f}ms")
        return {
            **state, "raw_verdict": raw, "verdict": parsed["verdict"],
            "confidence": float(parsed["confidence"]), "explanation": parsed["explanation"],
            "citations": citations, "token_usage": token_usage,
        }

    except json.JSONDecodeError as e:
        cleaned = re.sub(r"```json?\n?|```", "", raw).strip()
        try:
            parsed = json.loads(cleaned)
            citations = _clean_citations(parsed.get("citations", []))
            return {
                **state, "raw_verdict": raw, "verdict": parsed["verdict"],
                "confidence": float(parsed["confidence"]), "explanation": parsed["explanation"],
                "citations": citations, "token_usage": token_usage,
            }
        except Exception as inner_e:
            return {
                **state, "raw_verdict": raw, "verdict": "INSUFFICIENT_DATA",
                "confidence": 0.0, "explanation": "Could not parse the verdict. Please try again.",
                "citations": [], "token_usage": token_usage, "error": str(inner_e),
            }
    except Exception as e:
        return {
            **state, "verdict": "INSUFFICIENT_DATA", "confidence": 0.0,
            "explanation": "Error contacting AI service.", "citations": [],
            "token_usage": token_usage, "error": str(e),
        }


def _clean_citations(citations: list) -> list[str]:
    cleaned = []
    for c in citations:
        if isinstance(c, str):
            if c.strip().startswith("{") or "'id':" in c:
                continue
            cleaned.append(c[:120])
        else:
            continue
    return cleaned


VERDICT_EMOJI = {
    "SUPPORTED": "✅", "REFUTED": "❌", "PARTIALLY_SUPPORTED": "⚠️", "INSUFFICIENT_DATA": "❓",
}


async def format_node(state: AgentState) -> AgentState:
    t0 = time.time()
    verdict = state.get("verdict", "INSUFFICIENT_DATA")
    confidence_pct = int(state.get("confidence", 0.0) * 100)

    live_matches = state["match_context"].get("live_matches", {}).get("matches", [])
    match_snapshot = (
        {
            "home": live_matches[0]["home_team"], "away": live_matches[0]["away_team"],
            "score": f"{live_matches[0]['home_score']} - {live_matches[0]['away_score']}",
            "minute": live_matches[0].get("minute"),
        } if live_matches else None
    )

    card = {
        "verdict": verdict, "verdict_emoji": VERDICT_EMOJI[verdict], "confidence": confidence_pct,
        "claim": state["claim"], "explanation": state.get("explanation", ""),
        "citations": state.get("citations", []), "match_snapshot": match_snapshot,
        "token_usage": state.get("token_usage", {}),
        "share_text": (
            f"{VERDICT_EMOJI[verdict]} \"{state['claim']}\" → "
            f"{verdict} ({confidence_pct}% confidence) | MatchMind #WC2026"
        ),
    }
    print(f"[TIMING] format_node total: {(time.time()-t0)*1000:.1f}ms")
    return {**state, "card": card}


def build_agent():
    graph = StateGraph(AgentState)
    graph.add_node("fetch", fetch_node)
    graph.add_node("verdict", verdict_node)
    graph.add_node("format", format_node)
    graph.set_entry_point("fetch")
    graph.add_edge("fetch", "verdict")
    graph.add_edge("verdict", "format")
    graph.add_edge("format", END)
    return graph.compile()


agent = build_agent()


async def run_agent(claim: str) -> dict:
    start = time.time()
    initial_state: AgentState = {
        "claim": claim, "match_context": {}, "raw_verdict": "", "verdict": "",
        "confidence": 0.0, "explanation": "", "citations": [], "card": {},
        "latency_ms": 0.0, "token_usage": {}, "error": None,
    }
    result = await agent.ainvoke(initial_state)
    result["latency_ms"] = round((time.time() - start) * 1000, 1)
    print(f"[TIMING] === TOTAL run_agent: {result['latency_ms']}ms ===")
    return result
