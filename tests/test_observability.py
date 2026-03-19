"""
Test 2: Auto-Capture Observability Verification
================================================
Validates Bifrost's "zero-config observability" claim across BOTH providers.

What this does:
  1. Sends a request with a unique marker to OpenAI (gpt-4o-mini) through Bifrost
  2. Sends a request with a unique marker to Anthropic (claude-opus-4-6) through Bifrost
  3. Queries Bifrost's local SQLite database to find both requests
  4. Reports what metadata was captured for each — and compares fidelity across providers

How it calls the gateway:
  Uses the OpenAI SDK pointed at Bifrost (same as test_routing.py).
  After the requests, reads directly from ~/.config/bifrost/logs.db.

Why this matters:
  Bifrost claims all traffic metadata is captured automatically with <0.1ms
  overhead and zero SDK instrumentation. This test verifies that claim by
  checking exactly what fields are populated for known requests — and whether
  capture quality is consistent across providers.

What we're testing:
  - Is the "zero-config" claim true? (no SDK needed)
  - What metadata is captured automatically? (prompt, response, tokens, cost, latency)
  - Is capture fidelity the same for OpenAI and Anthropic?
  - Are there any gaps? (missing fields, inaccurate costs)

Usage:
  1. Ensure Bifrost is running at localhost:8080
  2. Ensure both OpenAI and Anthropic providers are configured
  3. Run: conda run -n bifrost-eval python tests/test_observability.py
"""

import json
import os
import sqlite3
import sys
import time
import uuid

from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

BIFROST_BASE_URL = os.getenv("BIFROST_BASE_URL", "http://localhost:8080")
BIFROST_LOGS_DB = os.path.expanduser("~/.config/bifrost/logs.db")

client = OpenAI(
    base_url=f"{BIFROST_BASE_URL}/openai/v1",
    api_key="managed-by-bifrost",
)

MODELS_TO_TEST = [
    {"name": "OpenAI GPT-4o-mini", "model": "openai/gpt-4o-mini"},
    {"name": "Anthropic Claude Opus 4.6", "model": "anthropic/claude-opus-4-6"},
]

FIELDS_TO_CHECK = [
    ("id", "Request ID"),
    ("provider", "Provider Name"),
    ("model", "Model Name"),
    ("status", "Request Status"),
    ("latency", "Latency (ms)"),
    ("cost", "Cost ($)"),
    ("prompt_tokens", "Prompt Tokens"),
    ("completion_tokens", "Completion Tokens"),
    ("total_tokens", "Total Tokens"),
    ("input_history", "Prompt/Messages"),
    ("output_message", "Response"),
    ("tool_calls", "Tool Calls"),
    ("params", "Request Parameters"),
    ("stream", "Streaming Flag"),
    ("selected_key_id", "API Key Used"),
    ("virtual_key_id", "Virtual Key"),
    ("timestamp", "Timestamp"),
]


# ---------------------------------------------------------------------------
# Step 1: Send traced requests to each provider
# ---------------------------------------------------------------------------

def send_traced_request(model_id, model_name, marker):
    """Send a request with a unique marker we can search for in the logs."""
    prompt = f"{marker}: Explain observability in distributed systems in 2 sentences."

    print(f"\n>> Sending traced request to {model_name}")
    print(f"   Marker: {marker}")
    print(f"   Model: {model_id}")

    start = time.time()
    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.7,
        )
        latency_ms = (time.time() - start) * 1000

        content = response.choices[0].message.content
        sdk_usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

        print(f"   SDK response received: {latency_ms:.0f}ms")
        print(f"   SDK tokens: {sdk_usage}")

        return {
            "status": "SUCCESS",
            "model": model_id,
            "marker": marker,
            "prompt": prompt,
            "response": content,
            "sdk_latency_ms": round(latency_ms, 1),
            "sdk_usage": sdk_usage,
        }

    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        print(f"   ERROR: {str(e)[:300]}")
        return {"status": "ERROR", "model": model_id, "marker": marker, "error": str(e)[:500]}


# ---------------------------------------------------------------------------
# Step 2: Query Bifrost's SQLite database for a traced request
# ---------------------------------------------------------------------------

def query_logs_for_marker(marker, max_wait_seconds=10):
    """Search the Bifrost logs database for a unique marker."""
    if not os.path.exists(BIFROST_LOGS_DB):
        print(f"   ERROR: Logs database not found at {BIFROST_LOGS_DB}")
        return None

    for attempt in range(max_wait_seconds):
        conn = sqlite3.connect(BIFROST_LOGS_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM logs WHERE input_history LIKE ? ORDER BY created_at DESC LIMIT 1",
            (f"%{marker}%",),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            print(f"   Found after {attempt + 1}s")
            return dict(row)

        time.sleep(1)

    print(f"   NOT FOUND after {max_wait_seconds}s")
    return None


# ---------------------------------------------------------------------------
# Step 3: Analyze capture for a single provider
# ---------------------------------------------------------------------------

def analyze_single_capture(log_entry, sdk_data, provider_label):
    """Analyze what Bifrost captured for one provider's request."""
    if log_entry is None:
        return {"status": "NOT_FOUND", "captured": 0, "missing": len(FIELDS_TO_CHECK), "details": {}}

    captured = 0
    missing = 0
    details = {}

    for field_name, display_name in FIELDS_TO_CHECK:
        value = log_entry.get(field_name)

        # Special handling for fields that are legitimately empty
        if field_name == "tool_calls" and not value:
            status = "N/A"
            captured += 1  # not a gap — no tools were in the request
        elif field_name in ("input_history", "output_message", "params"):
            status = "CAPTURED" if value else "MISSING"
            if status == "CAPTURED":
                captured += 1
            else:
                missing += 1
        elif value is not None and value != "" and value != 0:
            status = "CAPTURED"
            captured += 1
        else:
            status = "MISSING"
            missing += 1

        details[field_name] = {
            "status": status,
            "value": str(value)[:200] if value else None,
            "display_name": display_name,
        }

    # Token cross-check
    sdk_usage = sdk_data.get("sdk_usage", {})
    token_matches = {}
    for token_field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        sdk_val = sdk_usage.get(token_field)
        bf_val = log_entry.get(token_field)
        token_matches[token_field] = sdk_val == bf_val

    capture_rate = captured / (captured + missing) * 100 if (captured + missing) > 0 else 0

    return {
        "status": "ANALYZED",
        "captured": captured,
        "missing": missing,
        "capture_rate": round(capture_rate, 1),
        "token_matches": token_matches,
        "all_tokens_match": all(token_matches.values()),
        "details": details,
    }


# ---------------------------------------------------------------------------
# Step 4: Compare capture fidelity across providers
# ---------------------------------------------------------------------------

def print_comparison(results):
    """Print a side-by-side comparison of capture fidelity across providers."""
    print("\n" + "=" * 70)
    print("CROSS-PROVIDER CAPTURE COMPARISON")
    print("=" * 70)

    providers = list(results.keys())
    if len(providers) < 2:
        print("  Need at least 2 providers to compare.")
        return

    # Header
    header = f"  {'Field':<23}"
    for p in providers:
        header += f" {p:<15}"
    print(header)
    print("  " + "-" * (23 + 16 * len(providers)))

    # Per-field comparison
    discrepancies = []
    for field_name, display_name in FIELDS_TO_CHECK:
        row = f"  {display_name:<23}"
        statuses = []
        for p in providers:
            analysis = results[p]
            if analysis["status"] == "NOT_FOUND":
                status = "NOT_FOUND"
            else:
                status = analysis["details"].get(field_name, {}).get("status", "?")
            statuses.append(status)
            row += f" {status:<15}"
        print(row)

        # Flag discrepancies
        if len(set(statuses)) > 1 and "NOT_FOUND" not in statuses:
            discrepancies.append((display_name, dict(zip(providers, statuses))))

    # Summary
    print(f"\n  {'Provider':<23} {'Captured':<12} {'Missing':<12} {'Rate':<10} {'Tokens Match'}")
    print("  " + "-" * 70)
    for p in providers:
        a = results[p]
        if a["status"] == "NOT_FOUND":
            print(f"  {p:<23} {'N/A':<12} {'N/A':<12} {'N/A':<10} N/A")
        else:
            print(
                f"  {p:<23} {a['captured']:<12} {a['missing']:<12} "
                f"{a['capture_rate']:.0f}%{'':>6} {'YES' if a['all_tokens_match'] else 'MISMATCH'}"
            )

    if discrepancies:
        print(f"\n  DISCREPANCIES ({len(discrepancies)} fields differ across providers):")
        for field, status_map in discrepancies:
            parts = ", ".join(f"{p}: {s}" for p, s in status_map.items())
            print(f"    - {field}: {parts}")
    else:
        print(f"\n  No discrepancies — capture fidelity is identical across providers.")

    return discrepancies


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import requests as req

    print("Bifrost Product Evaluation — Observability Test")
    print(f"Gateway: {BIFROST_BASE_URL}")
    print(f"Logs DB: {BIFROST_LOGS_DB}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Connectivity check
    try:
        health = req.get(f"{BIFROST_BASE_URL}/health", timeout=5)
        print(f"Bifrost health: {health.status_code}")
    except req.exceptions.ConnectionError:
        print(f"\nERROR: Cannot connect to Bifrost at {BIFROST_BASE_URL}")
        sys.exit(1)

    # Step 1: Send traced requests to each provider
    all_sdk_data = {}
    all_log_entries = {}
    all_analyses = {}

    for model_info in MODELS_TO_TEST:
        marker = f"OBSTEST_{model_info['name'].split()[0].upper()}_{uuid.uuid4().hex[:8]}"
        sdk_data = send_traced_request(model_info["model"], model_info["name"], marker)

        if sdk_data["status"] != "SUCCESS":
            print(f"\n   Skipping log verification for {model_info['name']} (request failed)")
            all_sdk_data[model_info["name"]] = sdk_data
            all_analyses[model_info["name"]] = {"status": "REQUEST_FAILED"}
            continue

        all_sdk_data[model_info["name"]] = sdk_data

        # Step 2: Find it in the logs
        print(f"\n>> Searching logs for {model_info['name']}...")
        log_entry = query_logs_for_marker(marker)
        all_log_entries[model_info["name"]] = log_entry

        # Step 3: Analyze capture
        analysis = analyze_single_capture(log_entry, sdk_data, model_info["name"])
        all_analyses[model_info["name"]] = analysis

        # Print individual result
        print(f"\n   {model_info['name']}: {analysis['captured']} captured, "
              f"{analysis['missing']} missing ({analysis['capture_rate']:.0f}%), "
              f"tokens match: {analysis.get('all_tokens_match', 'N/A')}")

    # Step 4: Cross-provider comparison
    discrepancies = print_comparison(all_analyses)

    # Save results
    results_path = os.path.join(os.path.dirname(__file__), "results", "observability_results.json")
    output = {
        "test": "observability_auto_capture",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "models_tested": [m["model"] for m in MODELS_TO_TEST],
        "per_provider": {},
    }
    for name in all_sdk_data:
        output["per_provider"][name] = {
            "sdk_data": all_sdk_data[name],
            "bifrost_log_found": all_log_entries.get(name) is not None,
            "analysis": all_analyses[name],
        }
        if all_log_entries.get(name):
            output["per_provider"][name]["bifrost_log_fields"] = {
                k: str(v)[:200] if v else None
                for k, v in all_log_entries[name].items()
            }
    output["cross_provider_discrepancies"] = [
        {"field": f, "statuses": s} for f, s in (discrepancies or [])
    ]

    os.makedirs(os.path.dirname(results_path), exist_ok=True)
    with open(results_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to: {results_path}")
