"""
MatchMind Streamlit Frontend
Live sports argument verification for the 2026 FIFA World Cup.
"""

import os
import streamlit as st
import httpx
import asyncio
import json
from datetime import datetime

# ─── Page config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="MatchMind",
    page_icon="🎯",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ─── Styling ─────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;900&family=JetBrains+Mono:wght@400;600&display=swap');

/* Base */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #0a0a0a;
    color: #f0f0f0;
}

.stApp { background-color: #0a0a0a; }

/* Hide Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
[data-testid="collapsedControl"] { visibility: visible !important; }
.block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 720px; }

/* Header */
.mm-header {
    text-align: center;
    padding: 2rem 0 1rem 0;
    border-bottom: 1px solid #1e1e1e;
    margin-bottom: 2rem;
}
.mm-logo {
    font-size: 2.8rem;
    font-weight: 900;
    letter-spacing: -0.03em;
    color: #ffffff;
    line-height: 1;
}
.mm-logo span {
    color: #00e676;
}
.mm-tagline {
    font-size: 0.85rem;
    color: #666;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-top: 0.4rem;
}

/* Input area */
.stTextArea textarea {
    background-color: #111 !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 8px !important;
    color: #f0f0f0 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 1rem !important;
    resize: none !important;
}
.stTextArea textarea:focus {
    border-color: #00e676 !important;
    box-shadow: 0 0 0 1px #00e676 !important;
}

/* Button */
.stButton > button {
    background-color: #00e676 !important;
    color: #0a0a0a !important;
    font-weight: 700 !important;
    font-size: 0.95rem !important;
    letter-spacing: 0.02em !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.6rem 2rem !important;
    width: 100% !important;
    transition: background-color 0.15s ease !important;
}
.stButton > button:hover {
    background-color: #00c853 !important;
}

/* Verdict card */
.verdict-card {
    background: #111;
    border: 1px solid #1e1e1e;
    border-radius: 12px;
    padding: 1.5rem;
    margin-top: 1.5rem;
}
.verdict-card.supported { border-left: 4px solid #00e676; }
.verdict-card.refuted { border-left: 4px solid #ff1744; }
.verdict-card.partial { border-left: 4px solid #ffab00; }
.verdict-card.insufficient { border-left: 4px solid #555; }

.verdict-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 1rem;
}
.verdict-emoji { font-size: 2rem; line-height: 1; }
.verdict-label {
    font-size: 1.1rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
.verdict-label.supported { color: #00e676; }
.verdict-label.refuted { color: #ff1744; }
.verdict-label.partial { color: #ffab00; }
.verdict-label.insufficient { color: #888; }

.confidence-bar-bg {
    background: #1e1e1e;
    border-radius: 4px;
    height: 4px;
    margin: 0.5rem 0 1rem 0;
    overflow: hidden;
}
.confidence-bar-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.5s ease;
}

.claim-text {
    font-size: 1rem;
    color: #aaa;
    font-style: italic;
    margin-bottom: 1rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid #1e1e1e;
}
.claim-text span { color: #f0f0f0; font-style: normal; }

.explanation {
    font-size: 1rem;
    line-height: 1.6;
    color: #e0e0e0;
    margin-bottom: 1rem;
}

.citations-label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #555;
    margin-bottom: 0.5rem;
}
.citation-pill {
    display: inline-block;
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 4px;
    padding: 0.2rem 0.6rem;
    font-size: 0.8rem;
    font-family: 'JetBrains Mono', monospace;
    color: #aaa;
    margin: 0.15rem 0.15rem 0.15rem 0;
}

.meta-row {
    display: flex;
    gap: 1.5rem;
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid #1e1e1e;
    flex-wrap: wrap;
}
.meta-item {
    font-size: 0.75rem;
    color: #555;
    font-family: 'JetBrains Mono', monospace;
}
.meta-item span { color: #888; }

.share-text-box {
    background: #0d0d0d;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    padding: 0.75rem 1rem;
    font-size: 0.85rem;
    color: #888;
    margin-top: 1rem;
    font-family: 'JetBrains Mono', monospace;
    word-break: break-all;
}

/* Match snapshot */
.match-snapshot {
    background: #0d0d0d;
    border: 1px solid #1e1e1e;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    margin-bottom: 1rem;
    font-size: 0.8rem;
    color: #666;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.match-teams {
    font-weight: 600;
    color: #aaa;
    font-size: 0.85rem;
}
.match-score {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
    color: #00e676;
    font-size: 1rem;
}

/* Live indicator */
.live-dot {
    display: inline-block;
    width: 7px;
    height: 7px;
    background: #ff1744;
    border-radius: 50%;
    margin-right: 0.4rem;
    animation: pulse 1.5s infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
}

/* Error */
.error-box {
    background: #1a0a0a;
    border: 1px solid #3d1010;
    border-radius: 8px;
    padding: 1rem;
    color: #ff6b6b;
    font-size: 0.9rem;
    margin-top: 1rem;
}

/* Example claims */
.examples-label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #444;
    margin-bottom: 0.5rem;
    margin-top: 1.5rem;
}

/* Sidebar */
[data-testid="stSidebar"] { background-color: #ffffff !important; }
[data-testid="stSidebar"] *,
[data-testid="stSidebar"] [data-testid="stMetricLabel"],
[data-testid="stSidebar"] [data-testid="stMetricValue"],
[data-testid="stSidebar"] [data-testid="stMetricDelta"],
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] small,
[data-testid="stSidebar"] label { color: #000000 !important; }

/* Native Streamlit component text */
h1, h2, h3, h4, h5, h6,
p, span,
[data-testid="stMarkdownContainer"] p,
[data-testid="stCaptionContainer"] p,
[data-testid="stMetricLabel"],
[data-testid="stMetricValue"],
[data-testid="stMetricDelta"],
.stProgress > div > div > div > div { color: #f0f0f0 !important; }
</style>
""", unsafe_allow_html=True)

# ─── Config ───────────────────────────────────────────────────────────────────

BACKEND_URL = os.getenv("BACKEND_URL", "https://web-production-5bbd2.up.railway.app")

EXAMPLE_CLAIMS = [
    "Brazil is winning their match right now",
    "France has scored more goals than Argentina",
    "The USA is playing today",
    "Morocco is top of their group",
    "Mbappe has scored in this game",
]

VERDICT_CLASS = {
    "SUPPORTED": "supported",
    "REFUTED": "refuted",
    "PARTIALLY_SUPPORTED": "partial",
    "INSUFFICIENT_DATA": "insufficient",
}

CONFIDENCE_COLOR = {
    "SUPPORTED": "#00e676",
    "REFUTED": "#ff1744",
    "PARTIALLY_SUPPORTED": "#ffab00",
    "INSUFFICIENT_DATA": "#555",
}


# ─── API calls ────────────────────────────────────────────────────────────────

def verify_claim(claim: str) -> dict:
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                f"{BACKEND_URL}/verify",
                json={"claim": claim},
            )
            resp.raise_for_status()
            return {"ok": True, "data": resp.json()}
    except httpx.TimeoutException:
        return {"ok": False, "error": "Request timed out — the backend may be starting up. Try again."}
    except httpx.ConnectError:
        return {"ok": False, "error": "Cannot reach the backend at localhost:8000. Is python main.py running?"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_summary() -> dict:
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{BACKEND_URL}/evals/summary")
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return {}


def get_live_matches() -> dict:
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{BACKEND_URL}/matches/live")
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return {}


# ─── Sidebar: eval summary ───────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### MatchMind Stats")
    summary = get_summary()

    if not summary or summary.get("total_verdicts", 0) == 0:
        st.caption("No verdicts stored yet.")
    else:
        n = summary["total_verdicts"]
        st.metric("Total verdicts", n)

        st.markdown("**Latency**")
        c1, c2, c3 = st.columns(3)
        c1.metric("Avg", f"{summary['avg_latency_ms']:.0f}ms")
        c2.metric("p50", f"{summary['p50_latency_ms']:.0f}ms")
        c3.metric("p95", f"{summary['p95_latency_ms']:.0f}ms")

        st.metric("Avg tokens / LLM call", f"{summary['avg_total_tokens']:.0f}")

        st.markdown("**Eval scores**")
        st.metric("Overall", f"{summary['avg_eval_score']:.3f}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Citation", f"{summary['avg_citation_score']:.2f}")
        c2.metric("Position", f"{summary['avg_position_score']:.2f}")
        c3.metric("Concision", f"{summary['avg_concision_score']:.2f}")

        dist = summary.get("verdict_distribution", {})
        if dist:
            st.markdown("**Verdict distribution**")
            for label, emoji in [
                ("SUPPORTED", "✅"),
                ("REFUTED", "❌"),
                ("PARTIALLY_SUPPORTED", "⚠️"),
                ("INSUFFICIENT_DATA", "❓"),
            ]:
                count = dist.get(label, 0)
                pct = round(count / n * 100)
                st.markdown(f"{emoji} {label.replace('_', ' ')}  \n`{count}` ({pct}%)")

        flags = summary.get("flag_counts", {})
        if flags:
            st.markdown("**Quality flags**")
            for flag, count in sorted(flags.items(), key=lambda x: -x[1]):
                st.markdown(f"`{flag}` — {count}")

    if st.button("Refresh", use_container_width=True):
        st.rerun()

# ─── Header ──────────────────────────────────────────────────────────────────

st.markdown("""
<div class="mm-header">
    <div class="mm-logo">Match<span>Mind</span></div>
    <div class="mm-tagline">Live World Cup argument verification · WC 2026</div>
</div>
""", unsafe_allow_html=True)

# ─── Live match ticker ────────────────────────────────────────────────────────

live_data = get_live_matches()
matches = live_data.get("matches", [])

if matches:
    live_matches = [m for m in matches if m.get("status") == "LIVE"]
    if live_matches:
        m = live_matches[0]
        score = f"{m['home_score']} - {m['away_score']}" if m['home_score'] is not None else "0 - 0"
        minute = f"{m['minute']}'" if m.get('minute') else ""
        st.markdown(f"""
        <div class="match-snapshot">
            <div>
                <span class="live-dot"></span>
                <span style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.08em;color:#ff1744">Live</span>
                &nbsp;·&nbsp;
                <span class="match-teams">{m['home_team']} vs {m['away_team']}</span>
            </div>
            <div>
                <span class="match-score">{score}</span>
                {f'<span style="color:#555;font-size:0.75rem;margin-left:0.5rem">{minute}</span>' if minute else ''}
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        m = matches[0]
        st.markdown(f"""
        <div class="match-snapshot">
            <div>
                <span style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.08em;color:#555">Upcoming</span>
                &nbsp;·&nbsp;
                <span class="match-teams">{m['home_team']} vs {m['away_team']}</span>
            </div>
            <div style="font-size:0.75rem;color:#555">{m.get('stage','').replace('_',' ').title()}</div>
        </div>
        """, unsafe_allow_html=True)

# ─── Input ────────────────────────────────────────────────────────────────────

claim = st.text_area(
    label="Your claim",
    placeholder="e.g. Brazil is winning their match right now...",
    height=90,
    label_visibility="collapsed",
)

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    submit = st.button("Verify claim →", use_container_width=True)

# Example claims
st.markdown('<div class="examples-label">Try an example</div>', unsafe_allow_html=True)
for i, example in enumerate(EXAMPLE_CLAIMS):
    if st.button(example, key=f"ex_{i}", use_container_width=True):
        claim = example
        submit = True

# ─── Verdict ──────────────────────────────────────────────────────────────────

if submit and claim and claim.strip():
    claim = claim.strip()
    with st.spinner("Checking live data…"):
        result = verify_claim(claim)

    if not result["ok"]:
        st.error(f"⚠️ {result['error']}")
    else:
        d = result["data"]
        verdict = d["verdict"]
        confidence = d["confidence"]

        # Verdict + confidence
        st.subheader(f"{d['verdict_emoji']} {verdict.replace('_', ' ')}")
        st.progress(confidence / 100, text=f"{confidence}% confidence")

        # Match snapshot
        snapshot = d.get("match_snapshot")
        if snapshot:
            raw_score = snapshot.get("score", "")
            score = "— : —" if not raw_score or "None" in raw_score else raw_score
            minute = f"  ·  {snapshot['minute']}'" if snapshot.get("minute") else ""
            st.caption(f"**{snapshot['home']} vs {snapshot['away']}**  ·  {score}{minute}")

        # Claim + explanation
        st.markdown(f"*Claim: \"{claim}\"*")
        st.write(d["explanation"])

        # Citations
        citations = d.get("citations", [])
        if citations:
            st.caption("Citations: " + "  ·  ".join(citations))
        else:
            st.caption("No citations available")

        # Share — only shown for actionable verdicts
        if verdict != "INSUFFICIENT_DATA":
            st.caption("Share")
            st.markdown(
                f'<div style="background:#ffffff;color:#000000;padding:0.75rem 1rem;border-radius:6px;'
                f'font-family:monospace;font-size:0.85rem;word-break:break-all;">{d["share_text"]}</div>',
                unsafe_allow_html=True,
            )

        # Metrics
        token_usage = d.get("token_usage") or {}
        total_tokens = token_usage.get("total_tokens", 0)
        latency = d.get("latency_ms", 0)
        eval_scores = d.get("eval_scores", {})
        overall = eval_scores.get("overall", 0)
        tier = token_usage.get("tier", "—").replace("_", " ")

        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Latency", f"{latency:.0f} ms")
        c2.metric("Tokens", total_tokens)
        c3.metric("Eval", f"{overall:.2f}")
        c4.metric("Tier", tier)

elif submit and not (claim and claim.strip()):
    st.warning("Enter a claim to verify.")

# ─── Footer ──────────────────────────────────────────────────────────────────

st.markdown("""
<div style="text-align:center;margin-top:3rem;padding-top:1rem;border-top:1px solid #1a1a1a;font-size:0.75rem;color:#333">
    MatchMind · 2026 FIFA World Cup · Powered by Gemini 2.5 Flash + LangGraph
</div>
""", unsafe_allow_html=True)
