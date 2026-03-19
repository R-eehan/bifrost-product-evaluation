"""
Test 2: Auto-Capture Observability Verification
================================================
Validates Bifrost's "zero-config observability" claim.

What this does:
  1. Sends a request with a unique marker through Bifrost
  2. Queries Bifrost's local SQLite database to find that request
  3. Reports what metadata was automatically captured — and what wasn't

How it calls the gateway:
  Uses the OpenAI SDK pointed at Bifrost (same as test_routing.py).
  After the request, reads directly from ~/.config/bifrost/logs.db.

Why this matters:
  Bifrost claims all traffic metadata is captured automatically with <0.1ms
  overhead and zero SDK instrumentation. This test verifies that claim by
  checking exactly what fields are populated for a known request.

What we're testing:
  - Is the "zero-config" claim true? (no SDK needed)
  - What metadata is captured automatically? (prompt, response, tokens, cost, latency)
  - Are there any gaps? (missing fields, inaccurate costs)

Usage:
  1. Ensure Bifrost is running at localhost:8080
  2. Run: conda run -n bifrost-eval python tests/test_observability.py
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

# Unique marker so we can find this exact request in the database
TRACE_MARKER = f"OBSERVABILITY_TEST_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Step 1: Send a request with a unique marker
# ---------------------------------------------------------------------------

def send_traced_request():
    """Send a request with a unique marker we can search for in the logs."""
    prompt = f"{TRACE_MARKER}: Explain observability in distributed systems in 2 sentences."

    print(f"\n>> Sending traced request")
    print(f"   Marker: {TRACE_MARKER}")
    print(f"   Model: anthropic/claude-opus-4-6")

    start = time.time()
    try:
        response = client.chat.completions.create(
            model="anthropic/claude-opus-4-6",
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
            "prompt": prompt,
            "response": content,
            "sdk_latency_ms": round(latency_ms, 1),
            "sdk_usage": sdk_usage,
        }

    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        print(f"   ERROR: {str(e)[:300]}")
        return {"status": "ERROR", "error": str(e)[:500]}


# ---------------------------------------------------------------------------
# Step 2: Query Bifrost's SQLite database for the traced request
# ---------------------------------------------------------------------------

def query_logs_for_marker(marker, max_wait_seconds=10):
    """Search the Bifrost logs database for our unique marker."""
    print(f"\n>> Searching Bifrost logs for marker: {marker}")

    if not os.path.exists(BIFROST_LOGS_DB):
        print(f"   ERROR: Logs database not found at {BIFROST_LOGS_DB}")
        return None

    # Wait briefly for async logging to complete
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

    print(f"   NOT FOUND after {max_wait_seconds}s — logging may be delayed or marker not stored")
    return None


# ---------------------------------------------------------------------------
# Step 3: Analyze what was captured
# ---------------------------------------------------------------------------

def analyze_capture(log_entry, sdk_data):
    """Compare what Bifrost captured vs what the SDK reported."""
    print("\n" + "=" * 70)
    print("OBSERVABILITY CAPTURE ANALYSIS")
    print("=" * 70)

    if log_entry is None:
        print("\n  FAIL: Request not found in Bifrost logs database.")
        print("  This means either:")
        print("  - Async logging hasn't flushed yet")
        print("  - The marker wasn't stored in input_history")
        print("  - Logging is not working for this request type")
        return {"status": "NOT_FOUND"}

    # Define what we expect to be captured
    fields_to_check = [
        ("id", "Request ID", log_entry.get("id")),
        ("provider", "Provider Name", log_entry.get("provider")),
        ("model", "Model Name", log_entry.get("model")),
        ("status", "Request Status", log_entry.get("status")),
        ("latency", "Latency (ms)", log_entry.get("latency")),
        ("cost", "Cost ($)", log_entry.get("cost")),
        ("prompt_tokens", "Prompt Tokens", log_entry.get("prompt_tokens")),
        ("completion_tokens", "Completion Tokens", log_entry.get("completion_tokens")),
        ("total_tokens", "Total Tokens", log_entry.get("total_tokens")),
        ("input_history", "Prompt/Messages", "CAPTURED" if log_entry.get("input_history") else None),
        ("output_message", "Response", "CAPTURED" if log_entry.get("output_message") else None),
        ("tool_calls", "Tool Calls", "CAPTURED" if log_entry.get("tool_calls") else "N/A (no tools in request)"),
        ("params", "Request Parameters", "CAPTURED" if log_entry.get("params") else None),
        ("stream", "Streaming Flag", log_entry.get("stream")),
        ("selected_key_id", "API Key Used", log_entry.get("selected_key_id") or "Not tracked"),
        ("virtual_key_id", "Virtual Key", log_entry.get("virtual_key_id") or "Not configured"),
        ("timestamp", "Timestamp", log_entry.get("timestamp")),
    ]

    captured = 0
    missing = 0
    results = {}

    print(f"\n{'Field':<25} {'Status':<12} {'Value'}")
    print("-" * 70)

    for field_name, display_name, value in fields_to_check:
        if value is not None and value != "" and value != 0:
            status = "CAPTURED"
            captured += 1
            # Truncate long values for display
            display_val = str(value)[:60]
        else:
            status = "MISSING"
            missing += 1
            display_val = "—"

        print(f"  {display_name:<23} [{status:<8}] {display_val}")
        results[field_name] = {"status": status, "value": str(value)[:200] if value else None}

    # Cross-check: do Bifrost's numbers match the SDK's numbers?
    print(f"\n{'Cross-Check':<25} {'Match?':<12} {'SDK':<15} {'Bifrost'}")
    print("-" * 70)

    sdk_usage = sdk_data.get("sdk_usage", {})
    for token_field, label in [
        ("prompt_tokens", "Prompt Tokens"),
        ("completion_tokens", "Completion Tokens"),
        ("total_tokens", "Total Tokens"),
    ]:
        sdk_val = sdk_usage.get(token_field, "?")
        bf_val = log_entry.get(token_field, "?")
        match = "YES" if sdk_val == bf_val else "MISMATCH"
        print(f"  {label:<23} [{match:<8}] {sdk_val:<15} {bf_val}")

    print(f"\n  Summary: {captured} fields captured, {missing} fields missing/empty")
    capture_rate = captured / (captured + missing) * 100 if (captured + missing) > 0 else 0
    print(f"  Capture rate: {capture_rate:.0f}%")

    return {
        "status": "ANALYZED",
        "captured": captured,
        "missing": missing,
        "capture_rate": round(capture_rate, 1),
        "details": results,
    }


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

    # Step 1: Send traced request
    sdk_data = send_traced_request()
    if sdk_data["status"] != "SUCCESS":
        print("\nRequest failed — cannot verify observability.")
        sys.exit(1)

    # Step 2: Find it in the logs
    log_entry = query_logs_for_marker(TRACE_MARKER)

    # Step 3: Analyze what was captured
    analysis = analyze_capture(log_entry, sdk_data)

    # Save results
    results_path = os.path.join(os.path.dirname(__file__), "results", "observability_results.json")
    output = {
        "test": "observability_auto_capture",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "trace_marker": TRACE_MARKER,
        "sdk_data": sdk_data,
        "bifrost_log_found": log_entry is not None,
        "analysis": analysis,
    }
    # Remove non-serializable values
    if log_entry:
        output["bifrost_log_fields"] = {
            k: str(v)[:200] if v else None for k, v in log_entry.items()
        }

    os.makedirs(os.path.dirname(results_path), exist_ok=True)
    with open(results_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to: {results_path}")
