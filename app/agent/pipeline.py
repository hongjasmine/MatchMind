"""
MatchMind LangGraph Agent — with 3-tier claim routing
"""

import json
import time
import re
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
import google.generativeai as genai

from app.mcp_server.tools import get_live_matches, get_match_details, get_team_standings
from app.mcp_server.cache import cached_tool_call
from app.config import get_settings

settings = get_settings()
genai.configure(api_key=settings.google_api_key)

# ─── Team name helpers ────────────────────────────────────────────────────────

COMMON_TEAMS = [
    "brazil", "france", "argentina", "germany", "spain",
    "england", "portugal", "usa", "us", "united states", "mexico", "japan",
    "netherlands", "italy", "croatia", "senegal", "morocco", "australia",
]

TEAM_ALIASES = {
    "usa": "united states",
    "us": "united states",
    "united states": "usa",
}

EXISTENCE_PATTERNS = [
    "is playing", "are playing", "playing today", "playing right now",
    "playing tonight", "has a match", "have a match", "in a match",
    "playing a game", "is there a game", "is there a match", "playing now",
]

SIMPLE_STAT_PATTERNS = [
    "score", "winning", "losing", "won", "lost", "scored", "goal",
    "ahead", "behind", "leading", "trailing", "beating", "beat",
    "is up", "is down", "how many goals", "current score",
]

# ─── State ────────────────────────────────────────────────────────────────────


class AgentState(TypedDict):
    claim: str
    claim_tier: str          # EXISTENCE | SIMPLE_STAT | COMPLEX
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


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _mentioned_teams(claim_lower: str) -> list[str]:
    return [t for t in COMMON_TEAMS if t in claim_lower]


def _find_relevant_match(matches: list, mentioned_teams: list[str]) -> dict | None:
    for match in matches:
        home = match.get("home_team", "").lower()
        away = match.get("away_team", "").lower()
        for team in mentioned_teams:
            aliases = {team, TEAM_ALIASES.get(team, team)}
            if any(a in home or a in away for a in aliases):
                return match
    return None


def _extract_json(text: str) -> dict:
    """Parse JSON from Gemini response, tolerating thinking-model preamble."""
    text = text.strip()
    # Direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Strip markdown fences
    cleaned = re.sub(r"```json?\n?|```", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Extract the first {...} block — handles thinking preamble
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON object found in response: {text[:200]}")


def _clean_citations(citations: list) -> list[str]:
    cleaned = []
    for c in citations:
        if isinstance(c, str):
            if c.strip().startswith("{") or "'id':" in c:
                continue
            cleaned.append(c[:120])
    return cleaned


# ─── Node: classify ───────────────────────────────────────────────────────────

def classify_node(state: AgentState) -> AgentState:
    t0 = time.time()
    claim_lower = state["claim"].lower()

    if any(p in claim_lower for p in EXISTENCE_PATTERNS):
        tier = "EXISTENCE"
    elif any(p in claim_lower for p in SIMPLE_STAT_PATTERNS):
        tier = "SIMPLE_STAT"
    else:
        tier = "COMPLEX"

    print(f"[ROUTING] tier={tier}  ({(time.time()-t0)*1000:.1f}ms)")
    return {**state, "claim_tier": tier}


# ─── Node: fetch ──────────────────────────────────────────────────────────────

async def fetch_node(state: AgentState) -> AgentState:
    t0 = time.time()
    tier = state["claim_tier"]
    claim_lower = state["claim"].lower()
    context = {}

    live = await cached_tool_call("get_live_matches", get_live_matches)
    context["live_matches"] = live

    # EXISTENCE only needs the match list — skip standings and details
    if tier == "EXISTENCE":
        print(f"[TIMING] fetch_node (EXISTENCE): {(time.time()-t0)*1000:.1f}ms")
        return {**state, "match_context": context}

    mentioned_teams = _mentioned_teams(claim_lower)

    # SIMPLE_STAT: match details for the relevant match, no standings
    if tier == "SIMPLE_STAT":
        matches = live.get("matches", [])
        match = _find_relevant_match(matches, mentioned_teams) or (matches[0] if matches else None)
        if match:
            details = await cached_tool_call(
                "get_match_details", get_match_details, match_id=match["id"],
            )
            context["match_details"] = details
        print(f"[TIMING] fetch_node (SIMPLE_STAT): {(time.time()-t0)*1000:.1f}ms")
        return {**state, "match_context": context}

    # COMPLEX: full context — standings + match details
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

    print(f"[TIMING] fetch_node (COMPLEX): {(time.time()-t0)*1000:.1f}ms")
    return {**state, "match_context": context}


# ─── Node: existence_verdict (no Gemini) ─────────────────────────────────────

async def existence_verdict_node(state: AgentState) -> AgentState:
    t0 = time.time()
    claim_lower = state["claim"].lower()
    mentioned_teams = _mentioned_teams(claim_lower)
    matches = state["match_context"].get("live_matches", {}).get("matches", [])

    token_usage = {"tier": "EXISTENCE", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    if not matches:
        print(f"[TIMING] existence_verdict_node: {(time.time()-t0)*1000:.1f}ms  (no data)")
        return {
            **state,
            "verdict": "INSUFFICIENT_DATA", "confidence": 0.5,
            "explanation": "No match data available to verify this claim.",
            "citations": [], "token_usage": token_usage,
        }

    match = _find_relevant_match(matches, mentioned_teams) if mentioned_teams else None

    if match:
        home = match["home_team"]
        away = match["away_team"]
        status = match.get("status", "UNKNOWN")
        stage = match.get("stage", "").replace("_", " ").title()
        verdict = "SUPPORTED"
        confidence = 0.97
        explanation = f"{home} is scheduled to play {away} in a {stage} match today."
        citations = [f"{home} vs {away} · Status: {status} · {stage}"]
    else:
        team_name = mentioned_teams[0].title() if mentioned_teams else "The team"
        verdict = "REFUTED"
        confidence = 0.85
        explanation = f"{team_name} does not appear in today's match schedule."
        citations = [f"No match found for {team_name} in today's schedule"]

    print(f"[TIMING] existence_verdict_node: {(time.time()-t0)*1000:.1f}ms  verdict={verdict}")
    return {
        **state,
        "verdict": verdict, "confidence": confidence,
        "explanation": explanation, "citations": citations,
        "token_usage": token_usage,
    }


# ─── Node: verdict (Gemini) ──────────────────────────────────────────────────

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
    tier = state["claim_tier"]

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

    # SIMPLE_STAT: strip context to match_details + live_matches only
    if tier == "SIMPLE_STAT":
        context_data = {
            k: v for k, v in state["match_context"].items()
            if k in ("live_matches", "match_details")
        }
    else:
        context_data = state["match_context"]

    context_str = json.dumps(context_data, indent=2)
    print(f"[ROUTING] tier={tier}  context={len(context_str)} chars")

    user_prompt = (
        f'Claim to verify: "{state["claim"]}"\n\n'
        f"Live match data:\n{context_str}\n\n"
        "Verify the claim using the data above. Citations must be short, human-readable "
        'facts (e.g. "Score: 2-0" or "Brazil: 6 points"), never raw data structures.'
    )

    token_usage = {"tier": tier, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    try:
        response = await model.generate_content_async(user_prompt)
        t2 = time.time()
        print(f"[TIMING] gemini response: {(t2-t1)*1000:.1f}ms")

        # gemini-2.5-flash is a thinking model — extract text from the non-thinking part
        raw = ""
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if not getattr(part, "thought", False):
                    raw += part.text
        raw = raw.strip() or response.text
        print(f"[RAW] {repr(raw[:300])}")

        if hasattr(response, "usage_metadata") and response.usage_metadata:
            token_usage = {
                "tier": tier,
                "prompt_tokens": response.usage_metadata.prompt_token_count,
                "completion_tokens": response.usage_metadata.candidates_token_count,
                "total_tokens": response.usage_metadata.total_token_count,
            }
            print(
                f"[TOKENS] tier={tier}  "
                f"prompt={token_usage['prompt_tokens']}  "
                f"completion={token_usage['completion_tokens']}  "
                f"total={token_usage['total_tokens']}"
            )

        parsed = _extract_json(raw)
        citations = _clean_citations(parsed.get("citations", []))

        print(f"[TIMING] verdict_node total: {(time.time()-t0)*1000:.1f}ms")
        return {
            **state, "raw_verdict": raw,
            "verdict": parsed["verdict"], "confidence": float(parsed["confidence"]),
            "explanation": parsed["explanation"], "citations": citations,
            "token_usage": token_usage,
        }

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"[ERROR] parse failed: {e} — raw: {repr(raw[:300])}")
        return {
            **state, "raw_verdict": raw, "verdict": "INSUFFICIENT_DATA",
            "confidence": 0.0, "explanation": "Could not parse the verdict. Please try again.",
            "citations": [], "token_usage": token_usage, "error": str(e),
            }
    except Exception as e:
        err = str(e)
        if "429" in err or "quota" in err.lower() or "rate" in err.lower():
            explanation = "Gemini rate limit reached — free tier allows 20 requests/day. Try again tomorrow or upgrade your API key."
        else:
            explanation = "Error contacting AI service."
        print(f"[ERROR] verdict_node: {err[:200]}")
        return {
            **state, "verdict": "INSUFFICIENT_DATA", "confidence": 0.0,
            "explanation": explanation, "citations": [],
            "token_usage": token_usage, "error": err,
        }


# ─── Node: format ─────────────────────────────────────────────────────────────

VERDICT_EMOJI = {
    "SUPPORTED": "✅", "REFUTED": "❌",
    "PARTIALLY_SUPPORTED": "⚠️", "INSUFFICIENT_DATA": "❓",
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
        "verdict": verdict, "verdict_emoji": VERDICT_EMOJI[verdict],
        "confidence": confidence_pct, "claim": state["claim"],
        "explanation": state.get("explanation", ""),
        "citations": state.get("citations", []),
        "match_snapshot": match_snapshot,
        "token_usage": state.get("token_usage", {}),
        "share_text": (
            f'{VERDICT_EMOJI[verdict]} "{state["claim"]}" → '
            f"{verdict} ({confidence_pct}% confidence) | MatchMind #WC2026"
        ),
    }
    print(f"[TIMING] format_node: {(time.time()-t0)*1000:.1f}ms")
    return {**state, "card": card}


# ─── Graph ────────────────────────────────────────────────────────────────────

def _route_after_fetch(state: AgentState) -> str:
    return "existence_verdict" if state["claim_tier"] == "EXISTENCE" else "verdict"


def build_agent():
    graph = StateGraph(AgentState)
    graph.add_node("classify", classify_node)
    graph.add_node("fetch", fetch_node)
    graph.add_node("existence_verdict", existence_verdict_node)
    graph.add_node("verdict", verdict_node)
    graph.add_node("format", format_node)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "fetch")
    graph.add_conditional_edges(
        "fetch", _route_after_fetch,
        {"existence_verdict": "existence_verdict", "verdict": "verdict"},
    )
    graph.add_edge("existence_verdict", "format")
    graph.add_edge("verdict", "format")
    graph.add_edge("format", END)
    return graph.compile()


agent = build_agent()


async def run_agent(claim: str) -> dict:
    start = time.time()
    initial_state: AgentState = {
        "claim": claim, "claim_tier": "", "match_context": {},
        "raw_verdict": "", "verdict": "", "confidence": 0.0,
        "explanation": "", "citations": [], "card": {},
        "latency_ms": 0.0, "token_usage": {}, "error": None,
    }
    result = await agent.ainvoke(initial_state)
    result["latency_ms"] = round((time.time() - start) * 1000, 1)
    print(f"[TIMING] === TOTAL: {result['latency_ms']}ms  tier={result.get('claim_tier')} ===")
    return result
