"""
MatchMind Eval Framework
Three eval dimensions that map directly to the job description:
  1. citation_score   — did the verdict cite specific data points?
  2. position_score   — did it take a clear stance?
  3. concision_score  — was the explanation appropriately brief?

These scores are stored with every verdict and power the /evals/recent feed.
This is your benchmarking system for the resume bullet.
"""

from typing import TypedDict


class EvalScores(TypedDict):
    citation_score: float       # 0.0 – 1.0
    position_score: float       # 0.0 – 1.0
    concision_score: float      # 0.0 – 1.0
    overall: float              # Weighted average
    flags: list[str]            # Any quality issues flagged


def evaluate_verdict(claim: str, result: dict) -> EvalScores:
    """
    Deterministic eval — no LLM call, runs in microseconds.
    All scores are computed from the agent's output fields.
    """
    flags = []

    # ── Citation score ────────────────────────────────────────────────────────
    # Did the agent produce specific data citations?
    citations = result.get("citations", [])
    citation_count = len(citations)

    if citation_count == 0:
        citation_score = 0.0
        flags.append("NO_CITATIONS")
    elif citation_count == 1:
        citation_score = 0.6
    elif citation_count == 2:
        citation_score = 0.85
    else:
        citation_score = 1.0

    # Penalize vague citations only when the claim is about something
    # inherently numeric (score, points, goals, minute). Existence/scheduling
    # claims ("is X playing today") legitimately have no number to cite.
    stat_keywords = [
        "score", "win", "lose", "lost", "beat", "goal", "point",
        "minute", "lead", "ahead", "behind", "ranking", "standing",
        "top", "bottom", "first", "last", "tied", "draw",
    ]
    claim_is_stat_based = any(kw in claim.lower() for kw in stat_keywords)

    has_numbers = any(
        any(c.isdigit() for c in cite)
        for cite in citations
    )
    if citations and claim_is_stat_based and not has_numbers:
        citation_score *= 0.7
        flags.append("CITATIONS_LACK_NUMBERS")

    # ── Position score ────────────────────────────────────────────────────────
    # Did the agent take a clear, confident stance?
    verdict = result.get("verdict", "")
    confidence = result.get("confidence", 0.0)

    if verdict in ("SUPPORTED", "REFUTED"):
        position_score = min(1.0, confidence + 0.1)   # Reward clear verdicts
    elif verdict == "PARTIALLY_SUPPORTED":
        position_score = confidence
    elif verdict == "INSUFFICIENT_DATA":
        position_score = 0.3   # Acceptable, but not ideal
        flags.append("INSUFFICIENT_DATA_VERDICT")
    else:
        position_score = 0.0
        flags.append("NO_VERDICT")

    if confidence < 0.5:
        flags.append("LOW_CONFIDENCE")

    # ── Concision score ───────────────────────────────────────────────────────
    # Is the explanation tight? Target: 15-40 words.
    explanation = result.get("explanation", "")
    word_count = len(explanation.split())

    if word_count == 0:
        concision_score = 0.0
        flags.append("EMPTY_EXPLANATION")
    elif word_count <= 10:
        concision_score = 0.5    # Too brief — missing substance
        flags.append("TOO_BRIEF")
    elif word_count <= 40:
        concision_score = 1.0    # Sweet spot
    elif word_count <= 60:
        concision_score = 0.75   # Acceptable
    else:
        concision_score = 0.4    # Too verbose for live-match use
        flags.append("TOO_VERBOSE")

    # ── Overall (weighted) ────────────────────────────────────────────────────
    overall = round(
        (citation_score * 0.40) +
        (position_score * 0.40) +
        (concision_score * 0.20),
        3,
    )

    return EvalScores(
        citation_score=round(citation_score, 3),
        position_score=round(position_score, 3),
        concision_score=round(concision_score, 3),
        overall=overall,
        flags=flags,
    )


def eval_summary(scores_list: list[EvalScores]) -> dict:
    """Aggregate eval scores across multiple verdicts for benchmarking."""
    if not scores_list:
        return {}

    n = len(scores_list)
    return {
        "n": n,
        "avg_citation": round(sum(s["citation_score"] for s in scores_list) / n, 3),
        "avg_position": round(sum(s["position_score"] for s in scores_list) / n, 3),
        "avg_concision": round(sum(s["concision_score"] for s in scores_list) / n, 3),
        "avg_overall": round(sum(s["overall"] for s in scores_list) / n, 3),
        "flag_counts": {
            flag: sum(1 for s in scores_list if flag in s["flags"])
            for flag in [
                "NO_CITATIONS", "LOW_CONFIDENCE", "TOO_VERBOSE",
                "INSUFFICIENT_DATA_VERDICT", "CITATIONS_LACK_NUMBERS",
            ]
        },
    }
