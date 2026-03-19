"""
Test 1: Multi-Provider Routing Through Bifrost
===============================================
Tests Bifrost's core value proposition: one endpoint, multiple providers.

What this does:
  1. Sends the same prompt to OpenAI (gpt-4o-mini) through Bifrost
  2. Sends the same prompt to Anthropic (claude-3-5-haiku) through Bifrost
  3. Tests failover behavior with an intentionally invalid model

How it calls the gateway:
  Uses the standard OpenAI Python SDK with one change: base_url points to
  Bifrost instead of api.openai.com. This is Bifrost's core pitch — change
  one line, access any provider through a unified API.

What we're testing:
  - Provider abstraction: same SDK, same code → different providers
  - Format translation: OpenAI SDK format → Anthropic's native API
  - Failover behavior: what happens when a model doesn't exist?

Usage:
  1. Ensure Bifrost is running at localhost:8080
  2. Ensure both OpenAI and Anthropic providers are configured in Bifrost
  3. Run: conda run -n bifrost-eval python tests/test_routing.py
"""

import json
import os
import sys
import time

from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

BIFROST_BASE_URL = os.getenv("BIFROST_BASE_URL", "http://localhost:8080")

# The key insight: same OpenAI client, same code — Bifrost handles routing.
# The API key is "managed-by-bifrost" because Bifrost holds the real provider keys.
client = OpenAI(
    base_url=f"{BIFROST_BASE_URL}/openai/v1",
    api_key="managed-by-bifrost",
)

PROMPT = "Explain what an AI gateway is in exactly 2 sentences."

MODELS = [
    {"name": "OpenAI GPT-4o-mini", "model": "openai/gpt-4o-mini"},
    {"name": "Anthropic Claude Opus 4.6", "model": "anthropic/claude-opus-4-6"},
]


# ---------------------------------------------------------------------------
# Test 1: Multi-Provider Routing
# ---------------------------------------------------------------------------

def test_multi_provider_routing():
    """Send the same prompt to multiple providers through Bifrost's single endpoint."""
    print("\n" + "=" * 70)
    print("TEST 1: Multi-Provider Routing")
    print("=" * 70)
    print(f'Prompt: "{PROMPT}"')
    print(f"Gateway: {BIFROST_BASE_URL}")
    print("-" * 70)

    results = []

    for model_info in MODELS:
        print(f"\n>> Sending to: {model_info['name']} ({model_info['model']})")

        start = time.time()
        try:
            response = client.chat.completions.create(
                model=model_info["model"],
                messages=[{"role": "user", "content": PROMPT}],
                max_tokens=150,
                temperature=0.7,
            )
            latency_ms = (time.time() - start) * 1000

            content = response.choices[0].message.content
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

            print(f"   Status: SUCCESS")
            print(f"   Latency: {latency_ms:.0f}ms")
            print(f"   Tokens: {usage}")
            print(f"   Response: {content[:200]}")

            results.append({
                "model": model_info["name"],
                "model_id": model_info["model"],
                "status": "SUCCESS",
                "latency_ms": round(latency_ms, 1),
                "tokens": usage,
                "response_preview": content[:200],
            })

        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            error_msg = str(e)
            print(f"   ERROR: {error_msg[:300]}")

            results.append({
                "model": model_info["name"],
                "model_id": model_info["model"],
                "status": "ERROR",
                "latency_ms": round(latency_ms, 1),
                "error": error_msg[:500],
            })

    return results


# ---------------------------------------------------------------------------
# Test 2: Failover Behavior
# ---------------------------------------------------------------------------

def test_failover_behavior():
    """Request a non-existent model and observe how Bifrost handles the failure."""
    print("\n" + "=" * 70)
    print("TEST 2: Failover Behavior")
    print("=" * 70)
    print("Scenario: Request a model that doesn't exist in Bifrost's config")
    print("Question: Does Bifrost fail gracefully? Does it route to a backup?")
    print("-" * 70)

    fake_model = "openai/gpt-nonexistent-model"
    print(f"\n>> Sending to non-existent model: {fake_model}")

    start = time.time()
    try:
        response = client.chat.completions.create(
            model=fake_model,
            messages=[{"role": "user", "content": PROMPT}],
            max_tokens=50,
        )
        latency_ms = (time.time() - start) * 1000

        # If we get here, Bifrost routed to a fallback — interesting finding
        content = response.choices[0].message.content
        print(f"   UNEXPECTED SUCCESS — Bifrost routed to a fallback!")
        print(f"   Latency: {latency_ms:.0f}ms")
        print(f"   Response: {content[:200]}")

        return {
            "status": "FALLBACK_ROUTED",
            "latency_ms": round(latency_ms, 1),
            "response": content[:200],
            "observation": "Bifrost silently routed to a fallback model — good for reliability, "
                           "but the developer should know which model actually served the request.",
        }

    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        error_msg = str(e)
        print(f"   Expected error received: {error_msg[:300]}")
        print(f"   Latency: {latency_ms:.0f}ms")

        return {
            "status": "ERROR_RETURNED",
            "latency_ms": round(latency_ms, 1),
            "error": error_msg[:500],
            "observation": "Check: Is the error message clear enough to debug? "
                           "Does it tell the developer what models ARE available?",
        }


# ---------------------------------------------------------------------------
# Results Summary
# ---------------------------------------------------------------------------

def print_summary(routing_results, failover_result):
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    print("\nMulti-Provider Routing:")
    for r in routing_results:
        icon = "PASS" if r["status"] == "SUCCESS" else "FAIL"
        print(f"  [{icon}] {r['model']}: {r['status']} ({r['latency_ms']:.0f}ms)")

    print(f"\nFailover Behavior:")
    print(f"  Result: {failover_result['status']} ({failover_result['latency_ms']:.0f}ms)")
    print(f"  Observation: {failover_result.get('observation', 'N/A')}")

    # Save structured results to JSON
    results_path = os.path.join(os.path.dirname(__file__), "results", "routing_results.json")
    output = {
        "test": "multi_provider_routing",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "bifrost_url": BIFROST_BASE_URL,
        "prompt": PROMPT,
        "routing_results": routing_results,
        "failover_result": failover_result,
    }
    os.makedirs(os.path.dirname(results_path), exist_ok=True)
    with open(results_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to: {results_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import requests as req

    print("Bifrost Product Evaluation — Routing Test")
    print(f"Gateway: {BIFROST_BASE_URL}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Connectivity check
    try:
        health = req.get(f"{BIFROST_BASE_URL}/health", timeout=5)
        print(f"Bifrost health: {health.status_code}")
    except req.exceptions.ConnectionError:
        print(f"\nERROR: Cannot connect to Bifrost at {BIFROST_BASE_URL}")
        print("Make sure Bifrost is running: npx -y @maximhq/bifrost")
        sys.exit(1)

    routing_results = test_multi_provider_routing()
    failover_result = test_failover_behavior()
    print_summary(routing_results, failover_result)
