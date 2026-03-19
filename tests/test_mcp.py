"""
Test 3: MCP Gateway — Free Tier Experience & Enterprise Boundary
================================================================
Explores what the MCP gateway offers in the free OSS tier vs what's
behind the enterprise paywall — and whether the upgrade path is compelling.

What this does:
  1. Queries Bifrost's API for configured MCP servers and available tools
  2. Checks what MCP tool call data was captured from prior sessions
  3. Maps the free-tier MCP features vs enterprise-only features
  4. Assesses: does a developer using MCP for free feel the pull toward enterprise?

How it calls the gateway:
  Uses Bifrost's REST API endpoints for MCP configuration and the local
  SQLite database for historical MCP tool call logs.

Why this matters:
  MCP gateway is Bifrost's strategic differentiator — no other gateway has it.
  The free tier must create enough value to hook developers, while the enterprise
  tier (auth, tool groups, governance) must solve a pain they can feel.
  If the free→paid boundary is wrong, the differentiator doesn't monetize.

What we're testing:
  - What MCP features are accessible in the free tier?
  - What data is captured for MCP tool calls?
  - Does the free experience naturally surface the need for governance?
  - Is the enterprise upsell visible and compelling?

Usage:
  1. Ensure Bifrost is running at localhost:8080
  2. Run: conda run -n bifrost-eval python tests/test_mcp.py
"""

import json
import os
import sqlite3
import sys
import time

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

BIFROST_BASE_URL = os.getenv("BIFROST_BASE_URL", "http://localhost:8080")
BIFROST_LOGS_DB = os.path.expanduser("~/.config/bifrost/logs.db")
BIFROST_CONFIG_DB = os.path.expanduser("~/.config/bifrost/config.db")


# ---------------------------------------------------------------------------
# Part 1: MCP Configuration Discovery
# ---------------------------------------------------------------------------

def discover_mcp_config():
    """Query Bifrost's API to understand current MCP configuration."""
    print("\n" + "=" * 70)
    print("PART 1: MCP Configuration Discovery")
    print("=" * 70)

    results = {}

    # Check MCP clients (servers configured)
    endpoints = [
        ("/api/v1/mcp/clients", "MCP Clients (Servers)"),
        ("/api/v1/mcp/tools", "MCP Tools Available"),
        ("/api/v1/mcp/settings", "MCP Settings"),
    ]

    for endpoint, label in endpoints:
        url = f"{BIFROST_BASE_URL}{endpoint}"
        print(f"\n>> {label}: GET {endpoint}")
        try:
            resp = requests.get(url, timeout=10)
            print(f"   Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                print(f"   Response: {json.dumps(data, indent=2)[:500]}")
                results[endpoint] = {"status": resp.status_code, "data": data}
            else:
                print(f"   Response: {resp.text[:300]}")
                results[endpoint] = {"status": resp.status_code, "error": resp.text[:300]}
        except requests.exceptions.ConnectionError:
            print(f"   ERROR: Connection failed")
            results[endpoint] = {"status": "CONNECTION_ERROR"}
        except Exception as e:
            print(f"   ERROR: {str(e)[:200]}")
            results[endpoint] = {"status": "ERROR", "error": str(e)[:200]}

    return results


# ---------------------------------------------------------------------------
# Part 2: Historical MCP Tool Call Analysis
# ---------------------------------------------------------------------------

def analyze_mcp_tool_logs():
    """Analyze MCP tool call data captured from prior sessions (e.g., Claude Code)."""
    print("\n" + "=" * 70)
    print("PART 2: Historical MCP Tool Call Analysis")
    print("=" * 70)

    if not os.path.exists(BIFROST_LOGS_DB):
        print(f"   Logs database not found at {BIFROST_LOGS_DB}")
        return {"status": "NO_DB"}

    conn = sqlite3.connect(BIFROST_LOGS_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Count total MCP tool calls
    cursor.execute("SELECT COUNT(*) as count FROM mcp_tool_logs")
    total_mcp = cursor.fetchone()["count"]
    print(f"\n   Total MCP tool call logs: {total_mcp}")

    if total_mcp == 0:
        print("   No MCP tool calls recorded.")
        print("   This is expected if MCP servers weren't configured, or if the")
        print("   Claude Code session's tool calls weren't captured as MCP calls.")

        # Check if tool_calls were captured in the main logs instead
        cursor.execute("SELECT COUNT(*) as count FROM logs WHERE tool_calls IS NOT NULL AND tool_calls != ''")
        tool_call_logs = cursor.fetchone()["count"]
        print(f"\n   LLM requests with tool_calls in main logs: {tool_call_logs}")

        if tool_call_logs > 0:
            cursor.execute(
                "SELECT id, model, tool_calls, created_at FROM logs "
                "WHERE tool_calls IS NOT NULL AND tool_calls != '' "
                "ORDER BY created_at DESC LIMIT 3"
            )
            for row in cursor.fetchall():
                tc = row["tool_calls"]
                tc_preview = tc[:200] if tc else "None"
                print(f"\n   Request {row['id'][:12]}... ({row['model']}):")
                print(f"   Tool calls: {tc_preview}...")

        conn.close()
        return {
            "status": "NO_MCP_LOGS",
            "total_mcp_logs": 0,
            "tool_calls_in_llm_logs": tool_call_logs,
            "observation": "Tool calls captured in LLM logs but not in dedicated MCP log table. "
                           "This suggests the Claude Code session's tool calls were proxied but "
                           "not routed through Bifrost's MCP gateway pipeline.",
        }

    # If we have MCP logs, analyze them
    cursor.execute(
        "SELECT tool_name, server_label, status, COUNT(*) as count, "
        "AVG(latency) as avg_latency, SUM(cost) as total_cost "
        "FROM mcp_tool_logs GROUP BY tool_name, server_label, status "
        "ORDER BY count DESC LIMIT 20"
    )
    tool_stats = [dict(row) for row in cursor.fetchall()]

    print(f"\n   Tool call breakdown:")
    print(f"   {'Tool':<30} {'Server':<15} {'Status':<10} {'Count':<8} {'Avg Latency'}")
    print("   " + "-" * 80)
    for stat in tool_stats:
        print(
            f"   {stat['tool_name']:<30} "
            f"{(stat['server_label'] or 'unknown'):<15} "
            f"{stat['status']:<10} "
            f"{stat['count']:<8} "
            f"{stat['avg_latency']:.0f}ms" if stat['avg_latency'] else "N/A"
        )

    # Check what metadata is captured per MCP call
    cursor.execute("SELECT * FROM mcp_tool_logs ORDER BY created_at DESC LIMIT 1")
    sample = cursor.fetchone()
    if sample:
        sample_dict = dict(sample)
        captured_fields = [k for k, v in sample_dict.items() if v is not None and v != ""]
        missing_fields = [k for k, v in sample_dict.items() if v is None or v == ""]
        print(f"\n   Fields captured per MCP call: {len(captured_fields)}/{len(sample_dict)}")
        print(f"   Captured: {', '.join(captured_fields)}")
        print(f"   Missing: {', '.join(missing_fields)}")

    conn.close()
    return {
        "status": "ANALYZED",
        "total_mcp_logs": total_mcp,
        "tool_stats": tool_stats,
    }


# ---------------------------------------------------------------------------
# Part 3: Free vs Enterprise Feature Mapping
# ---------------------------------------------------------------------------

def map_free_vs_enterprise():
    """Document what MCP features are available in free tier vs enterprise."""
    print("\n" + "=" * 70)
    print("PART 3: Free vs Enterprise MCP Feature Boundary")
    print("=" * 70)

    # Based on the Bifrost Web UI sidebar and documentation
    features = [
        # (Feature, Tier, Accessible, Evidence)
        ("MCP Catalog (add servers)", "Free", True, "Visible in Web UI sidebar under MCP Gateway"),
        ("MCP Tool Logs", "Free", True, "mcp_tool_logs table exists in logs.db"),
        ("MCP Settings", "Free", True, "Visible in Web UI sidebar"),
        ("Tool Groups (RBAC)", "Enterprise", False, "Behind 'Unlock users & user governance' paywall"),
        ("Auth Config (tool-level)", "Enterprise", False, "Behind enterprise paywall in Web UI"),
        ("Virtual Key → Tool mapping", "Enterprise", False, "Requires enterprise governance"),
        ("Code Mode (meta-tools)", "Free", True, "Documented as OSS feature"),
        ("Manual/Agent/Code modes", "Free", True, "Three execution modes in OSS"),
        ("Per-tool observability", "Free", None, "Unknown — need to test with MCP server configured"),
        ("Tool call approval flow", "Free", True, "Manual mode = LLM suggests, app approves"),
        ("Tool allowlisting", "Free", True, "Agent mode with allowlist"),
        ("Federated MCP (API→MCP)", "Enterprise", False, "Listed as enterprise feature in research"),
    ]

    print(f"\n   {'Feature':<35} {'Tier':<12} {'Accessible':<12} {'Evidence'}")
    print("   " + "-" * 90)

    free_count = 0
    enterprise_count = 0

    for feature, tier, accessible, evidence in features:
        if tier == "Free":
            free_count += 1
        else:
            enterprise_count += 1

        status = "Yes" if accessible else ("No" if accessible is False else "Unknown")
        print(f"   {feature:<35} {tier:<12} {status:<12} {evidence[:50]}")

    print(f"\n   Free tier features: {free_count}")
    print(f"   Enterprise-only features: {enterprise_count}")

    return {
        "features": [
            {"name": f[0], "tier": f[1], "accessible": f[2], "evidence": f[3]}
            for f in features
        ],
        "free_count": free_count,
        "enterprise_count": enterprise_count,
    }


# ---------------------------------------------------------------------------
# Part 4: Conversion Path Assessment
# ---------------------------------------------------------------------------

def assess_conversion_path(mcp_data, feature_map):
    """Assess whether the free MCP experience naturally drives enterprise upgrades."""
    print("\n" + "=" * 70)
    print("PART 4: Free → Enterprise Conversion Path Assessment")
    print("=" * 70)

    observations = []

    # Observation 1: Is the free tier useful enough to hook developers?
    if feature_map["free_count"] >= 5:
        observations.append({
            "signal": "POSITIVE",
            "finding": f"Free tier has {feature_map['free_count']} MCP features — enough to be genuinely useful",
            "impact": "Developers will actually adopt the MCP gateway, not just try it",
        })
    else:
        observations.append({
            "signal": "CONCERN",
            "finding": f"Free tier has only {feature_map['free_count']} MCP features — may feel limited",
            "impact": "Developers might not adopt deeply enough to feel the enterprise need",
        })

    # Observation 2: Does the free experience surface governance needs?
    if mcp_data.get("total_mcp_logs", 0) > 0:
        observations.append({
            "signal": "POSITIVE",
            "finding": "MCP tool calls are logged — developer can see tool usage patterns",
            "impact": "Creates awareness: 'I can see what my agents are doing, but can I control it?'",
        })
    else:
        observations.append({
            "signal": "GAP",
            "finding": "No MCP tool calls in dedicated log table despite tool_calls in LLM logs",
            "impact": "The free MCP experience may not feel differentiated from basic proxying. "
                      "If tool calls only appear in LLM logs (not a dedicated MCP view), "
                      "the governance narrative doesn't start building.",
        })

    # Observation 3: Is the enterprise upgrade visible?
    observations.append({
        "signal": "PRESENT_BUT_WEAK",
        "finding": "Enterprise features show 'Book a demo' paywall in Web UI",
        "impact": "The paywall exists but doesn't explain WHY governance matters. "
                  "A developer who hasn't felt the pain of uncontrolled tool access "
                  "won't be motivated to 'Book a demo'. The free tier should surface "
                  "the governance gap (e.g., 'X tool calls had no authorization policy') "
                  "before presenting the gate.",
    })

    print("\n   Conversion Path Observations:")
    for i, obs in enumerate(observations, 1):
        print(f"\n   {i}. [{obs['signal']}] {obs['finding']}")
        print(f"      Impact: {obs['impact']}")

    return {"observations": observations}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Bifrost Product Evaluation — MCP Gateway Test")
    print(f"Gateway: {BIFROST_BASE_URL}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Connectivity check
    try:
        health = requests.get(f"{BIFROST_BASE_URL}/health", timeout=5)
        print(f"Bifrost health: {health.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"\nERROR: Cannot connect to Bifrost at {BIFROST_BASE_URL}")
        sys.exit(1)

    # Run all parts
    config_results = discover_mcp_config()
    mcp_data = analyze_mcp_tool_logs()
    feature_map = map_free_vs_enterprise()
    conversion_assessment = assess_conversion_path(mcp_data, feature_map)

    # Save results
    results_path = os.path.join(os.path.dirname(__file__), "results", "mcp_results.json")
    output = {
        "test": "mcp_gateway_assessment",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "config_discovery": config_results,
        "mcp_tool_logs": mcp_data,
        "feature_boundary": feature_map,
        "conversion_assessment": conversion_assessment,
    }
    os.makedirs(os.path.dirname(results_path), exist_ok=True)
    with open(results_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to: {results_path}")
