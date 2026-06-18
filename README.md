# MatchMind 🎯

**Live sports argument verification agent for the 2026 FIFA World Cup.**

Drop a sports claim during a live match → get a data-backed verdict in under 3 seconds with a shareable card.

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
LangGraph 3-node agent
  ┌─────────────────────────────────────┐
  │  [fetch] → [verdict] → [format]     │
  └─────────────────────────────────────┘
       │            │            │
       ▼            ▼            ▼
  MCP server    Gemini 2.5   Shareable
  (football-    Flash LLM    card JSON
  data.org)
       │                         │
       ▼                         ▼
  Redis cache              MongoDB Atlas
  (Upstash)                (verdict store)
```

## Agent Engineering Coverage

| Capability | Implementation |
|---|---|
| **Agent/harness engineering** | LangGraph `StateGraph` with typed `AgentState` flowing through all nodes |
| **Retrieval engineering** | `fetch_node` — intelligent MCP tool selection based on claim content |
| **Prompt/context engineering** | `verdict_node` — structured system prompt + JSON-forced output schema |
| **Tools and skills (MCP)** | Custom MCP server wrapping football-data.org: `get_live_matches`, `get_match_details`, `get_team_standings` |
| **Evals and benchmarking** | Deterministic eval framework: citation score, position score, concision score — stored with every verdict |
| **LangGraph** | 3-node compiled graph with async nodes, typed state, `END` edge |
| **API gateways/routing** | FastAPI with `/verify`, `/matches/live`, `/evals/recent` — Redis-cached MCP passthrough |

## Stack

- **Backend**: FastAPI + Python 3.11
- **Agent**: LangGraph (fetch → verdict → format)
- **LLM**: Gemini 2.5 Flash
- **Live data**: football-data.org (free tier)
- **Cache**: Redis via Upstash (free tier, 30s TTL)
- **Storage**: MongoDB Atlas (free tier)
- **Deployment**: Railway → GCP Cloud Run

## Setup

```bash
git clone https://github.com/yourusername/matchmind
cd matchmind
python -m venv venv && source venv/bin/activate
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

# Start the server
python main.py
# → http://localhost:8000/docs
```

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
  "eval_scores": {
    "citation_score": 0.85,
    "position_score": 0.97,
    "concision_score": 1.0,
    "overall": 0.94,
    "flags": []
  }
}
```

## MCP Tools

| Tool | Description |
|---|---|
| `get_live_matches()` | All currently live WC 2026 matches with scores and minute |
| `get_match_details(match_id)` | Lineups, goals, bookings for a specific match |
| `get_team_standings(team_name)` | Group table position and stats for a team |

## Eval Framework

Every verdict is scored on three dimensions:

- **Citation score** (40% weight) — did the verdict cite specific data points with numbers?
- **Position score** (40% weight) — did the agent take a clear, confident stance?
- **Concision score** (20% weight) — is the explanation 15-40 words (right for live-match use)?

Scores are stored in MongoDB and accessible at `GET /evals/recent`.

## Deployment (Railway)

```bash
# Install Railway CLI
npm install -g @railway/cli
railway login
railway init
railway up
```

Set env vars in Railway dashboard → match your `.env` file.

---

Built during the 2026 FIFA World Cup (June 11 – July 19, 2026).
