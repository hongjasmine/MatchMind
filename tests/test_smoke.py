"""
Smoke tests — run with: python tests/test_smoke.py
Tests eval framework and card formatting without needing API keys.
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.evals.framework import evaluate_verdict, eval_summary


def test_eval_citation_score():
    result = {
        "verdict": "SUPPORTED",
        "confidence": 0.9,
        "explanation": "Brazil leads Group C with 6 points after winning both of their opening matches convincingly.",
        "citations": ["Brazil: 6 points", "2 wins from 2 games"],
    }
    scores = evaluate_verdict("Is Brazil top of their group?", result)
    assert scores["citation_score"] == 0.85, f"Got {scores['citation_score']}"
    assert scores["position_score"] > 0.8
    assert scores["concision_score"] == 1.0
    print(f"✅ citation test passed: {scores}")


def test_eval_low_confidence():
    result = {
        "verdict": "PARTIALLY_SUPPORTED",
        "confidence": 0.3,
        "explanation": "Some data supports this but it's unclear.",
        "citations": [],
    }
    scores = evaluate_verdict("Is Mbappe the top scorer?", result)
    assert "NO_CITATIONS" in scores["flags"]
    assert "LOW_CONFIDENCE" in scores["flags"]
    print(f"✅ low confidence test passed: {scores}")


def test_eval_verbose():
    long_explanation = " ".join(["word"] * 70)
    result = {
        "verdict": "REFUTED",
        "confidence": 0.8,
        "explanation": long_explanation,
        "citations": ["Score: 2-0", "Minute: 67"],
    }
    scores = evaluate_verdict("Is the game tied?", result)
    assert "TOO_VERBOSE" in scores["flags"]
    print(f"✅ verbose test passed: {scores}")


def test_eval_summary():
    results = [
        {"verdict": "SUPPORTED", "confidence": 0.9, "explanation": "Clear from data.", "citations": ["3 goals", "minute 45"]},
        {"verdict": "REFUTED", "confidence": 0.85, "explanation": "No.", "citations": ["Score 0-2"]},
    ]
    scores_list = [evaluate_verdict("claim", r) for r in results]
    summary = eval_summary(scores_list)
    assert summary["n"] == 2
    assert 0 <= summary["avg_overall"] <= 1
    print(f"✅ summary test passed: {summary}")


if __name__ == "__main__":
    test_eval_citation_score()
    test_eval_low_confidence()
    test_eval_verbose()
    test_eval_summary()
    print("\n✅ All smoke tests passed. Ready to wire up API keys and run main.py")
