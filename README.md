# MatchMind 🎯

**Live sports argument verification agent for the 2026 FIFA World Cup.**

Drop a sports claim during a live match → get a data-backed verdict (p50 ~2.6s) with a shareable card.

> *"Brazil is going to win this game"* → ❌ REFUTED (78% confidence) — Brazil are currently losing 0-2 in the 67th minute.

---

## Architecture

```
User claim
    │
    ▼
FastAPI gateway (/verify)
    │
    ▼
LangGraph 5-node agent
  ┌──────────────────────────────────────────────────────────┐
  │  [classify] → [fetch] → [existence_verdict]  → [format]  │
  │                       ↘ [verdict (Gemini)]  ↗            │
  └──────────────────────────────────────────────────────────┘
       │            │              │                  │
       ▼            ▼              ▼                  ▼
  3-tier       MCP server     No LLM call        Shareable
  routing      (football-     (EXISTENCE)        card JSON
               data.org)      Gemini 2.5
                              Flash (others)
       │                                              │
       ▼                                              ▼
  Redis cache                                   MongoDB Atlas
  (Upstash)                                     (verdict store)
```

### Claim routing tiers

Before fetching any data, a `classify_node` routes every claim into one of three tiers:

| Tier | Trigger | Gemini called? | Context sent | Typical tokens |
|---|---|---|---|---|
| `EXISTENCE` | "is playing", "playing today", "has a match" | No | — | 0 |
| `SIMPLE_STAT` | "score", "winning", "losing", "scored", "goal" | Yes | live matches + match details only | ~300–500 |
| `COMPLEX` | standings, comparisons, predictions | Yes | full context + standings | ~800–1500 |

EXISTENCE claims skip Gemini entirely and are answered directly from fetched match data (~100–200 ms vs ~2–3 s).

---

## Agent Engineering Coverage

| Capability | Implementation |
|---|---|
| **Agent/harness engineering** | LangGraph `StateGraph` with typed `AgentState` flowing through all nodes |
| **Claim routing / classification** | `classify_node` — keyword-based 3-tier routing (EXISTENCE → SIMPLE_STAT → COMPLEX) before any fetch |
| **Retrieval engineering** | `fetch_node` — fetches only what the tier needs (no standings for EXISTENCE/SIMPLE_STAT) |
| **Prompt/context engineering** | `verdict_node` — structured system prompt + JSON-forced output; SIMPLE_STAT strips context to relevant match only |
| **Tools and skills (MCP)** | Custom MCP server wrapping football-data.org: `get_live_matches`, `get_match_details`, `get_team_standings` |
| **Evals and benchmarking** | Deterministic eval framework: citation score, position score, concision score — stored with every verdict |
| **LangGraph** | 5-node compiled graph with conditional edges, async nodes, typed state |
| **API gateways/routing** | FastAPI with `/verify`, `/matches/live`, `/evals/recent`, `/evals/summary` — Redis-cached MCP passthrough |
| **Observability** | `GET /evals/summary` aggregates total verdicts, avg/p50/p95 latency, avg tokens per LLM call, eval score breakdown, verdict distribution, flag counts from MongoDB |
| **Frontend** | Streamlit UI with live match ticker, verdict card, tier/token/latency/eval metrics, and live observability sidebar |

---

## Stack

- **Backend**: FastAPI + Python 3.11
- **Agent**: LangGraph (classify → fetch → verdict/existence_verdict → format)
- **LLM**: Gemini 2.5 Flash
- **Live data**: football-data.org (free tier)
- **Cache**: Redis via Upstash (free tier, 30s TTL)
- **Storage**: MongoDB Atlas (free tier)
- **Frontend**: Streamlit

---

## Setup

```bash
# Requires Python 3.11+
git clone https://github.com/hongjasmine/MatchMind
cd MatchMind
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in: GOOGLE_API_KEY, FOOTBALL_DATA_API_KEY, MONGODB_URI, REDIS_URL
```

**Get your free API keys:**
- Gemini: [aistudio.google.com](https://aistudio.google.com)
- football-data.org: [football-data.org/client/register](https://www.football-data.org/client/register)
- MongoDB Atlas: [mongodb.com/atlas](https://mongodb.com/atlas) (free M0 tier)
- Upstash Redis: [upstash.com](https://upstash.com) (free tier)

```bash
# Run smoke tests (no API keys needed)
python tests/test_smoke.py

# Start the backend
python main.py
# → http://localhost:8000/docs

# Start the frontend (separate terminal)
streamlit run streamlit_app.py
# → http://localhost:8501
```

---

## Usage

```bash
curl -X POST http://localhost:8000/verify \
  -H "Content-Type: application/json" \
  -d '{"claim": "France has scored more goals than Argentina in this tournament"}'
```

Response:
```json
{
  "verdict": "SUPPORTED",
  "verdict_emoji": "✅",
  "confidence": 87,
  "explanation": "France have scored 8 goals vs Argentina's 6 through the group stage.",
  "citations": ["France: 8 goals for", "Argentina: 6 goals for"],
  "share_text": "✅ \"France has scored more...\" → SUPPORTED (87% confidence) | MatchMind #WC2026",
  "latency_ms": 1840,
  "token_usage": {
    "tier": "COMPLEX",
    "prompt_tokens": 912,
    "completion_tokens": 88,
    "total_tokens": 1000
  },
  "eval_scores": {
    "citation_score": 0.85,
    "position_score": 0.97,
    "concision_score": 1.0,
    "overall": 0.94,
    "flags": []
  }
}
```

---

## MCP Tools

| Tool | Description |
|---|---|
| `get_live_matches()` | All currently live WC 2026 matches with scores and minute |
| `get_match_details(match_id)` | Lineups, goals, bookings for a specific match |
| `get_team_standings(team_name)` | Group table position and stats for a team |

---

## Eval Framework

Every verdict is scored on three deterministic dimensions (no LLM, runs in microseconds):

| Dimension | Weight | What it checks |
|---|---|---|
| **Citation score** | 40% | Did the verdict cite specific data points? Penalized if claim is stat-based but citations contain no numbers. |
| **Position score** | 40% | Did the agent take a clear, confident stance? SUPPORTED/REFUTED score higher than INSUFFICIENT_DATA. |
| **Concision score** | 20% | Is the explanation 15–40 words? Too brief (≤10) or too verbose (>60) both lose points. |

Scores are stored in MongoDB and accessible at `GET /evals/recent`. The Streamlit UI shows the overall score live with each verdict.

### Aggregate observability — `GET /evals/summary`

```json
{
  "total_verdicts": 57,
  "avg_latency_ms": 2662.3,
  "p50_latency_ms": 2559.4,
  "p95_latency_ms": 6521.4,
  "avg_total_tokens": 1268.6,
  "avg_eval_score": 0.605,
  "avg_citation_score": 0.409,
  "avg_position_score": 0.682,
  "avg_concision_score": 0.841,
  "verdict_distribution": {
    "SUPPORTED": 18, "REFUTED": 9,
    "PARTIALLY_SUPPORTED": 7, "INSUFFICIENT_DATA": 8
  },
  "flag_counts": {
    "CITATIONS_LACK_NUMBERS": 5,
    "INSUFFICIENT_DATA_VERDICT": 8
  }
}
```

`avg_total_tokens` excludes EXISTENCE-tier calls (0 tokens) to give a meaningful per-LLM-call cost baseline. `avg_eval_score` is always consistent with the three sub-scores: `citation×0.40 + position×0.40 + concision×0.20`.

---

## Token efficiency by tier

Terminal output for every request:
```
[ROUTING] tier=EXISTENCE  (0.1ms)
# → 0 tokens, ~150ms total

[TOKENS] tier=SIMPLE_STAT  prompt=312  completion=87  total=399
# → ~400 tokens, ~1.2s total

[TOKENS] tier=COMPLEX  prompt=912  completion=88  total=1000
# → ~1000 tokens, ~2.5s total
```

---

Built during the 2026 FIFA World Cup (June 11 – July 19, 2026).
